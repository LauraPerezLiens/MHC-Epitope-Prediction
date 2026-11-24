import csv, sys, collections
csv.field_size_limit(10**9)
path = sys.argv[1]
cols = ["mhc_restriction__name","assay__qualitative_measurement","assay__method",
        "mhc_restriction__evidence_code","epitope__object_type","host__name",
        "epitope__source_organism","assay__units"]
cnt = {c: collections.Counter() for c in cols}
n=0; lens=collections.Counter(); quant=0; hasiri=0
with open(path, newline='', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        n+=1
        for c in cols: cnt[c][(r.get(c) or "").strip()] += 1
        ep=(r.get("epitope__name") or "").strip().upper()
        if ep.isalpha(): lens[len(ep)]+=1
        if (r.get("assay__quantitative_measurement") or "").strip(): quant+=1
        if (r.get("epitope__molecule_parent_iri") or "").strip(): hasiri+=1
print(f"FILAS: {n}   con medida cuantitativa: {quant} ({100*quant/max(n,1):.1f}%)   con parent_iri: {hasiri} ({100*hasiri/max(n,1):.1f}%)")
for c in cols:
    print(f"\n--- {c}  ({len(cnt[c])} valores distintos)")
    for v,k in cnt[c].most_common(15): print(f"   {k:8d}  {v[:90]!r}")
print("\n--- longitudes de péptido (top 15)")
for v,k in sorted(lens.items())[:20]: print(f"   len={v:3d}  {k}")
