#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
embed_fragments_prott5.py — ProtT5 POR RESIDUO sobre los fragmentos.

QUE CAMBIA RESPECTO AL HISTORICO
--------------------------------
1. **No hay mean pooling.** Se guarda el estado oculto de CADA residuo:
   `(N, w, 1024)` en lugar de `(N, 1024)`. Decision de Laura del 25 nov, y es
   la correcta porque **del vector por residuo se puede derivar cualquier
   agregado despues, y del promedio no se puede recuperar nada**. Cuesta ~23x
   mas disco y ni un segundo mas de GPU.

   Se guarda ademas el vector del token `</s>` aparte, de modo que tambien se
   puede reproducir el promedio del pipeline historico, que lo incluia.

2. **Se embebe solo el fragmento UNICO.** El 34 % de las filas repiten
   secuencia, porque la misma region de proteina es senuelo en varias
   familias. Se embebe una vez y el entrenamiento une por secuencia.

3. **Sin padding ni mascara.** Todos los fragmentos de una configuracion miden
   exactamente `w`, asi que el lote es rectangular por construccion: no hay
   posiciones de relleno que excluir, que era la fuente de error del §6.

4. **Tokenizador leido del propio `spiece.model`.** `transformers` 5.x no carga
   el SentencePiece de ProtT5 (lo confunde con un tiktoken y pide `tiktoken`),
   y `sentencepiece` no esta en ningun entorno de este servidor. El vocabulario
   de ProtT5 son 28 piezas y se extrae del fichero del modelo con un lector
   minimo de protobuf: NO se codifica a mano, se lee del modelo, de modo que no
   puede desviarse de el. Los 20 aminoacidos aparecen como `_A`, `_L`, ...
   porque la entrada de ProtT5 va con espacios entre residuos.

SOBRE EL EOS DEL HISTORICO
--------------------------
`prott5_v2.py:121` declara `pooling="float32 mean of final hidden states at
active positions including EOS"`, y en efecto promediaba sobre la secuencia
entera incluido `</s>`. Para una ventana de 25 aa eso es 1/26 del vector, un
3,8 % que no es un residuo. Aqui se separa, y quien quiera reproducir el
promedio historico puede recomponerlo.

USO
---
    P=/home/nap/miniconda3/envs/nap_env/bin/python
    # dos GPU, una por proceso, dejando 2 y 3 libres
    for g in 0 1; do
      CUDA_VISIBLE_DEVICES=$g $P -u \\
        data_pipeline/scripts/embeddings/primary_structure/embed_fragments_prott5.py \\
        --fragments data/fragments_w21 --out data/embeddings_prott5_w21 \\
        --shard $g --shards 2 &
    done; wait
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

MODELO = "model/prott5/94a6abc029ae13029317b140b7424e012bf8dfbf"
DIM = 1024


def _git_commit(repo: Path) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip() or None
    except Exception:
        return None


def leer_vocabulario(spiece: Path) -> dict[str, int]:
    """Extrae {pieza: id} del `spiece.model` con un lector minimo de protobuf.

    El fichero es un `ModelProto`: campo 1 repetido `pieces`, y cada
    `SentencePiece` tiene el texto en su campo 1. El id es el orden de
    aparicion. Se quita el marcador de inicio de palabra U+2581 para que la
    clave sea la letra del aminoacido.
    """
    d = spiece.read_bytes()

    def vi(b: bytes, i: int) -> tuple[int, int]:
        r = s = 0
        while True:
            x = b[i]
            i += 1
            r |= (x & 0x7F) << s
            s += 7
            if not x & 0x80:
                return r, i

    piezas: list[str] = []
    i = 0
    while i < len(d):
        tag, i = vi(d, i)
        campo, wt = tag >> 3, tag & 7
        if wt == 2:
            n, i = vi(d, i)
            sub = d[i:i + n]
            i += n
            if campo == 1:
                j, texto = 0, None
                while j < len(sub):
                    t2, j = vi(sub, j)
                    f2, w2 = t2 >> 3, t2 & 7
                    if w2 == 2:
                        m, j = vi(sub, j)
                        v = sub[j:j + m]
                        j += m
                        if f2 == 1:
                            texto = v.decode("utf-8")
                    elif w2 == 5:
                        j += 4
                    elif w2 == 0:
                        _, j = vi(sub, j)
                    else:
                        break
                if texto:
                    piezas.append(texto)
        elif wt == 0:
            _, i = vi(d, i)
        elif wt == 5:
            i += 4
        else:
            break
    vocab = {(p[1:] if p.startswith("▁") else p): k for k, p in enumerate(piezas)}
    faltan = [a for a in "ACDEFGHIKLMNPQRSTVWY" if a not in vocab]
    if faltan:
        raise SystemExit(f"ABORTADO: el vocabulario no trae {faltan}")
    for esp in ("</s>", "<unk>", "<pad>"):
        if esp not in vocab:
            raise SystemExit(f"ABORTADO: falta el token especial {esp}")
    return vocab


