#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
embed_structure_secondarybert.py — SecondaryBERT POR RESIDUO sobre los fragmentos.

PARA QUE
--------
El brazo de estructura secundaria del cargador usa **3 canales one-hot** de
C/H/E. Peticion de Laura del 25 nov: que SecondaryBERT sin mean pooling sea
**otro brazo**, ademas del one-hot. Tiene razon, y conviene decir con precision
qué compara cada uno, porque no es lo mismo.

> **El one-hot por residuo ya contiene TODA la informacion que SecondaryBERT
> recibe.** Su entrada es exactamente la cadena de C/H/E, y 3 canales one-hot la
> codifican sin pérdida. SecondaryBERT no puede, por tanto, añadir informacion:
> solo una **recodificacion aprendida**. Esto NO era asi en el pipeline
> historico, donde los dos iban promediados y promediar el one-hot deja solo 3
> numeros —las fracciones de C/H/E—, que si destruye casi todo.
>
> **Y por eso este brazo es el que cierra bien la linea de §0.5.6.** Al brazo de
> one-hot se le puede objetar que 3 canales sobre 21.507 features se ahogan, de
> modo que un resultado nulo seria de escala y no de contenido. SecondaryBERT da
> `w x 768` = 16.128 features, del mismo orden que las 21.504 de ProtT5: iguala
> el peso de las dos modalidades en la entrada y elimina la objecion.

DEDUPLICAR POR LA CADENA Q3, NO POR EL FRAGMENTO
-----------------------------------------------
Muchas secuencias distintas comparten estructura: **257.691 cadenas Q3 unicas
para 2.210.409 fragmentos unicos en w21**, el 11,7 %. Como la entrada del modelo
es solo la cadena Q3, se embebe una vez por cadena y se une por ella. Son **8,3
GB en lugar de 71,3** en w21 y 16,6 en lugar de 74,3 en w25.

De paso, el numero dice algo del dato: 8,6 fragmentos por cadena de estructura
significa que Q3 es una descripcion muy gruesa de la ventana.

EL PROMEDIO HISTORICO SE REPRODUCE EXACTAMENTE
----------------------------------------------
`generate_secondary_bert_embeddings.py:253` hace
`last_hidden_state[:, 1:-1, :].mean(dim=1)`: promedio sobre los residuos
**excluyendo `[CLS]` y `[SEP]`**. **Esto corrige §7.1, que afirmaba que la
extraccion historica usaba `[CLS]` de la ultima capa.** No lo hacia. La
consecuencia practica es buena: al contrario que con ProtT5 —donde el historico
incluia el EOS en el promedio y por eso no se puede reproducir desde los
residuos solos— aqui promediar el tensor por residuo da el vector historico sin
aproximacion. El `[CLS]` se guarda aparte de todos modos, por si acaso.

USO
---
    P=/home/nap/miniconda3/envs/nap_env/bin/python
    # en CPU, para no ocupar una tercera GPU mientras el entrenamiento usa dos
    $P -u data_pipeline/scripts/embeddings/secondary_structure/\\
embed_structure_secondarybert.py \\
        --fragments data/fragments_w21_ss --out data/embeddings_sbert_w21 \\
        --device cpu --hilos 24
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

MODELO = Path("model/secondary_bert")
DIM = 768
# Los ids los fija el tokenizer del checkpoint; se verifican contra
# tokenizer.json antes de usarlos, no se dan por buenos.
CLS_ID, SEP_ID = 2, 3
Q3_ID = {"C": 5, "H": 6, "E": 7}


def _git_commit(repo: Path) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                           capture_output=True, text=True, timeout=10)
        h = r.stdout.strip()
        if not h:
            return None
        # §19 pide el commit Y el estado del repositorio: devolver el hash a
        # secas con el arbol modificado senala un codigo que no es el que se
        # ejecuto, y quien reproduzca desde ese commit no vera los cambios.
        s = subprocess.run(["git", "-C", str(repo), "status", "--porcelain",
                            "--untracked-files=no"],
                           capture_output=True, text=True, timeout=10)
        return h + ("-sucio" if s.stdout.strip() else "")
    except Exception:
        return None


