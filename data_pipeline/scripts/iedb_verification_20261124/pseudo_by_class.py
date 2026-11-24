#!/usr/bin/env python3
"""Cobertura de pseudosecuencia desglosada por clase y familia."""
import csv, collections, glob, os
csv.field_size_limit(10**9)
PSEUDO = "/data/nap/lperez_nn/reference/pseudosequences/pseudosequences.netmhcpan.34aa.csv"
ROOT = os.environ.get("RAW_ROOT", "/data/nap/lperez_nn/data/data_raw_20261124")
pseudo = {r["allele"]: r["pseudosequence"] for r in csv.DictReader(open(PSEUDO))}


def norm(a):
    c = [a, a.replace("*", ""), a.replace("*", "").replace(":", "")]
    c += [x.replace("H2-", "H-2-") for x in list(c)]
    c += [x.replace("H-2-", "H2-") for x in list(c)]
    for x in c:
        if x in pseudo:
            return x
    return None


print("%-24s %10s %10s %7s  %s" % ("familia", "filas", "cubiertas", "%", "alelos sin pseudosec."))
agg = collections.Counter()
for fam in sorted(glob.glob(ROOT + "/*/*/*")):
    name = "/".join(fam.split("/")[-3:])
    tot = hit = 0
    miss = collections.Counter()
    for fn in ("mhc_export_full.csv", "tcell_export_full.csv"):
        p = os.path.join(fam, fn)
        if not os.path.exists(p) or os.path.getsize(p) == 0:
            continue
        for r in csv.DictReader(open(p, newline="", encoding="utf-8")):
            a = (r.get("mhc_restriction__name") or "").strip()
            tot += 1
            if norm(a):
                hit += 1
            else:
                miss[a] += 1
    cls = "I" if "mhc-I/" in fam else "II"
    agg["tot_" + cls] += tot
    agg["hit_" + cls] += hit
    top = ", ".join("%s(%d)" % (a or "<vacio>", n) for a, n in miss.most_common(2))
    print("%-24s %10d %10d %6.1f%%  %s" % (name, tot, hit, 100 * hit / max(tot, 1), top[:60]))

print()
for cls in ("I", "II"):
    t, h = agg["tot_" + cls], agg["hit_" + cls]
    print("CLASE %-3s  filas=%9d  con pseudosecuencia=%9d  (%.2f %%)" % (cls, t, h, 100 * h / t))
