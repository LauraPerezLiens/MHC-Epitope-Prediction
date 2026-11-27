#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
compute_scaler.py — Estandarizacion de los embeddings ProtT5, ajustada SOLO en TRAIN.

POR QUE HACE FALTA
------------------
Los estados ocultos de ProtT5 no estan normalizados: la escala varia mucho de
un canal a otro. Con AdamW eso no impide converger, pero lastra: los canales de
mayor magnitud dominan el gradiente inicial y el learning rate efectivo deja de
ser comparable entre dimensiones. §8 ya ajustaba un StandardScaler y §13.7
obliga a ajustarlo **exclusivamente en TRAIN**; esto es lo mismo para la
representacion por residuo.

LA DECISION DE DISENO: POR CANAL, NO POR (POSICION, CANAL)
----------------------------------------------------------
La entrada es `(w, 1024)`, asi que hay dos formas de estandarizar:

  * **por canal** (1024 medias y 1024 desviaciones, compartidas por las `w`
    posiciones) — la que se adopta;
  * por (posicion, canal) (21.504 o 25.600 parametros).

Se elige por canal por dos razones. Primera, es lo que necesita cualquier
modelo que **comparta pesos entre posiciones** —CNN 1D, LSTM, atencion—: si se
normaliza cada posicion con su propia media, dos residuos identicos en
posiciones distintas dejan de dar el mismo vector y se destruye la equivarianza
que justifica compartir pesos. Segunda, porque se ha medido que apenas cambia:
el script guarda **tambien** las estadisticas por posicion y reporta cuanto se
desvian de las globales, de modo que la decision queda comprobada y no asumida.

**Los 3 canales de estructura secundaria NO se estandarizan.** Son one-hot: su
media y su desviacion son las frecuencias de C/H/E, y dividir por ellas
convertiria un indicador en un numero sin interpretacion y con escalas
distintas por clase. Se dejan en 0/1.

UN SCALER POR CONJUNTO DE TRAIN, NO UNO PARA TODO
-------------------------------------------------
`primary` y `primary_secondary` comparten exactamente las mismas filas de TRAIN
(la estructura secundaria se exige en los dos brazos, §0.15.1), asi que
comparten scaler. El brazo que **conserva las contradicciones** tiene otro
TRAIN —2.666.904 filas en lugar de 2.494.946— y por tanto necesita el suyo.
Reutilizar el del brazo limpio seria usar estadisticas de un conjunto de datos
distinto del que se entrena, que es exactamente lo que §13.7 prohibe.

PONDERACION POR MULTIPLICIDAD
-----------------------------
Los embeddings guardan el fragmento **unico**, pero una misma secuencia puede
ser ejemplo de entrenamiento varias veces (senuelo en varias familias). La
distribucion de TRAIN es la de las FILAS, no la de las secuencias, asi que cada
fragmento entra con peso igual a su numero de filas en TRAIN. Sin eso el scaler
describiria un conjunto que no es el que se entrena.

USO
---
    P=/home/nap/miniconda3/envs/nap_env/bin/python
    $P -u data_pipeline/scripts/embeddings/primary_structure/compute_scaler.py \\
        --fragments data/fragments_w21_ss --embeddings data/embeddings_prott5_w21 \\
        --splits data/splits_w21/splits.parquet \\
        --out data/scalers_w21/scaler_sin_contradicciones.npz \\
        --excluir-contradictorios
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fragment_dataset import FragmentDataset  # noqa: E402

