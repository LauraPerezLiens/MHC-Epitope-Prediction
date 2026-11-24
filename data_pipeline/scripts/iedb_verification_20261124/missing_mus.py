#!/usr/bin/env python3
"""Los positivos de Wert que son Mus musculus (o sin organismo) y NO estan en
nuestra re-descarga: estan en el snapshot historico? Eso distingue
'el paginado antiguo/nuevo pierde filas' de 'el filtro los excluye'.
"""
import csv, collections, os
csv.field_size_limit(10**9)
WERT = ("/data/nap/lperez_nn/reference/neoantigenpred_zip/neoantigenpred-master/"
        "media/downloadable_content/H2Kb_data.csv")
NEW = "/data/nap/lperez_nn/data/data_raw_20261124/mouse/mhc-I/H2-K"
OLD = os.environ.get("OLD_RAW", "") and os.path.join(os.environ["OLD_RAW"], "mouse/mhc-I/H2-K")

def peps(base):
    out = set()
    if not base:
        return out
    for fn in ("mhc_export_full.csv", "tcell_export_full.csv"):
        p = os.path.join(base, fn)
        if os.path.exists(p) and os.path.getsize(p):
            for r in csv.DictReader(open(p, newline="", encoding="utf-8")):
                v = (r.get("epitope__name") or "").strip().upper()
                if v and v.isalpha():
                    out.add(v)
    return out

new, old = peps(NEW), peps(OLD)
print("peptidos H2-K  nuevo=%d  historico=%d" % (len(new), len(old)))

rows = list(csv.reader(open(WERT, newline="", encoding="utf-8", errors="replace")))
cat, nam, data = rows[3], rows[4], rows[5:]
seen = collections.Counter(); pn = []
for c in cat:
    pn.append(c if seen[c] == 0 else "%s.%d" % (c, seen[c])); seen[c] += 1
i_ep, i_as, i_src = pn.index("Epitope.2"), pn.index("Assay.4"), 18
g = lambda r, i: (r[i].strip() if i < len(r) else "")

# peptidos de interes: positivos de Wert, Mus musculus o sin organismo, ausentes del nuevo
tgt = collections.defaultdict(set)   # organismo -> peptidos
for r in data:
    pep, org = g(r, i_ep), g(r, i_src)
    if not pep or g(r, i_as) == "Negative" or pep in new:
        continue
    key = "Mus musculus" if "mus musculus" in org.lower() else ("(vacio)" if not org else None)
    if key:
        tgt[key].add(pep)

for key, s in sorted(tgt.items()):
    en_old = len(s & old) if old else None
    print("\n=== %s: %d peptidos unicos ausentes del nuevo ===" % (key, len(s)))
    if old:
        print("   de ellos, presentes en el snapshot historico: %d  (%.1f%%)"
              % (en_old, 100.0*en_old/max(1, len(s))))
        print("   ausentes en AMBOS (-> el filtro, no el paginado):   %d" % len(s - old))
    else:
        print("   (snapshot historico no disponible: exporta OLD_RAW)")
    print("   longitudes:", dict(sorted(collections.Counter(len(p) for p in s).items())[:10]))
    print("   ejemplos:", sorted(s)[:6])
