#!/usr/bin/env python3
"""Compara data_raw (snapshot del 10-nov, paginado por offset SIN order)
contra data_raw_20261124 (keyset sobre assay_id).

La comparacion se hace sobre assay_id, que es la clave unica de IEDB:
asi se distingue 'filas nuevas en IEDB' de 'filas que el paginado antiguo
se salto o duplico'.
"""
import csv, glob, os, sys, json
csv.field_size_limit(10**9)

OLD = os.environ.get("OLD_RAW", "/data/nap/lperez_nn/data/data_raw_historico_extract/data_raw")
NEW = "/data/nap/lperez_nn/data/data_raw_20261124"


def ids(path):
    """Devuelve (lista de assay_id, set de assay_id) de un CSV de export."""
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return [], set()
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            v = (r.get("assay_id") or "").strip()
            if v:
                out.append(v)
    return out, set(out)


fams = sorted("/".join(p.split("/")[-3:]) for p in glob.glob(OLD + "/*/*/*"))
# FAMS: lista separada por comas para restringir la comparacion a familias
# ya descargadas (la re-descarga va por tandas).
_only = [f.strip() for f in os.environ.get("FAMS", "").split(",") if f.strip()]
if _only:
    fams = [f for f in fams if f in _only]
print("%-22s %-6s %9s %9s %7s %9s %9s %9s" % (
    "familia", "export", "viejo", "nuevo", "dup_v", "solo_viejo", "solo_nuevo", "comun"))
tot = {k: 0 for k in ("old", "new", "dup", "only_old", "only_new", "common")}
rows_out = []

for fam in fams:
    for mode in ("mhc", "tcell"):
        fn = "%s_export_full.csv" % mode
        lo, so = ids(os.path.join(OLD, fam, fn))
        ln, sn = ids(os.path.join(NEW, fam, fn))
        if not ln and not lo:
            continue
        dup = len(lo) - len(so)
        only_old = len(so - sn)
        only_new = len(sn - so)
        common = len(so & sn)
        print("%-22s %-6s %9d %9d %7d %9d %9d %9d" % (
            fam, mode, len(lo), len(ln), dup, only_old, only_new, common))
        tot["old"] += len(lo); tot["new"] += len(ln); tot["dup"] += dup
        tot["only_old"] += only_old; tot["only_new"] += only_new; tot["common"] += common
        rows_out.append(dict(familia=fam, export=mode, viejo=len(lo), nuevo=len(ln),
                             duplicados_en_viejo=dup, solo_viejo=only_old,
                             solo_nuevo=only_new, comun=common))

print("\n=== TOTALES ===")
print("filas en data_raw (10-nov)        : %d" % tot["old"])
print("  de las cuales DUPLICADAS        : %d" % tot["dup"])
print("filas en data_raw_20261124        : %d" % tot["new"])
print("assay_id solo en el viejo         : %d   <- se han retirado de IEDB, o el keyset los pierde" % tot["only_old"])
print("assay_id solo en el nuevo         : %d   <- nuevos en IEDB, o el offset antiguo se los salto" % tot["only_new"])
print("assay_id en comun                 : %d" % tot["common"])

OUTJ = os.environ.get("OUT_JSON", "/data/nap/lperez_nn/reports/audits/iedb_comparacion_descargas_20261124.json")
json.dump(rows_out, open(OUTJ, "w"), indent=2)
print("\n-> detalle en %s" % OUTJ)
