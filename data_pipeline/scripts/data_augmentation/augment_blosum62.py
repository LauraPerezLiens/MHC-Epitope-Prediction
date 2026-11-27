#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
augment_blosum62.py — Secuencias aumentadas con BLOSUM62, solo sobre TRAIN.

SUSTITUYE a `generate_blosum62_variants.py`, que lee el formato historico
(`25aa_seq`, `protein_group_id`, `contains_epitope`) que el pipeline ya no
genera. Este consume las dos salidas de fragmentos vigentes y su particion.

DOS METODOS, Y NO SON VERSIONES DEL MISMO PROCEDIMIENTO
-------------------------------------------------------
Se generan los dos como brazos comparables (decision de Laura, 27 nov 2026),
porque difieren en todo lo que importa: cuantas variantes, como se elige la
sustitucion y de donde sale la etiqueta.

  `--metodo repo` — el del pipeline historico, leido de
  `generate_blosum62_variants.py`:
    * UNA variante por CADA posicion de la ventana (25 variantes en w=25).
    * Sustitucion DETERMINISTA: siempre el aminoacido de mayor score BLOSUM62
      (`max(candidatos, key=score)`), de modo que las variantes son una funcion
      predecible del original y no aportan diversidad. Explica el coseno
      0,9883 que midio 0.4.4.
    * La etiqueta SE HEREDA del original.

  `--metodo wert` — el publicado, leido de `LSTMcvonehot.py:122` (`BLOSUMSIM`):
    * UNA posicion elegida al azar por variante, no todas.
    * El sustituto se MUESTREA entre los de score BLOSUM positivo, no se toma
      el maximo.
    * La etiqueta NO se hereda: sale de `prob = exp(score)/sum(exp(scores))` y
      se compara con `--p-aug` (0,2 en el paper). Por debajo, la variante entra
      como NEGATIVA. Replicado en 0.7.6: el self-match domina el softmax, de
      modo que el metodo genera de hecho NEGATIVOS DIFICILES a un residuo de
      un positivo, no positivos sinteticos.
    * En el paper se aplicaba ON-BATCH con `N_AUG = 1`, es decir UNA variante
      por lote y no por ejemplo. Materializarlo a disco cambia su naturaleza y
      hay que decirlo al reportarlo.

  Los cinco defectos de `BLOSUMSIM` documentados en 0.7.6 NO se reproducen
  aqui, porque reproducirlos seria heredar errores: se usa la matriz completa
  sin invertir el diccionario (`dict(map(reversed, ...))` perdia aminoacidos),
  no se descarta el primer score por orden de columna (`listprob[1:]`), C/G/P
  si tienen opciones, no se introducen `B` ni `Z` (que no son aminoacidos sino
  ambiguedades) y la ultima posicion tambien puede mutar (`randint(0, len-1)`
  nunca la elegia). El manifiesto lo deja constar.

SOLO TRAIN
----------
Se aumenta UNICAMENTE la particion TRAIN. VALIDATION y TEST se quedan con las
secuencias originales intactas. Motivo (seccion 5): si una variante cae en
TRAIN y su original en TEST, la fuga es directa —estan a coseno 0,9883— y la
metrica deja de medir generalizacion. El script LEE la particion y se niega a
funcionar sin ella.

EL INDICE QUE RELACIONA VARIANTE Y ORIGINAL
-------------------------------------------
Cada fila de salida lleva:

  * `group_id`   — identificador del GRUPO: el original y todas sus variantes
                   comparten el mismo valor. Es la unidad de independencia
                   estadistica: 26 filas de un grupo NO son 26 observaciones.
                   Cualquier particion, barajado o muestreo posterior tiene
                   que respetarlo, y es la columna por la que agrupar para
                   evitar que una variante y su original se separen.
  * `variante_id`— 0 para el original, 1..N para las variantes.
  * `es_original` — booleano, redundante con `variante_id == 0` pero explicito.
  * `fragmento_original` — la secuencia de la que deriva, para poder
                   reconstruir la relacion sin depender del `group_id`.
  * `pos_mutada` / `aa_original` / `aa_nuevo` — que cambio exactamente.
                   Permite medir el efecto de la posicion y del tipo de
                   sustitucion sin volver a alinear nada.
  * `prob_blosum` — solo en `--metodo wert`: la probabilidad del softmax que
                   decidio la etiqueta.
  * `accession`, `familia`, `especie`, `clase`, `label` — heredados.

`group_id` es un entero estable: se asigna por orden de (familia, accession,
fragmento) y se registra en el manifiesto, de modo que dos ejecuciones con los
mismos datos dan los mismos identificadores.