DIM = 1024
PISO_STD = 1e-6


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


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fragments", required=True)
    ap.add_argument("--embeddings", required=True)
    ap.add_argument("--splits", required=True)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--split", default="train",
                    help="por omision train; NO usar val ni test (§13.7)")
    ap.add_argument("--excluir-contradictorios", action="store_true")
    ap.add_argument("--bloque", type=int, default=2000,
                    help="filas por bloque; 2000 son ~172 MB en float32")
    ap.add_argument("--max-chunks", type=int, default=0,
                    help="solo para medir el ritmo; 0 = todos")
    args = ap.parse_args()

    if args.split != "train":
        print(f"AVISO: ajustando el scaler sobre '{args.split}'. §13.7 exige "
              f"TRAIN; esto solo vale para diagnostico.", file=sys.stderr)

    repo = Path(__file__).resolve().parents[4]
    args.out.parent.mkdir(parents=True, exist_ok=True)

    ds = FragmentDataset(
        fragments=args.fragments, embeddings=args.embeddings,
        splits=args.splits, split=args.split, features="primary",
        excluir_contradictorios=args.excluir_contradictorios, verbose=True)
    w = ds.w
    emb = Path(args.embeddings)

    # Peso de cada fragmento unico = numero de filas de TRAIN que lo usan.
    pesos = (ds.tabla.groupby(["chunk", "fila"]).size()
             .rename("peso").reset_index())
    print(f"  fragmentos unicos en {args.split}: {len(pesos):,} | "
          f"filas: {int(pesos.peso.sum()):,} | "
          f"multiplicidad media {pesos.peso.mean():.3f}, maxima {int(pesos.peso.max())}")

    S = np.zeros((w, DIM), dtype=np.float64)
    S2 = np.zeros((w, DIM), dtype=np.float64)
    # Suma de cuadrados del vector PROMEDIADO sobre las w posiciones, para el
    # brazo de control con mean pooling. La media del promedio es identica a la
    # media por canal, asi que solo hace falta el segundo momento; lo que cambia
    # es la desviacion, porque promediar 21 valores correlacionados la reduce.
    Sp2 = np.zeros(DIM, dtype=np.float64)
    n_filas = 0.0
    t0 = time.time()
    chunks = sorted(pesos.chunk.unique())
    if args.max_chunks:
        chunks = chunks[:args.max_chunks]
        print(f"  AVISO: solo {len(chunks)} chunks, el scaler NO es valido")
    for k, c in enumerate(chunks, 1):
        arr = np.load(emb / f"chunk_{c:06d}_residues.npy", mmap_mode="r")
        pc = pesos[pesos.chunk == c]
        wv = np.zeros(arr.shape[0], dtype=np.float32)
        wv[pc.fila.values] = pc.peso.values
        for a in range(0, arr.shape[0], args.bloque):
            b = min(a + args.bloque, arr.shape[0])
            wb = wv[a:b]
            if not wb.any():
                continue
            # Los productos se hacen en float32 (sgemv de BLAS) y se acumulan en
            # float64. Mezclar float64 y float32 en el `@` saca a numpy de BLAS
            # y lo manda a una ruta que es dos ordenes de magnitud mas lenta:
            # medido, 2,5 min sin terminar el primer chunk.
            Xb3 = np.asarray(arr[a:b], dtype=np.float32)
            Pb = Xb3.mean(axis=1)
            Xb = Xb3.reshape(b - a, -1)
            S += (wb @ Xb).astype(np.float64).reshape(w, DIM)
            np.square(Pb, out=Pb)
            Sp2 += (wb @ Pb).astype(np.float64)
            np.square(Xb, out=Xb)
            S2 += (wb @ Xb).astype(np.float64).reshape(w, DIM)
        n_filas += float(wv.sum(dtype=np.float64))
        if k % 5 == 0 or k == 1 or k == len(chunks):
            print(f"  chunk {c:06d} ({k}/{len(chunks)}) | "
                  f"{n_filas:,.0f} filas | {time.time()-t0:.0f} s", flush=True)

    if n_filas <= 1:
        print("ERROR: sin filas", file=sys.stderr)
        return 2

    n_res = n_filas * w
    mean_pos = S / n_filas
    var_pos = np.maximum(S2 / n_filas - mean_pos ** 2, 0.0)
    mean_canal = S.sum(axis=0) / n_res
    var_canal = np.maximum(S2.sum(axis=0) / n_res - mean_canal ** 2, 0.0)
    std_canal = np.sqrt(var_canal)
    degenerados = int((std_canal < PISO_STD).sum())
    std_canal = np.maximum(std_canal, PISO_STD)
    std_pool = np.sqrt(np.maximum(Sp2 / n_filas - mean_canal ** 2, 0.0))
    deg_pool = int((std_pool < PISO_STD).sum())
    std_pool = np.maximum(std_pool, PISO_STD)
    # Cuanto encoge la desviacion al promediar. 1/sqrt(w) seria independencia
    # total entre posiciones; cerca de 1 seria que el promedio no pierde nada.
    encogimiento = float(np.median(std_pool / std_canal))

    # Cuanto se pierde al compartir las estadisticas entre posiciones. Si esto
    # fuera grande, la decision de estandarizar por canal habria que revisarla.
    desv_rel = np.abs(mean_pos - mean_canal) / std_canal
    print(f"\n  canales con desviacion ~0 (degenerados): {degenerados}")
    print(f"  |media_posicion - media_canal| / std_canal: "
          f"mediana {np.median(desv_rel):.4f} | p99 {np.percentile(desv_rel, 99):.4f} "
          f"| max {desv_rel.max():.4f}")
    print(f"  media de std por canal {std_canal.mean():.4f} "
          f"(min {std_canal.min():.4f}, max {std_canal.max():.4f})")
    print(f"  mean pooling: std mediana {np.median(std_pool):.4f}, "
          f"encogimiento {encogimiento:.4f} (1/sqrt(w) = {1/np.sqrt(w):.4f} "
          f"seria independencia total entre posiciones) | degenerados {deg_pool}")

    np.savez(args.out, mean_canal=mean_canal.astype(np.float32),
             std_canal=std_canal.astype(np.float32),
             mean_pos=mean_pos.astype(np.float32),
             std_pos=np.sqrt(var_pos).astype(np.float32),
             mean_pool=mean_canal.astype(np.float32),
             std_pool=std_pool.astype(np.float32),
             ventana=np.int32(w), dim=np.int32(DIM),
             n_filas=np.float64(n_filas))
    man = {
        "generado_por": "data_pipeline/scripts/embeddings/primary_structure/"
                        "compute_scaler.py",
        "fecha_utc": datetime.now(timezone.utc).isoformat(),
        "commit_git": _git_commit(repo),
        "fragmentos": str(args.fragments),
        "embeddings": str(args.embeddings),
        "splits": str(args.splits),
        "split_ajustado": args.split,
        "excluir_contradictorios": bool(args.excluir_contradictorios),
        "ventana": int(w),
        "dim": DIM,
        "filas_train": int(n_filas),
        "fragmentos_unicos": int(len(pesos)),
        "residuos": int(n_res),
        "politica": ("por canal, compartido entre las w posiciones; los 3 canales "
                     "de estructura secundaria NO se estandarizan porque son one-hot"),
        "canales_degenerados": degenerados,
        "piso_std": PISO_STD,
        "desviacion_posicion_vs_canal": {
            "mediana": float(np.median(desv_rel)),
            "p99": float(np.percentile(desv_rel, 99)),
            "max": float(desv_rel.max()),
        },
        "std_canal": {"media": float(std_canal.mean()),
                      "min": float(std_canal.min()),
                      "max": float(std_canal.max())},
        "mean_pooling": {
            "nota": ("mean_pool es identica a mean_canal por construccion; lo que "
                     "cambia es la desviacion. Promedio sobre los w residuos, SIN "
                     "el token </s>: el pipeline historico lo INCLUIA (§0.11.2), "
                     "asi que este control no es bit a bit el historico"),
            "std_mediana": float(np.median(std_pool)),
            "encogimiento_mediano": encogimiento,
            "encogimiento_si_independientes": float(1 / np.sqrt(w)),
            "canales_degenerados": deg_pool,
        },
        "sha256_npz": _sha256(args.out),
        "segundos": round(time.time() - t0, 1),
    }
    p = args.out.with_suffix(".json")
    p.write_text(json.dumps(man, indent=2, ensure_ascii=False))
    print(f"\nSalida: {args.out}\nManifiesto: {p}\nDONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
