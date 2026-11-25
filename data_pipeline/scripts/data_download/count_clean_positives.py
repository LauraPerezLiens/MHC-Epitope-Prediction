#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
count_clean_positives.py — Cuantos positivos quedan tras limpiar de verdad.

Aplica un embudo de filtros acumulativos sobre los Parquet de
`data_raw_full_*_clean` y, al final, desglosa los positivos que sobreviven por
origen del epitopo (propio / otro organismo / sin anotar) y por fiabilidad del
alelo (natural / mutante puntual / serotipo de baja resolucion).

EL EMBUDO
---------
    1. Todas las filas
    2. + ligando eluido            `assay__response_measured == 'ligand presentation'`
    3. + sin modificacion quimica  `epitope__modifications` vacio
    4. + peptido canonico          solo los 20 aminoacidos estandar
    5. + positivo                  `assay__qualitative_measurement` empieza por 'Positive'

El paso 2 solo existe en `mhc_export`: en `tcell_export` hay CERO filas de
`ligand presentation`, porque ahi se mide inmunogenicidad (IFNg release,
citotoxicidad, proliferacion), no presentacion. Para `tcell` el embudo se
reporta sin ese paso, y se dice.

POR QUE ESTOS FILTROS
---------------------
  * **Ligando eluido** es el objetivo decidido en §0.7.4: lo que el modelo
    predice es "este peptido fue eluido de este MHC". Mezclar afinidad e
    inmunogenicidad en la misma etiqueta es el hallazgo Q.
  * **Sin modificacion quimica**: un peptido oxidado o cisteinilado no es el
    mismo objeto quimico, y la secuencia de aminoacidos no captura la
    diferencia. Entra como si fuera el peptido sin modificar.
  * **Peptido canonico**: hay entradas que no son peptidos simples, del tipo
    `GPPGPAGPAGERGEQG + HYL(P3)`, que ninguna representacion de secuencia
    puede tratar.
  * **Alelo mutante**: un `HLA-A*02:01 K66A mutant` es una molecula construida
    en laboratorio para estudiar el surco. Su pseudosecuencia de referencia es
    la del alelo silvestre, de modo que entrenar con esas filas asigna al
    alelo silvestre el comportamiento de una proteina que no existe en ninguna
    persona.
  * **Serotipo de baja resolucion** (`HLA-A2`, `H2-k class I`): no identifica
    un alelo, sino un grupo serologico con motivos de union distintos.

USO
---
    P=/home/nap/miniconda3/envs/nap_env/bin/python
    $P -u data_pipeline/scripts/data_processing/count_clean_positives.py \
        --clean data/data_raw_full_20261124_clean
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd

CANONICAL = set("ACDEFGHIKLMNPQRSTVWY")
LIGAND_PRESENTATION = "ligand presentation"

# Especie propia de cada rama del arbol de directorios.
SELF_SPECIES = {"human": "Homo sapiens", "mouse": "Mus musculus"}
# Valores de `epitope__species` que no identifican un organismo.
UNANNOTATED = {"unidentified", "unidentified organism", "synthetic construct"}

# Serotipos de baja resolucion: no llevan separador de alelo (`*` o un sufijo
# de haplotipo murino de letra minuscula), o se declaran como clase serologica.
_RE_MUTANT = re.compile(r"\bmutant\b", re.IGNORECASE)
_RE_SEROTYPE = re.compile(
    r"(^HLA-[A-Z]+[0-9]+$)"            # HLA-A2, HLA-B27, HLA-DR4
    r"|(class\s+I{1,2}$)"              # H2-k class I
    r"|(^H2-[A-Z]$)",                  # H2-K sin haplotipo
    re.IGNORECASE,
)


def allele_class(name: str | float) -> str:
    if not isinstance(name, str) or not name.strip():
        return "sin_alelo"
    if _RE_MUTANT.search(name):
        return "mutante"
    if _RE_SEROTYPE.search(name.strip()):
        return "serotipo"
    return "natural"


def origin_class(species: str | float, self_species: str) -> str:
    if not isinstance(species, str) or not species.strip():
        return "sin_anotar"
    s = species.strip()
    if s.lower() in UNANNOTATED:
        return "sin_anotar"
    return "propio" if self_species.lower() in s.lower() else "otro"


def is_canonical(pep: str | float) -> bool:
    return isinstance(pep, str) and bool(pep) and set(pep) <= CANONICAL