USO
---
    P=/home/nap/miniconda3/envs/nap_env/bin/python

    $P -u data_pipeline/scripts/data_augmentation/augment_blosum62.py \\
        --fragments data/fragments_w25_centrado_20261127 \\
        --splits    data/splits_w25_centrado_20261127/splits.parquet \\
        --out       data/augmented_w25_centrado_repo_20261127 \\
        --metodo repo

    # metodo de Wert, con su P_AUG publicado y semilla registrada:
    $P -u ... --metodo wert --p-aug 0.2 --n-variantes 25 --seed 42
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

CANONICOS = "ACDEFGHIKLMNPQRSTVWY"
FLUSH_FILAS = 2_000_000

ESQUEMA = pa.schema([
    ("group_id", pa.int64()),
    ("variante_id", pa.int16()),
    ("es_original", pa.bool_()),
    ("especie", pa.string()),
    ("clase", pa.string()),
    ("familia", pa.string()),
    ("accession", pa.string()),
    ("fragmento", pa.string()),
    ("fragmento_original", pa.string()),
    ("label", pa.int8()),
    ("pos_mutada", pa.int16()),
    ("aa_original", pa.string()),
    ("aa_nuevo", pa.string()),
    ("prob_blosum", pa.float32()),
])


def setup_logging() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s %(levelname)s: %(message)s")


def commit_git() -> str:
    try:
        repo = Path(__file__).resolve().parents[3]
        h = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo,
                                    text=True).strip()
        sucio = subprocess.check_output(["git", "status", "--porcelain"],
                                        cwd=repo, text=True).strip()
        return h + ("-sucio" if sucio else "")
    except Exception:
        return "desconocido"