def verifica_vocabulario(model_dir: Path) -> None:
    """Que los ids codificados coincidan con el tokenizer del checkpoint."""
    tk = json.loads((model_dir / "tokenizer.json").read_text())
    v = tk["model"]["vocab"]
    esperado = {"[CLS]": CLS_ID, "[SEP]": SEP_ID, **Q3_ID}
    malos = {k: (v.get(k), i) for k, i in esperado.items() if v.get(k) != i}
    if malos:
        raise SystemExit(f"ABORTADO: el tokenizer no coincide: {malos}")
    print(f"  vocabulario verificado contra tokenizer.json: {esperado}")


def cadenas_unicas(frag_dir: Path) -> tuple[list[str], int, dict]:
    """Cadenas Q3 unicas de los fragmentos con estructura, y la ventana."""
    vistas: set[str] = set()
    w = None
    filas = con_ss = 0
    frags: set[str] = set()
    for f in sorted(frag_dir.rglob("fragments_ss.parquet")):
        d = pd.read_parquet(f, columns=["fragmento", "secondary_structure",
                                        "ss_status", "ventana"])
        if len(d):
            v = int(d.ventana.iloc[0])
            if w is None:
                w = v
            elif w != v:
                raise SystemExit(f"ABORTADO: ventanas distintas ({w} y {v})")
        filas += len(d)
        d = d[d.ss_status == "ok"]
        con_ss += len(d)
        vistas.update(d.secondary_structure)
        frags.update(d.fragmento)
    malas = [s for s in list(vistas)[:2000] if len(s) != w or set(s) - set("CHE")]
    if malas:
        raise SystemExit(f"ABORTADO: cadenas Q3 invalidas: {malas[:3]}")
    stats = {"filas": filas, "filas_con_ss": con_ss,
             "fragmentos_unicos": len(frags), "cadenas_q3_unicas": len(vistas)}
    return sorted(vistas), int(w), stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fragments", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--model", type=Path, default=MODELO)
    ap.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    ap.add_argument("--hilos", type=int, default=0,
                    help="hilos de torch en CPU; 0 deja el valor por omision")
    ap.add_argument("--batch", type=int, default=1024)
    ap.add_argument("--chunk", type=int, default=20_000)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    import torch
    from transformers import BertModel

    repo = Path(__file__).resolve().parents[4]
    args.out.mkdir(parents=True, exist_ok=True)
    if args.device == "cuda" and not torch.cuda.is_available():
        print("ERROR: sin CUDA", file=sys.stderr)
        return 2
    if args.hilos:
        torch.set_num_threads(args.hilos)
    print(f"dispositivo {args.device} | hilos torch {torch.get_num_threads()}",
          flush=True)

    verifica_vocabulario(args.model)
    seqs, w, stats = cadenas_unicas(args.fragments)
    if 2 + w > 30:
        raise SystemExit(f"ABORTADO: {2+w} tokens y max_position_embeddings=30")
    print(f"  filas {stats['filas']:,} | con estructura {stats['filas_con_ss']:,} | "
          f"fragmentos unicos {stats['fragmentos_unicos']:,} | "
          f"cadenas Q3 unicas {len(seqs):,} "
          f"({100*len(seqs)/stats['fragmentos_unicos']:.1f} %) | w={w}", flush=True)

    # El indice se indexa por la CADENA Q3, no por el fragmento: es la clave de
    # union del cargador.
    idx_p = args.out / "index.parquet"
    if args.force or not idx_p.exists():
        pd.DataFrame({
            "secondary_structure": seqs,
            "chunk": [i // args.chunk for i in range(len(seqs))],
            "fila": [i % args.chunk for i in range(len(seqs))],
        }).to_parquet(idx_p, index=False, compression="zstd")
        print(f"  indice escrito: {idx_p}", flush=True)

    mdl = BertModel.from_pretrained(args.model).to(args.device).eval()
    npar = sum(p.numel() for p in mdl.parameters())
    print(f"  modelo cargado: {npar:,} parametros", flush=True)

    n_chunks = (len(seqs) + args.chunk - 1) // args.chunk
    t0 = time.time()
    hechos = 0
    for c in range(n_chunks):
        r_p = args.out / f"chunk_{c:06d}_residues.npy"
        l_p = args.out / f"chunk_{c:06d}_cls.npy"
        s_p = args.out / f"chunk_{c:06d}_seq.txt"
        if r_p.exists() and l_p.exists() and s_p.exists() and not args.force:
            print(f"  [salta] chunk {c:06d}", flush=True)
            continue
        bloque = seqs[c * args.chunk:(c + 1) * args.chunk]
        res = np.empty((len(bloque), w, DIM), dtype=np.float16)
        cls = np.empty((len(bloque), DIM), dtype=np.float16)
        with torch.no_grad():
            for i in range(0, len(bloque), args.batch):
                b = bloque[i:i + args.batch]
                ids = torch.tensor(
                    [[CLS_ID] + [Q3_ID[ch] for ch in s] + [SEP_ID] for s in b],
                    dtype=torch.long, device=args.device)
                out = mdl(input_ids=ids,
                          attention_mask=torch.ones_like(ids)).last_hidden_state
                # out[:, 0] es [CLS]; out[:, 1:1+w] son los residuos; el ultimo
                # es [SEP]. El promedio de out[:, 1:-1] reproduce exactamente el
                # vector del pipeline historico.
                res[i:i + len(b)] = out[:, 1:1 + w].cpu().numpy()
                cls[i:i + len(b)] = out[:, 0].cpu().numpy()
        if not np.isfinite(res).all():
            raise SystemExit(f"ABORTADO: valores no finitos en el chunk {c}")
        np.save(r_p, res)
        np.save(l_p, cls)
        s_p.write_text("\n".join(bloque))
        hechos += len(bloque)
        vel = hechos / (time.time() - t0)
        print(f"  chunk {c:06d}: {len(bloque):,} cadenas | {vel:,.0f} cad/s | "
              f"quedan ~{(len(seqs)-hechos)/vel/60:,.1f} min", flush=True)

    man_p = args.out / "manifest.json"
    man_p.write_text(json.dumps({
        "generado_por": "data_pipeline/scripts/embeddings/secondary_structure/"
                        "embed_structure_secondarybert.py",
        "fecha_utc": datetime.now(timezone.utc).isoformat(),
        "commit_git": _git_commit(repo),
        "fragmentos": str(args.fragments),
        "modelo": str(args.model),
        "parametros": npar,
        "ventana": w, "dim": DIM,
        "clave_del_indice": "secondary_structure (la cadena Q3), NO el fragmento",
        "motivo": ("la entrada del modelo es solo la cadena Q3, asi que se embebe "
                   "una vez por cadena: 257.691 unicas para 2.210.409 fragmentos "
                   "en w21, el 11,7 %"),
        **stats,
        "chunk": args.chunk, "batch": args.batch, "device": args.device,
        "pooling": "ninguno: estado oculto por residuo, (N, w, 768) fp16",
        "cls": ("guardado aparte en chunk_*_cls.npy. OJO: la extraccion "
                "historica NO usaba [CLS] —§7.1 lo afirmaba y es falso—, sino "
                "last_hidden_state[:, 1:-1, :].mean(dim=1), es decir promedio "
                "sobre los residuos excluyendo [CLS] y [SEP]. Ese promedio se "
                "reproduce exactamente desde este tensor por residuo"),
        "limitacion_informativa": (
            "el one-hot por residuo de C/H/E ya contiene toda la informacion que "
            "este modelo recibe; lo que este brazo mide es si una recodificacion "
            "preentrenada ayuda, no si aporta informacion nueva"),
        "segundos": round(time.time() - t0, 1),
    }, indent=2, ensure_ascii=False))
    print(f"\n{hechos:,} cadenas en {(time.time()-t0)/60:.1f} min\n"
          f"Manifiesto: {man_p}\nDONE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
