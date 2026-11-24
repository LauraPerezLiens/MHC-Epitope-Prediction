#!/usr/bin/env python3
"""Verificacion a tres bandas de una descarga de IEDB.

Responde a: que datos trae esta descarga frente a (1) el snapshot
historico que alimento D1 y (2) el dataset con el que Carlos Wert
entreno la red publicada en Sci Rep 2021.

Las dos comparaciones usan claves distintas, y eso no es un detalle:

  nuevo vs viejo   -> por `assay_id`, la clave unica de IEDB. Es la unica
                      forma de distinguir "IEDB ha crecido" de "el
                      paginado antiguo perdio o duplico filas".

  nuevo vs Wert    -> por SECUENCIA DE PEPTIDO. El CSV de Wert viene de
                      un export distinto de IEDB, con otra cabecera y sin
                      assay_id utilizable, asi que el peptido es la unica
                      clave comun. Implica que la comparacion es a nivel
                      de peptido, no de ensayo.

El lado Wert replica `peptides_extraction.py` del ZIP, incluido su
criterio real `Assay.4 != "Negative"` (que NO es lo mismo que
`== "Positive"`: admite filas con el campo vacio; ver hallazgo E).

Uso:
    python verify_download.py --new DIR --old DIR [--wert CSV] \
        [--report reports/audits/...md] [--json ...json]
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import sys
from pathlib import Path

csv.field_size_limit(10 ** 9)

WERT_DEFAULT = Path(
    "/data/nap/lperez_nn/reference/neoantigenpred_zip/neoantigenpred-master"
    "/media/downloadable_content/H2Kb_data.csv"
)
EXPORTS = ("mhc", "tcell")


def read_column(path: Path, candidates: tuple[str, ...]) -> list[str]:
    """Lee la primera columna disponible de `candidates`. Lista, no set:
    conservar las repeticiones es lo que permite contar duplicados."""
    if not path.exists() or path.stat().st_size == 0:
        return []
    values = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        column = next((c for c in candidates if c in (reader.fieldnames or [])), None)
        if column is None:
            return []
        for row in reader:
            value = (row.get(column) or "").strip()
            if value:
                values.append(value)
    return values


def families(root: Path) -> list[str]:
    return sorted(
        "/".join(p.parts[-3:])
        for p in root.glob("*/*/*")
        if p.is_dir()
    )


def compare_assays(new_root: Path, old_root: Path) -> tuple[list[dict], dict]:
    """nuevo vs viejo por assay_id, por familia y export."""
    rows = []
    totals = collections.Counter()
    seen = sorted(set(families(new_root)) | set(families(old_root)))

    for family in seen:
        for export in EXPORTS:
            name = "%s_export_full.csv" % export
            old_list = read_column(old_root / family / name, ("assay_id",))
            new_list = read_column(new_root / family / name, ("assay_id",))
            if not old_list and not new_list:
                continue
            old_set, new_set = set(old_list), set(new_list)

            # Huecos intercalados: un paginado que pierde paginas deja
            # ausencias repartidas por todo el rango. Si todo lo nuevo
            # esta por encima del maximo viejo, es crecimiento de IEDB.
            only_new = new_set - old_set
            interleaved = 0
            if old_set and only_new:
                try:
                    old_max = max(int(v) for v in old_set)
                    interleaved = sum(1 for v in only_new if int(v) < old_max)
                except ValueError:
                    interleaved = -1  # assay_id no numerico

            record = {
                "familia": family,
                "export": export,
                "viejo": len(old_list),
                "nuevo": len(new_list),
                "duplicados_en_viejo": len(old_list) - len(old_set),
                "duplicados_en_nuevo": len(new_list) - len(new_set),
                "solo_viejo": len(old_set - new_set),
                "solo_nuevo": len(only_new),
                "solo_nuevo_intercalado": interleaved,
                "comun": len(old_set & new_set),
            }
            rows.append(record)
            for key, value in record.items():
                if isinstance(value, int):
                    totals[key] += value
    return rows, dict(totals)


def wert_peptides(path: Path) -> dict:
    """Replica peptides_extraction.py sobre el CSV de dos cabeceras."""
    raw = list(csv.reader(path.open(newline="", encoding="utf-8", errors="replace")))
    header, data = raw[3], raw[5:]

    # El export de Wert repite nombres de columna; pandas los desambigua
    # con sufijos .1 .2 ... y el script original usa esos nombres.
    seen: collections.Counter = collections.Counter()
    names = []
    for column in header:
        names.append(column if seen[column] == 0 else "%s.%d" % (column, seen[column]))
        seen[column] += 1

    i_pep = names.index("Epitope.2")
    i_assay = names.index("Assay.4")
    i_acc = names.index("Epitope.8")
    cell = lambda row, i: (row[i].strip() if i < len(row) else "")

    every, positive, with_accession = set(), set(), set()
    for row in data:
        peptide = cell(row, i_pep)
        if not peptide:
            continue
        every.add(peptide)
        # Criterio REAL de Wert: distinto de "Negative", no igual a
        # "Positive". Cuela filas con el campo vacio (hallazgo E).
        if cell(row, i_assay) != "Negative":
            positive.add(peptide)
            if cell(row, i_acc):
                with_accession.add(peptide)
    return {
        "todos": every,
        "positivos": positive,
        "negativos": every - positive,
        "positivos_con_accession": with_accession,
    }


def compare_wert(new_root: Path, wert_csv: Path, family: str) -> dict:
    wert = wert_peptides(wert_csv)
    ours: set[str] = set()
    per_export = {}
    for export in EXPORTS:
        peptides = set(read_column(
            new_root / family / ("%s_export_full.csv" % export),
            ("epitope__name", "epitope__reference_name"),
        ))
        per_export[export] = len(peptides)
        ours |= peptides

    recovered = wert["positivos"] & ours
    return {
        "familia_comparada": family,
        "wert_peptidos_unicos": len(wert["todos"]),
        "wert_positivos": len(wert["positivos"]),
        "wert_positivos_con_accession": len(wert["positivos_con_accession"]),
        "wert_negativos_explicitos": len(wert["negativos"]),
        "nuestros_peptidos_unicos": len(ours),
        "nuestros_por_export": per_export,
        "positivos_de_wert_presentes": len(recovered),
        "positivos_de_wert_presentes_pct": round(
            100.0 * len(recovered) / max(len(wert["positivos"]), 1), 2),
        "positivos_de_wert_ausentes": len(wert["positivos"] - ours),
        "nuestros_que_wert_no_tiene": len(ours - wert["todos"]),
        "negativos_de_wert_presentes": len(wert["negativos"] & ours),
    }


def render_report(assay_rows, assay_totals, wert, args) -> str:
    out = ["# Verificación de descarga IEDB", ""]
    out.append("- Descarga nueva: `%s`" % args.new)
    out.append("- Snapshot histórico: `%s`" % args.old)
    if wert:
        out.append("- Dataset de Wert2021: `%s`" % args.wert)
    out.append("")

    out += ["## 1. Nuevo frente al histórico, por `assay_id`", "",
            "| Familia | Export | Viejo | Nuevo | Dup. viejo | Solo viejo | Solo nuevo | Intercalado | Común |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in assay_rows:
        out.append("| %s | %s | %d | %d | %d | %d | %d | %d | %d |" % (
            r["familia"], r["export"], r["viejo"], r["nuevo"],
            r["duplicados_en_viejo"], r["solo_viejo"], r["solo_nuevo"],
            r["solo_nuevo_intercalado"], r["comun"]))
    t = assay_totals
    out += ["", "**Totales.** Viejo %d filas (%d duplicadas), nuevo %d. "
            "Solo en el viejo %d, solo en el nuevo %d (%d intercaladas), común %d."
            % (t.get("viejo", 0), t.get("duplicados_en_viejo", 0), t.get("nuevo", 0),
               t.get("solo_viejo", 0), t.get("solo_nuevo", 0),
               t.get("solo_nuevo_intercalado", 0), t.get("comun", 0)), ""]
    out += ["> Cómo leerlo: `Dup. viejo` > 0 indicaría que el paginado por "
            "`offset` sin `order` repetía filas. `Intercalado` cuenta los "
            "`assay_id` nuevos **por debajo** del máximo del snapshot viejo: "
            "esos sí serían filas que el paginado antiguo se saltó. Si "
            "`Intercalado` ≈ 0, lo nuevo es crecimiento real de IEDB.", ""]

    if wert:
        out += ["## 2. Nuestro %s frente al H-2Kb de Wert2021, por péptido"
                % wert["familia_comparada"], "",
                "| Magnitud | Valor |", "|---|---:|"]
        for key, value in wert.items():
            if key in ("familia_comparada", "nuestros_por_export"):
                continue
            out.append("| %s | %s |" % (key.replace("_", " "), value))
        out += ["", "> La clave de comparación es la **secuencia de péptido**, "
                "no el ensayo: el CSV de Wert procede de otro export de IEDB. "
                "`negativos de wert presentes` debe ser 0 en el perfil "
                "`legacy` (no descarga negativos) y >0 en el perfil `full`.", ""]
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--new", required=True, type=Path)
    parser.add_argument("--old", required=True, type=Path)
    parser.add_argument("--wert", type=Path, default=WERT_DEFAULT)
    parser.add_argument("--wert-family", default="mouse/mhc-I/H2-K")
    parser.add_argument("--no-wert", action="store_true")
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()

    assay_rows, assay_totals = compare_assays(args.new, args.old)
    wert = None
    if not args.no_wert:
        if args.wert.exists():
            wert = compare_wert(args.new, args.wert, args.wert_family)
        else:
            print("AVISO: no existe %s; omito la comparación con Wert" % args.wert,
                  file=sys.stderr)

    report = render_report(assay_rows, assay_totals, wert, args)
    print(report)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(report + "\n", encoding="utf-8")
        print("\n-> informe en %s" % args.report, file=sys.stderr)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(
            {"por_familia": assay_rows, "totales": assay_totals, "wert": wert},
            indent=2, ensure_ascii=False), encoding="utf-8")
        print("-> detalle en %s" % args.json, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