def sha256(p: Path, buf: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for b in iter(lambda: fh.read(buf), b""):
            h.update(b)
    return h.hexdigest()


# --------------------------------------------------------------------------- #
# BLOSUM62. Se carga de Biopython, que trae la matriz estandar, y se registra
# su digest en el manifiesto para que la procedencia quede fijada.
# --------------------------------------------------------------------------- #
def cargar_blosum62() -> dict[str, dict[str, int]]:
    from Bio.Align import substitution_matrices
    M = substitution_matrices.load("BLOSUM62")
    out: dict[str, dict[str, int]] = {}
    for a in CANONICOS:
        out[a] = {b: int(M[a, b]) for b in CANONICOS}
    return out


def mejor_sustituto(blosum: dict[str, dict[str, int]]) -> dict[str, str]:
    """Metodo `repo`: para cada aminoacido, el de mayor score excluyendose."""
    best = {}
    for a in CANONICOS:
        cand = [b for b in CANONICOS if b != a]
        best[a] = max(cand, key=lambda b: blosum[a][b])
    return best


def opciones_wert(blosum: dict[str, dict[str, int]]) -> dict[str, tuple]:
    """Metodo `wert`: sustitutos de score POSITIVO, con su softmax.

    Se excluye el self-match del conjunto de sustitutos (mutar a si mismo no
    es una variante), pero SI entra en el denominador del softmax, porque en
    `BLOSUMSIM` el denominador son todos los scores positivos de la fila,
    self-match incluido. De ahi que las probabilidades sean bajas y que el
    umbral `P_AUG = 0,2` deje casi todas las variantes etiquetadas como 0.
    """
    out = {}
    for a in CANONICOS:
        scores_pos = [blosum[a][b] for b in CANONICOS if blosum[a][b] > 0]
        denom = float(np.sum(np.exp(np.array(scores_pos, dtype=np.float64))))
        cand = [(b, blosum[a][b]) for b in CANONICOS
                if b != a and blosum[a][b] > 0]
        if not cand:
            out[a] = ((), (), denom)
            continue
        aas = tuple(b for b, _ in cand)
        probs = tuple(float(np.exp(s)) / denom for _, s in cand)
        out[a] = (aas, probs, denom)
    return out


# --------------------------------------------------------------------------- #
def variantes_repo(seq: str, best: dict[str, str]) -> list[tuple]:
    """Una variante por cada posicion, sustitucion determinista."""
    filas = []
    for i, aa in enumerate(seq):
        nuevo = best.get(aa)
        if nuevo is None or nuevo == aa:
            continue
        filas.append((seq[:i] + nuevo + seq[i + 1:], i, aa, nuevo, float("nan")))
    return filas


def variantes_wert(seq: str, opts: dict, n: int, rng: np.random.Generator,
                   ) -> list[tuple]:
    """`n` variantes, cada una mutando UNA posicion elegida al azar."""
    filas = []
    for _ in range(n):
        # A diferencia de BLOSUMSIM, la ULTIMA posicion tambien puede salir.
        i = int(rng.integers(0, len(seq)))
        aa = seq[i]
        aas, probs, _ = opts.get(aa, ((), (), 0.0))
        if not aas:
            continue
        k = int(rng.integers(0, len(aas)))
        filas.append((seq[:i] + aas[k] + seq[i + 1:], i, aa, aas[k], probs[k]))
    return filas


def main() -> int:
    setup_logging()
    ap = argparse.ArgumentParser()
    ap.add_argument("--fragments", required=True, type=Path,
                    help="directorio de fragmentos (centrado o deslizante)")
    ap.add_argument("--splits", required=True, type=Path,
                    help="splits.parquet: se aumenta SOLO la particion TRAIN")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--metodo", choices=("repo", "wert"), required=True)
    ap.add_argument("--n-variantes", type=int, default=25,
                    help="solo en --metodo wert (en 'repo' son las posiciones)")
    ap.add_argument("--p-aug", type=float, default=0.2,
                    help="solo en --metodo wert: umbral de etiqueta (0,2 en el paper)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--solo-positivos", action="store_true",
                    help=("aumenta solo las filas con label=1. CAMBIA LA PREVALENCIA "
                          "y hay que declararlo al reportar."))
    ap.add_argument("--format", choices=("parquet", "csv", "both"), default="parquet",
                    help=("formato de salida. Por omision solo Parquet, decision de Laura\n"
                          "del 27 nov: el CSV se pide explicitamente cuando hace falta\n"
                          "inspeccionar a ojo. Las tablas son de millones de filas y su\n"
                          "CSV puede ser dos ordenes de magnitud mayor."))
    ap.add_argument("--only", action="append", default=None)
    args = ap.parse_args()

    blosum = cargar_blosum62()
    best = mejor_sustituto(blosum)
    opts = opciones_wert(blosum)
    rng = np.random.default_rng(args.seed)

    # --- Particion. Sin ella el script no funciona, a proposito. -----------
    if not args.splits.exists():
        logging.error("no existe %s", args.splits)
        return 2
    S = pd.read_parquet(args.splits, columns=["familia", "fragmento", "split"])
    # `build_splits.py` escribe 'train'/'val'/'test' en minusculas; se compara
    # sin distinguir mayusculas para no depender de ese detalle, y se ABORTA si
    # no hay ninguna fila de TRAIN: un aumento vacio por no reconocer el valor
    # de la columna seria un fallo silencioso.
    etiqueta = S["split"].astype(str).str.strip().str.lower()
    train = S[etiqueta == "train"]
    if train.empty:
        logging.error("la particion no tiene ninguna fila de TRAIN. Valores de "
                      "'split' encontrados: %s",
                      sorted(etiqueta.unique().tolist())[:10])
        return 2
    claves_train = set(zip(train["familia"], train["fragmento"]))
    logging.info("particion: %d filas, TRAIN %d (%.1f %%), claves unicas %d",
                 len(S), len(train), 100 * len(train) / max(1, len(S)),
                 len(claves_train))
    del S, train, etiqueta

    nombres = ("fragments_ss.parquet", "fragments.parquet", "windows.parquet")
    ficheros: list[Path] = []
    for n in nombres:
        ficheros = sorted(args.fragments.rglob(n))
        if ficheros:
            logging.info("entrada: %s (%d ficheros)", n, len(ficheros))
            break
    if not ficheros:
        logging.error("ningun %s bajo %s", "/".join(nombres), args.fragments)
        return 2

    args.out.mkdir(parents=True, exist_ok=True)
    resultados = []
    gid = 0

    for f in ficheros:
        rel = f.relative_to(args.fragments).parent
        if args.only and str(rel) not in args.only:
            continue
        cols = ["especie", "clase", "familia", "accession", "fragmento", "label"]
        d = pd.read_parquet(f, columns=cols)
        n_in = len(d)

        # Solo TRAIN.
        en_train = [
            (fam, frag) in claves_train
            for fam, frag in zip(d["familia"].values, d["fragmento"].values)
        ]
        d = d[pd.Series(en_train, index=d.index)]
        n_train = len(d)
        if args.solo_positivos:
            d = d[d["label"] == 1]

        # Orden estable: el group_id no debe depender del orden del Parquet.
        d = d.sort_values(["familia", "accession", "fragmento"], kind="stable")

        destino = args.out / rel
        destino.mkdir(parents=True, exist_ok=True)
        salida = destino / "augmented.parquet"
        salida_csv = destino / "augmented.csv" if args.format in ("csv", "both") else None
        escritor = pq.ParquetWriter(salida, ESQUEMA, compression="zstd")
        cabecera = False
        buffer: list[list] = []
        n_var = n_pos_var = 0

        def volcar() -> None:
            nonlocal buffer, cabecera
            if not buffer:
                return
            df = pd.DataFrame(buffer, columns=[c.name for c in ESQUEMA])
            escritor.write_table(pa.Table.from_pandas(
                df, schema=ESQUEMA, preserve_index=False))
            if salida_csv is not None:
                df.to_csv(salida_csv, index=False,
                          mode="w" if not cabecera else "a", header=not cabecera)
                cabecera = True
            buffer = []

        for r in d.itertuples(index=False):
            gid += 1
            # Fila 0: el original. Entra SIEMPRE, para que el grupo este
            # completo y la relacion variante-original sea verificable.
            buffer.append([gid, 0, True, r.especie, r.clase, r.familia,
                           r.accession, r.fragmento, r.fragmento, int(r.label),
                           -1, "", "", float("nan")])
            if args.metodo == "repo":
                vs = variantes_repo(r.fragmento, best)
            else:
                vs = variantes_wert(r.fragmento, opts, args.n_variantes, rng)
            for k, (frag, pos, aa0, aa1, prob) in enumerate(vs, start=1):
                if args.metodo == "repo":
                    lab = int(r.label)                    # etiqueta heredada
                else:
                    lab = 1 if prob >= args.p_aug else 0  # etiqueta del softmax
                n_var += 1
                n_pos_var += lab
                buffer.append([gid, k, False, r.especie, r.clase, r.familia,
                               r.accession, frag, r.fragmento, lab,
                               pos, aa0, aa1, prob])
            if len(buffer) >= FLUSH_FILAS:
                volcar()

        volcar()
        escritor.close()
        total = len(d) + n_var
        info = {
            "familia": str(rel),
            "filas_de_entrada": n_in,
            "filas_en_train": n_train,
            "originales_aumentados": int(len(d)),
            "variantes_generadas": n_var,
            "variantes_etiquetadas_1": int(n_pos_var),
            "variantes_etiquetadas_0": int(n_var - n_pos_var),
            "filas_de_salida": total,
            "variantes_por_original": round(n_var / max(1, len(d)), 3),
            "salida": str(salida),
            "sha256": sha256(salida),
            "bytes": salida.stat().st_size,
        }
        if salida_csv is not None and salida_csv.exists():
            info["salida_csv"] = str(salida_csv)
            info["bytes_csv"] = salida_csv.stat().st_size
        resultados.append(info)
        logging.info("%s: TRAIN %d -> %d originales + %d variantes = %d filas "
                     "(%.2f var/orig)", rel, n_train, len(d), n_var, total,
                     info["variantes_por_original"])

    tot_o = sum(r["originales_aumentados"] for r in resultados)
    tot_v = sum(r["variantes_generadas"] for r in resultados)
    manifiesto = {
        "generado_por": "data_pipeline/scripts/data_augmentation/augment_blosum62.py",
        "fecha_utc": datetime.now(timezone.utc).isoformat(),
        "commit_git": commit_git(),
        "fragmentos": str(args.fragments),
        "particion": str(args.splits),
        "particion_sha256": sha256(args.splits),
        "metodo": args.metodo,
        "solo_train": True,
        "solo_positivos": bool(args.solo_positivos),
        "semilla": args.seed if args.metodo == "wert" else None,
        "n_variantes_pedidas": args.n_variantes if args.metodo == "wert" else "una por posicion",
        "p_aug": args.p_aug if args.metodo == "wert" else None,
        "etiqueta": ("heredada del original" if args.metodo == "repo"
                     else "decidida por el softmax de BLOSUM62 frente a p_aug"),
        "defectos_de_BLOSUMSIM_no_reproducidos": [
            "dict(map(reversed,...)) que perdia aminoacidos con score repetido",
            "listprob[1:] que descartaba el primer score en orden de columna",
            "C, G y P sin ninguna opcion de sustitucion",
            "introduccion de B y Z, que no son aminoacidos",
            "randint(0, len-1), que nunca mutaba la ultima posicion",
        ],
        "indice_de_grupo": {
            "group_id": "el original y todas sus variantes comparten valor",
            "variante_id": "0 = original, 1..N = variantes",
            "nota": ("group_id es la unidad de independencia: las filas de un "
                     "grupo NO son observaciones independientes y ninguna "
                     "particion posterior debe separarlas"),
        },
        "totales": {
            "originales_aumentados": tot_o,
            "variantes_generadas": tot_v,
            "filas_de_salida": tot_o + tot_v,
            "variantes_por_original": round(tot_v / max(1, tot_o), 3),
        },
        "por_familia": resultados,
    }
    (args.out / "manifest.json").write_text(
        json.dumps(manifiesto, indent=2, ensure_ascii=False), encoding="utf-8")
    logging.info("TOTAL %d originales + %d variantes = %d filas",
                 tot_o, tot_v, tot_o + tot_v)
    logging.info("manifiesto: %s", args.out / "manifest.json")
    logging.info("DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
