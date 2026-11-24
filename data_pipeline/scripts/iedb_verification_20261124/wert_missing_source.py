#!/usr/bin/env python3
"""Por que faltan 4.328 positivos de Wert en nuestro H2-K?
Hipotesis: build_iedb_dataset.py filtra epitope__source_organism = especie
del host (Mus musculus), excluyendo epitopos virales/bacterianos.
"""
import csv, collections, os
csv.field_size_limit(10**9)
WERT = ("/data/nap/lperez_nn/reference/neoantigenpred_zip/neoantigenpred-master/"
        "media/downloadable_content/H2Kb_data.csv")
NEW = "/data/nap/lperez_nn/data/data_raw_20261124/mouse/mhc-I/H2-K"

rows = list(csv.reader(open(WERT, newline="", encoding="utf-8", errors="replace")))
cat, nam, data = rows[3], rows[4], rows[5:]
seen = collections.Counter(); pn = []
for c in cat:
    pn.append(c if seen[c] == 0 else "%s.%d" % (c, seen[c])); seen[c] += 1
g = lambda r, i: (r[i].strip() if i < len(r) else "")

# localizar columna de organismo fuente por su NOMBRE REAL (fila 4)
src = [i for i, n in enumerate(nam) if "Source Organism" in n or "Organism Name" in n]
print("columnas candidatas a organismo fuente:")
for i in src:
    print("   idx=%3d  %-20s %r" % (i, pn[i], nam[i]))
i_ep, i_as = pn.index("Epitope.2"), pn.index("Assay.4")
i_src = src[0] if src else None

ours = set()
for fn in ("mhc_export_full.csv", "tcell_export_full.csv"):
    p = os.path.join(NEW, fn)
    if os.path.exists(p) and os.path.getsize(p):
        for r in csv.DictReader(open(p, newline="", encoding="utf-8")):
            v = (r.get("epitope__name") or "").strip().upper()
            if v and v.isalpha():
                ours.add(v)

miss = collections.Counter(); have = collections.Counter()
for r in data:
    pep = g(r, i_ep)
    if not pep or g(r, i_as) == "Negative":
        continue
    org = g(r, i_src) if i_src is not None else "?"
    (have if pep in ours else miss)[org] += 1

print("\n=== organismo fuente de los positivos de Wert QUE NOS FALTAN ===")
for o, k in miss.most_common(15):
    print("   %6d  %r" % (k, o[:70]))
print("\n=== organismo fuente de los positivos de Wert QUE SI TENEMOS ===")
for o, k in have.most_common(10):
    print("   %6d  %r" % (k, o[:70]))
mus = lambda o: "mus musculus" in o.lower()
print("\nde los que faltan: %d de %d NO son Mus musculus (%.1f%%)"
      % (sum(k for o, k in miss.items() if not mus(o)), sum(miss.values()),
         100.0*sum(k for o, k in miss.items() if not mus(o))/max(1,sum(miss.values()))))
