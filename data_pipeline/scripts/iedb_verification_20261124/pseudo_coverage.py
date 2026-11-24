#!/usr/bin/env python3
"""Cobertura de la tabla de pseudosecuencias NetMHCpan 34aa frente a los
alelos realmente presentes en data_raw."""
import csv, collections, glob, os
csv.field_size_limit(10**9)

PSEUDO = "/data/nap/lperez_nn/reference/pseudosequences/pseudosequences.netmhcpan.34aa.csv"
ROOT = os.environ.get("RAW_ROOT", "/data/nap/lperez_nn/data/data_raw_20261124")

pseudo = {}
for r in csv.DictReader(open(PSEUDO)):
    pseudo[r["allele"]] = r["pseudosequence"]
print("alelos en la tabla: %d   longitud: %s" % (
    len(pseudo), sorted({len(v) for v in pseudo.values()})))

# alelos y numero de filas en data_raw
rows_by_allele = collections.Counter()
for fam in sorted(glob.glob(ROOT + "/*/*/*")):
    for fn in ("mhc_export_full.csv", "tcell_export_full.csv"):
        p = os.path.join(fam, fn)
        if not os.path.exists(p) or os.path.getsize(p) == 0:
            continue
        for r in csv.DictReader(open(p, newline="", encoding="utf-8")):
            rows_by_allele[(r.get("mhc_restriction__name") or "").strip()] += 1

total_rows = sum(rows_by_allele.values())


def norm(a):
    """La tabla usa HLA-A02:01 y HLA-A0201 (sin asterisco)."""
    cands = [a, a.replace("*", ""), a.replace("*", "").replace(":", "")]
    cands += [c.replace("H2-", "H-2-") for c in list(cands)]
    cands += [c.replace("H-2-", "H2-") for c in list(cands)]
    for c in cands:
        if c in pseudo:
            return c
    return None


hit_alleles, miss_alleles = [], []
hit_rows = miss_rows = 0
for a, n in rows_by_allele.items():
    if norm(a):
        hit_alleles.append((a, n)); hit_rows += n
    else:
        miss_alleles.append((a, n)); miss_rows += n

print("\n=== COBERTURA ===")
print("alelos distintos en data_raw : %d" % len(rows_by_allele))
print("  con pseudosecuencia        : %d" % len(hit_alleles))
print("  sin pseudosecuencia        : %d" % len(miss_alleles))
print("filas totales                : %d" % total_rows)
print("  cubiertas                  : %d  (%.2f %%)" % (hit_rows, 100 * hit_rows / total_rows))
print("  no cubiertas               : %d  (%.2f %%)" % (miss_rows, 100 * miss_rows / total_rows))

print("\n=== los 20 alelos SIN pseudosecuencia con mas filas ===")
for a, n in sorted(miss_alleles, key=lambda x: -x[1])[:20]:
    print("  %8d  %r" % (n, a[:60]))

print("\n=== ejemplo: pseudosecuencias de los haplotipos de raton de clase I ===")
for a in ["H2-Kb", "H2-Kd", "H2-Kk", "H2-Db", "H2-Dd", "H2-Ld"]:
    k = norm(a)
    print("  %-7s %s" % (a, pseudo[k] if k else "AUSENTE"))

print("\n=== cuanto se parecen entre si (identidad por posicion) ===")
import itertools
ks = {a: pseudo[norm(a)] for a in ["H2-Kb", "H2-Kd", "H2-Kk", "H2-Db"] if norm(a)}
for a, b in itertools.combinations(ks, 2):
    same = sum(1 for x, y in zip(ks[a], ks[b]) if x == y)
    print("  %-6s vs %-6s  %2d/34 iguales (%.0f %%)" % (a, b, same, 100 * same / 34))