def funnel(df: pd.DataFrame, kind: str, self_species: str) -> dict:
    out: dict = {}
    n = len(df)
    out["1_todas"] = n

    if kind == "mhc":
        df = df[df["assay__response_measured"] == LIGAND_PRESENTATION]
        out["2_ligando_eluido"] = len(df)
    else:
        # En tcell no existe: se deja constancia explicita del cero.
        out["2_ligando_eluido"] = int(
            (df["assay__response_measured"] == LIGAND_PRESENTATION).sum()
        )

    df = df[df["epitope__modifications"].isna()]
    out["3_sin_modificacion"] = len(df)

    df = df[df["epitope__name"].map(is_canonical)]
    out["4_peptido_canonico"] = len(df)

    df = df[df["assay__qualitative_measurement"].fillna("").str.startswith("Positive")]
    out["5_positivos"] = len(df)

    org = df["epitope__species"].map(lambda s: origin_class(s, self_species))
    out["origen"] = {k: int(v) for k, v in org.value_counts().items()}
    al = df["mhc_restriction__name"].map(allele_class)
    out["alelo"] = {k: int(v) for k, v in al.value_counts().items()}
    # Positivos que sobreviven a TODO: propios o no, pero con alelo natural.
    out["positivos_alelo_natural"] = int((al == "natural").sum())
    out["positivos_propios_alelo_natural"] = int(((al == "natural") & (org == "propio")).sum())
    out["positivos_otros_alelo_natural"] = int(((al == "natural") & (org == "otro")).sum())
    out["peptidos_unicos_tras_filtrar"] = int(df["epitope__name"].nunique())
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean", required=True, type=Path,
                    help="directorio de los Parquet limpios (--columns core)")
    ap.add_argument("--json-out", type=Path, default=None,
                    help="ruta donde volcar el resultado en JSON")
    ap.add_argument("--kind", choices=("mhc", "tcell", "ambos"), default="mhc",
                    help=("que export analizar. Por omision solo 'mhc': es donde estan los "
                          "ligandos eluidos, que es el objetivo decidido en §0.7.4. En "
                          "'tcell' hay CERO filas de ligand presentation."))
    args = ap.parse_args()

    cols = [
        "assay__response_measured", "epitope__modifications", "epitope__name",
        "assay__qualitative_measurement", "epitope__species", "mhc_restriction__name",
    ]
    rows: list[dict] = []
    for path in sorted(args.clean.rglob("*_slim.parquet")):
        rel = path.relative_to(args.clean)
        species = rel.parts[0]
        family = rel.parts[2] if len(rel.parts) > 3 else rel.parts[-2]
        kind = "tcell" if "tcell" in path.name else "mhc"
        if args.kind != "ambos" and kind != args.kind:
            continue
        df = pd.read_parquet(path, columns=cols)
        r = funnel(df, kind, SELF_SPECIES[species])
        r.update({"familia": f"{species}/{family}", "tipo": kind})
        rows.append(r)

    def show(kind: str) -> None:
        sel = [r for r in rows if r["tipo"] == kind]
        if not sel:
            return
        print(f"\n{'='*118}\n{kind}_export — embudo de filtrado\n{'='*118}")
        hdr = (f"{'familia':22s} {'todas':>10s} {'eluido':>10s} {'sin modif':>10s} "
               f"{'canonico':>10s} {'POSITIVOS':>11s} {'propio':>9s} {'otro':>9s} "
               f"{'sin anot':>9s} {'nat':>9s} {'mutante':>8s} {'serot':>7s}")
        print(hdr)
        tot: dict = {}
        for r in sel + [None]:
            if r is None:
                r = tot
                r["familia"] = "TOTAL"
            else:
                for k, v in r.items():
                    if isinstance(v, int):
                        tot[k] = tot.get(k, 0) + v
                    elif isinstance(v, dict):
                        d = tot.setdefault(k, {})
                        for kk, vv in v.items():
                            d[kk] = d.get(kk, 0) + vv
            o, a = r.get("origen", {}), r.get("alelo", {})
            print(
                f"{r['familia']:22s} {r['1_todas']:10,} {r['2_ligando_eluido']:10,} "
                f"{r['3_sin_modificacion']:10,} {r['4_peptido_canonico']:10,} "
                f"{r['5_positivos']:11,} {o.get('propio',0):9,} {o.get('otro',0):9,} "
                f"{o.get('sin_anotar',0):9,} {a.get('natural',0):9,} "
                f"{a.get('mutante',0):8,} {a.get('serotipo',0):7,}"
            )
        rows.append({**tot, "familia": "TOTAL", "tipo": kind})

    for k in (("mhc", "tcell") if args.kind == "ambos" else (args.kind,)):
        show(k)

    if args.json_out:
        args.json_out.write_text(json.dumps(rows, indent=2, ensure_ascii=False))
        print(f"\nJSON: {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
