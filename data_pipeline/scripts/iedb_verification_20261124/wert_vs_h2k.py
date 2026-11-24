#!/usr/bin/env python3
"""Puente entre el dataset de Wert2021 (H2Kb_data.csv del ZIP) y nuestra
re-descarga de mouse/mhc-I/H2-K. Compara por SECUENCIA DE PEPTIDO, que es
la unica clave comun: los assay_id de Wert vienen de un export distinto.
"""
import csv, collections, os
csv.field_size_limit(10**9)

WERT = os.environ.get("WERT_CSV", "/data/nap/lperez_nn/reference/neoantigenpred_zip/"
       "neoantigenpred-master/media/downloadable_content/H2Kb_data.csv")
NEW = os.environ.get("NEW_RAW", "/data/nap/lperez_nn/data/data_raw_20261124")

# --- lado Wert: replicar peptides_extraction.py ---
rows = list(csv.reader(open(WERT, newline="", encoding="utf-8", errors="replace")))
cat, data = rows[3], rows[5:]
seen = collections.Counter(); pn = []
for c in cat:
    pn.append(c if seen[c] == 0 else "%s.%d" % (c, seen[c])); seen[c] += 1
i_ep, i_acc, i_as = pn.index("Epitope.2"), pn.index("Epitope.8"), pn.index("Assay.4")
g = lambda r, i: (r[i].strip() if i < len(r) else "")

wert_all = set()
wert_pos = set()
for r in data:
    pep = g(r, i_ep)
    if not pep:
        continue
    wert_all.add(pep)
    if g(r, i_as) != "Negative":
        wert_pos.add(pep)
wert_neg = wert_all - wert_pos

# --- lado nuestro: H2-K de la re-descarga ---
def peptides(path):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return set(), None
    out = set()
    with open(path, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        col = None
        for cand in ("epitope__name", "epitope_name", "linear_sequence",
                     "epitope__linear_sequence"):
            if rd.fieldnames and cand in rd.fieldnames:
                col = cand; break
        if col is None:
            return set(), (rd.fieldnames or [])[:40]
        for r in rd:
            v = (r.get(col) or "").strip().upper()
            if v and v.isalpha():
                out.add(v)
    return out, col

base = os.path.join(NEW, "mouse", "mhc-I", "H2-K")
ours_mhc, c1 = peptides(os.path.join(base, "mhc_export_full.csv"))
ours_tc, c2 = peptides(os.path.join(base, "tcell_export_full.csv"))
print("columna de peptido usada: mhc=%r  tcell=%r" % (c1, c2))
ours = ours_mhc | ours_tc

print("\n=== Wert H2Kb_data.csv ===")
print("  peptidos unicos            %7d" % len(wert_all))
print("  no-'Negative' (positivos)  %7d" % len(wert_pos))
print("  'Negative' explicitos      %7d" % len(wert_neg))
print("\n=== nuestra re-descarga mouse/mhc-I/H2-K (solo filas Positive) ===")
print("  peptidos unicos mhc_export   %7d" % len(ours_mhc))
print("  peptidos unicos tcell_export %7d" % len(ours_tc))
print("  union                        %7d" % len(ours))

print("\n=== interseccion por secuencia ===")
print("  positivos de Wert que tenemos      %7d / %d  (%.1f%%)"
      % (len(wert_pos & ours), len(wert_pos),
         100.0 * len(wert_pos & ours) / max(1, len(wert_pos))))
print("  positivos de Wert que NO tenemos   %7d" % len(wert_pos - ours))
print("  nuestros que Wert no tiene         %7d" % len(ours - wert_all))
print("  'Negative' de Wert que nosotros    %7d  <- discrepancia de etiqueta"
      % len(wert_neg & ours))

ln = collections.Counter(len(p) for p in (wert_pos - ours))
print("\n  longitudes de los positivos de Wert ausentes:",
      dict(sorted(ln.items())[:12]))
