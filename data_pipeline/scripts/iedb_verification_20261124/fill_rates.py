#!/usr/bin/env python3
"""% de relleno y cardinalidad de cada columna, sobre dos familias representativas."""
import csv, collections
csv.field_size_limit(10**9)
ROOT = "/tmp/claude-7259/-data-nap-lperez-nn/71faedc6-a6ec-485d-aa35-95634e1242e6/scratchpad/data_raw_extract/data_raw"
FILES = [("H2-K mhc", ROOT + "/mouse/mhc-I/H2-K/mhc_export_full.csv"),
         ("HLA-A mhc", ROOT + "/human/mhc-I/HLA-A/mhc_export_full.csv")]

for label, path in FILES:
    filled = collections.Counter()
    uniq = collections.defaultdict(set)
    n = 0
    for r in csv.DictReader(open(path, newline="", encoding="utf-8")):
        n += 1
        for k, v in r.items():
            v = (v or "").strip()
            if v:
                filled[k] += 1
                if len(uniq[k]) < 5000:
                    uniq[k].add(v)
    print("\n########## %s  (%d filas) ##########" % (label, n))
    rows = sorted(filled.items(), key=lambda x: -x[1])
    print("%-46s %7s %9s" % ("columna", "relleno", "distintos"))
    for k, c in rows:
        nu = len(uniq[k])
        print("%-46s %6.1f%% %9s" % (k, 100 * c / n, ("%d+" % nu) if nu >= 5000 else nu))
    empty = [k for k in uniq if filled[k] == 0]
    allk = set()
    for r in csv.DictReader(open(path, newline="", encoding="utf-8")):
        allk = set(r.keys()); break
    never = sorted(allk - set(filled))
    print("\n--- SIEMPRE VACIAS (%d de %d) ---" % (len(never), len(allk)))
    for k in never:
        print("   ", k)
