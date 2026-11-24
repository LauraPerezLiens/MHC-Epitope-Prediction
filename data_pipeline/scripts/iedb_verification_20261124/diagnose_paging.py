#!/usr/bin/env python3
"""Diagnostico: los assay_id que faltan en data_raw, estan agrupados al final
del rango (= datos nuevos en IEDB) o repartidos (= paginado por offset roto)?

Si el paginado por offset sin ORDER BY se saltaba filas, las ausencias deben
aparecer en TODO el rango de assay_id, y en multiplos aproximados del LIMIT=1000
que usaba el script antiguo.
"""
import csv, os, sys
csv.field_size_limit(10**9)

OLD = "/tmp/claude-7259/-data-nap-lperez-nn/71faedc6-a6ec-485d-aa35-95634e1242e6/scratchpad/data_raw_extract/data_raw"
NEW = "/data/nap/lperez_nn/data/data_raw_20261124"


def ids(path):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return [int(r["assay_id"]) for r in csv.DictReader(f)
                if (r.get("assay_id") or "").strip()]


fam = sys.argv[1] if len(sys.argv) > 1 else "mouse/mhc-II/H2-IA"
mode = sys.argv[2] if len(sys.argv) > 2 else "mhc"
fn = "%s_export_full.csv" % mode

lo = ids(os.path.join(OLD, fam, fn))
ln = ids(os.path.join(NEW, fam, fn))
so, sn = set(lo), set(ln)
missing = sorted(sn - so)   # estan hoy, faltaban en data_raw

print("### %s / %s" % (fam, mode))
print("viejo: %d filas (%d assay_id unicos, %d duplicados)" % (len(lo), len(so), len(lo) - len(so)))
print("nuevo: %d filas (%d assay_id unicos, %d duplicados)" % (len(ln), len(sn), len(ln) - len(sn)))
print("ausentes en el viejo: %d" % len(missing))
if not missing or not sn:
    sys.exit()

lo_max = max(so) if so else 0
print("\nassay_id maximo en el viejo : %d" % lo_max)
print("assay_id maximo en el nuevo : %d" % max(sn))
n_above = sum(1 for m in missing if m > lo_max)
print("\nausentes POR ENCIMA del maximo viejo (= altas nuevas en IEDB): %d  (%.1f %%)"
      % (n_above, 100 * n_above / len(missing)))
print("ausentes DENTRO del rango ya cubierto (= paginado roto)      : %d  (%.1f %%)"
      % (len(missing) - n_above, 100 * (len(missing) - n_above) / len(missing)))

# distribucion por deciles del rango de assay_id nuevo
lo_r, hi_r = min(sn), max(sn)
span = max(hi_r - lo_r, 1)
dec = [0] * 10
for m in missing:
    dec[min(int(10 * (m - lo_r) / span), 9)] += 1
print("\ndistribucion de las ausencias por decil del rango de assay_id:")
for i, c in enumerate(dec):
    bar = "#" * min(int(60 * c / max(dec)), 60) if max(dec) else ""
    print("  decil %2d  %7d  %s" % (i + 1, c, bar))

# posicion ordinal de las ausencias dentro de la secuencia nueva ordenada
order = {a: i for i, a in enumerate(sorted(sn))}
pos = sorted(order[m] for m in missing)
print("\nposicion ordinal de las ausencias (si el offset se saltaba paginas,")
print("deberian agruparse cerca de multiplos de 1000):")
print("  primeras 30:", pos[:30])
mod = [p % 1000 for p in pos]
import collections
c = collections.Counter(p // 1000 for p in pos)
print("  paginas de 1000 afectadas: %d de %d" % (len(c), (len(sn) // 1000) + 1))
