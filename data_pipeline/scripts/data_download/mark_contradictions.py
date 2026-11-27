#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
mark_contradictions.py — Marca como columna las filas con etiqueta contradictoria.

PARA QUE
--------
El brazo experimental "sin contradicciones" debe ser un **filtro sobre una
columna**, no un recalculo. Este script anade esa columna a los ficheros de
fragmentos, in situ, mas los contadores que permiten diagnosticar cada caso.

QUE ES UNA CONTRADICCION AQUI
-----------------------------
Una misma secuencia de fragmento que aparece como **positiva en una familia y
como senuelo en otra**. Medido sobre w21: 63.900 secuencias, el 2,891 % de las
unicas, que implican 221.546 filas (6,647 %). Dentro de una misma familia no
hay ninguna, porque `build_fragments.py` resuelve la colision dando la
preferencia al positivo.

> **No es ruido de etiqueta, es el caracter positive-unlabeled.** Que un tramo
> sea epitopo de HLA-B y no este anotado para HLA-A no significa que HLA-A no lo
> presente: significa que nadie lo ha medido. Entrenando sin el alelo en la
> entrada, el modelo recibe el mismo vector con etiquetas opuestas. Con la
> pseudosecuencia del alelo en la entrada esas filas dejan de ser
> contradictorias y pasan a ser lo que el modelo debe aprender.

COLUMNAS QUE ANADE
------------------
  `contradictorio`        la secuencia aparece con ambas etiquetas en el conjunto
  `contradictorio_ss`     idem, pero la clave es (secuencia, estructura Q3).
                          Resuelve el 4,3 % de los casos, porque el mismo
                          fragmento en proteinas distintas puede tener
                          estructura distinta.
  `n_familias_positivo`   en cuantas familias es positivo
  `n_familias_senuelo`    en cuantas es senuelo
  `n_alelos_positivo`     en cuantos alelos es positivo. No es contradiccion:
                          es promiscuidad, y el 33,76 % de los positivos la
                          tiene, uno de ellos en 97 alelos. Un modelo sin alelo
                          en la entrada no puede representarla.

USO
---
    P=/home/nap/miniconda3/envs/nap_env/bin/python
    $P -u data_pipeline/scripts/data_download/mark_contradictions.py \\
        --fragments data/fragments_w21_ss
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fragments", required=True, type=Path)
    ap.add_argument("--format", choices=("parquet", "csv", "both"), default="parquet",
                    help=("formato de salida. Por omision solo Parquet, decision de Laura\n"
                          "del 27 nov: el CSV se pide explicitamente cuando hace falta\n"
                          "inspeccionar a ojo. Las tablas son de millones de filas y su\n"
                          "CSV puede ser dos ordenes de magnitud mayor."))
    args = ap.parse_args()

    repo = Path(__file__).resolve().parents[3]
    ficheros = sorted(args.fragments.rglob("fragments_ss.parquet"))
    if not ficheros:
        print(f"ERROR: ningun fragments_ss.parquet bajo {args.fragments}",
              file=sys.stderr)
        return 2

    # --- primera pasada: agregados globales por secuencia ---
    partes = []
    for f in ficheros:
        partes.append(pd.read_parquet(
            f, columns=["fragmento", "secondary_structure", "label",
                        "familia", "alelo"]))
    D = pd.concat(partes, ignore_index=True)
    del partes
    print(f"filas {len(D):,} | secuencias unicas {D.fragmento.nunique():,}")

    etiq = D.groupby("fragmento").label.nunique()
    contra = set(etiq[etiq > 1].index)

    D["par"] = D.fragmento + "|" + D.secondary_structure.fillna("")
    hay_ss = D.secondary_structure.notna()
    etiq_ss = D[hay_ss].groupby("par").label.nunique()
    contra_ss = set(etiq_ss[etiq_ss > 1].index)

    pos = D[D.label == 1]
    neg = D[D.label == 0]
    nfp = pos.groupby("fragmento").familia.nunique()
    nfn = neg.groupby("fragmento").familia.nunique()
    nap = pos.groupby("fragmento").alelo.nunique()
    print(f"  contradictorias por secuencia        : {len(contra):,}")
    print(f"  contradictorias por secuencia+Q3     : {len(contra_ss):,}")
    print(f"  resueltas al anadir la estructura    : {len(contra)-len(contra_ss):,}")
    del D, pos, neg

    # --- segunda pasada: escribir las columnas ---
    tot = marcadas = marcadas_ss = 0
    por_familia: dict[str, dict] = {}
    for f in ficheros:
        d = pd.read_parquet(f)
        d["contradictorio"] = d.fragmento.isin(contra)
        par = d.fragmento + "|" + d.secondary_structure.fillna("")
        d["contradictorio_ss"] = par.isin(contra_ss)
        d["n_familias_positivo"] = d.fragmento.map(nfp).fillna(0).astype("int32")
        d["n_familias_senuelo"] = d.fragmento.map(nfn).fillna(0).astype("int32")
        d["n_alelos_positivo"] = d.fragmento.map(nap).fillna(0).astype("int32")
        if args.format in ("parquet", "both"):
            d.to_parquet(f, index=False, compression="zstd")
        if args.format in ("csv", "both"):
            d.to_csv(f.with_suffix(".csv"), index=False)
        fam = str(f.relative_to(args.fragments).parent)
        por_familia[fam] = {
            "filas": len(d),
            "contradictorias": int(d.contradictorio.sum()),
            "contradictorias_ss": int(d.contradictorio_ss.sum()),
        }
        tot += len(d)
        marcadas += int(d.contradictorio.sum())
        marcadas_ss += int(d.contradictorio_ss.sum())
        print(f"[{fam:22s}] {len(d):9,} filas | contradictorias "
              f"{int(d.contradictorio.sum()):8,} "
              f"({100*d.contradictorio.mean():5.2f} %)")

    man = {
        "generado_por": "data_pipeline/scripts/data_download/mark_contradictions.py",
        "fecha_utc": datetime.now(timezone.utc).isoformat(),
        "commit_git": _git_commit(repo),
        "fragmentos": str(args.fragments),
        "definicion": ("una secuencia de fragmento que aparece como positiva en una "
                       "familia y como senuelo en otra; dentro de una misma familia no "
                       "hay ninguna, porque build_fragments.py da preferencia al "
                       "positivo"),
        "filas": tot,
        "secuencias_contradictorias": len(contra),
        "secuencias_contradictorias_ss": len(contra_ss),
        "filas_contradictorias": marcadas,
        "filas_contradictorias_pct": round(100.0 * marcadas / tot, 4) if tot else 0,
        "filas_contradictorias_ss": marcadas_ss,
        "filas_contradictorias_ss_pct": (round(100.0 * marcadas_ss / tot, 4)
                                         if tot else 0),
        "por_familia": por_familia,
    }
    p = args.fragments / "manifest_contradicciones.json"
    p.write_text(json.dumps(man, indent=2, ensure_ascii=False))
    print(f"\nTOTAL {marcadas:,} de {tot:,} filas contradictorias "
          f"({100*marcadas/tot:.3f} %) | con Q3 {marcadas_ss:,} "
          f"({100*marcadas_ss/tot:.3f} %)")
    print(f"Manifiesto: {p}\nDONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