def fragmentos_unicos(frag_dir: Path) -> tuple[list[str], int]:
    """Secuencias unicas, en orden determinista, y la longitud de ventana."""
    vistos: set[str] = set()
    w = None
    for f in sorted(frag_dir.rglob("fragments.parquet")):
        d = pd.read_parquet(f, columns=["fragmento", "ventana"])
        if len(d):
            v = int(d.ventana.iloc[0])
            if w is None:
                w = v
            elif w != v:
                raise SystemExit(f"ABORTADO: ventanas distintas en el mismo "
                                 f"directorio ({w} y {v})")
        vistos.update(d.fragmento)
    malos = [s for s in list(vistos)[:1000] if len(s) != w]
    if malos:
        raise SystemExit(f"ABORTADO: fragmentos que no miden {w}: {malos[:3]}")
    return sorted(vistos), int(w)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fragments", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--model", type=Path, default=Path(MODELO))
    ap.add_argument("--batch", type=int, default=1024,
                    help="1024 es el optimo medido: ~520 frag/s y 6,2 GiB de VRAM")
    ap.add_argument("--chunk", type=int, default=20_000,
                    help="fragmentos por fichero de salida (~860 MB con w=21)")
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--shards", type=int, default=1)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    import torch
    from transformers import T5EncoderModel

    if not torch.cuda.is_available():
        print("ERROR: sin CUDA", file=sys.stderr)
        return 2
    repo = Path(__file__).resolve().parents[4]
    args.out.mkdir(parents=True, exist_ok=True)

    vocab = leer_vocabulario(args.model / "spiece.model")
    EOS, UNK = vocab["</s>"], vocab["<unk>"]

    seqs, w = fragmentos_unicos(args.fragments)
    print(f"[shard {args.shard}/{args.shards}] {len(seqs):,} fragmentos unicos, w={w}",
          flush=True)

    # Indice global, escrito una sola vez por el shard 0: es el contrato que
    # permite al entrenamiento unir fragmento -> (chunk, fila).
    idx_p = args.out / "index.parquet"
    if args.shard == 0 and (args.force or not idx_p.exists()):
        pd.DataFrame({
            "fragmento": seqs,
            "chunk": [i // args.chunk for i in range(len(seqs))],
            "fila": [i % args.chunk for i in range(len(seqs))],
        }).to_parquet(idx_p, index=False, compression="zstd")
        print(f"  indice escrito: {idx_p}", flush=True)

    mdl = T5EncoderModel.from_pretrained(args.model, dtype=torch.float16).cuda().eval()

    n_chunks = (len(seqs) + args.chunk - 1) // args.chunk
    mios = [c for c in range(n_chunks) if c % args.shards == args.shard]
    print(f"  chunks totales {n_chunks}, de este shard {len(mios)}", flush=True)

    t0 = time.time()
    hechos = 0
    for c in mios:
        r_p = args.out / f"chunk_{c:06d}_residues.npy"
        e_p = args.out / f"chunk_{c:06d}_eos.npy"
        s_p = args.out / f"chunk_{c:06d}_seq.txt"
        if r_p.exists() and e_p.exists() and s_p.exists() and not args.force:
            print(f"  [salta] chunk {c:06d}", flush=True)
            continue
        bloque = seqs[c * args.chunk:(c + 1) * args.chunk]
        res = np.empty((len(bloque), w, DIM), dtype=np.float16)
        eos = np.empty((len(bloque), DIM), dtype=np.float16)
        with torch.no_grad():
            for i in range(0, len(bloque), args.batch):
                b = bloque[i:i + args.batch]
                ids = torch.tensor(
                    [[vocab.get(ch, UNK) for ch in s] + [EOS] for s in b],
                    dtype=torch.long, device="cuda")
                if int((ids == UNK).sum()):
                    raise SystemExit("ABORTADO: aminoacido fuera del vocabulario")
                out = mdl(input_ids=ids,
                          attention_mask=torch.ones_like(ids)).last_hidden_state
                # out[:, :w] son los residuos; out[:, w] es `</s>`.
                res[i:i + len(b)] = out[:, :w].cpu().numpy()
                eos[i:i + len(b)] = out[:, w].cpu().numpy()
        if not np.isfinite(res).all():
            raise SystemExit(f"ABORTADO: valores no finitos en el chunk {c}")
        np.save(r_p, res)
        np.save(e_p, eos)
        s_p.write_text("\n".join(bloque))
        hechos += len(bloque)
        vel = hechos / (time.time() - t0)
        resto = (sum(len(seqs[x * args.chunk:(x + 1) * args.chunk]) for x in mios)
                 - hechos) / vel if vel else 0
        print(f"  chunk {c:06d}: {len(bloque):,} frag | {vel:,.0f} frag/s | "
              f"quedan ~{resto/60:,.0f} min", flush=True)

    man_p = args.out / f"manifest_shard{args.shard}.json"
    man_p.write_text(json.dumps({
        "generado_por": "data_pipeline/scripts/embeddings/primary_structure/"
                        "embed_fragments_prott5.py",
        "fecha_utc": datetime.now(timezone.utc).isoformat(),
        "commit_git": _git_commit(repo),
        "fragmentos": str(args.fragments),
        "modelo": str(args.model),
        "ventana": w,
        "dim": DIM,
        "fragmentos_unicos": len(seqs),
        "chunk": args.chunk,
        "batch": args.batch,
        "shard": args.shard, "shards": args.shards,
        "chunks_de_este_shard": mios,
        "fragmentos_escritos_ahora": hechos,
        "pooling": "ninguno: se guarda el estado oculto por residuo, (N, w, 1024) fp16",
        "eos": "guardado aparte en chunk_*_eos.npy, (N, 1024) fp16, para poder "
               "reproducir el promedio del pipeline historico, que lo incluia",
        "tokenizacion": "vocabulario leido de spiece.model; un token por residuo "
                        "mas </s> al final; sin padding porque todos los "
                        "fragmentos miden w",
        "vocab_aminoacidos": {a: vocab[a] for a in "ACDEFGHIKLMNPQRSTVWY"},
    }, indent=2, ensure_ascii=False))
    print(f"\n[shard {args.shard}] {hechos:,} fragmentos en "
          f"{(time.time()-t0)/60:.1f} min\nManifiesto: {man_p}\nDONE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
