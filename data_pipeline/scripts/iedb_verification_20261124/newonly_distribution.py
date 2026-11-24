#!/usr/bin/env python3
"""Las filas que solo estan en la re-descarga, son altas (crecimiento real
de IEDB) o estan repartidas por todo el rango (el paginado viejo se las
salto)? Es la prueba que distingue 'IEDB crecio' de 'la descarga quedo
incompleta'.
"""
import csv, os, sys
csv.field_size_limit(10**9)
OLD = os.environ["OLD_RAW"]; NEW = os.environ["NEW_RAW"]

def ids(path):
    if not os.path.exists(path) or not os.path.getsize(path):
        return set()
    out = set()
    for r in csv.DictReader(open(path, newline="", encoding="utf-8")):
        v = (r.get("assay_id") or "").strip()
        if v.isdigit():
            out.add(int(v))
    return out

print("%-20s %-6s %10s %10s %10s %7s" % (
    "familia", "export", "max_viejo", "nuevos<=max", "nuevos>max", "%inter"))
for fam in sys.argv[1:]:
    for mode in ("mhc", "tcell"):
        fn = "%s_export_full.csv" % mode
        o = ids(os.path.join(OLD, fam, fn)); n = ids(os.path.join(NEW, fam, fn))
        if not o or not n:
            continue
        only = n - o
        if not only:
            continue
        mx = max(o)
        inter = sum(1 for i in only if i <= mx)   # intercalados: el viejo los perdio
        after = len(only) - inter                 # posteriores: crecimiento real
        print("%-20s %-6s %10d %10d %10d %6.1f%%" % (
            fam, mode, mx, inter, after, 100.0 * inter / len(only)))
