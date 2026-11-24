import csv, collections, glob, os
csv.field_size_limit(10**9)
root="/tmp/claude-7259/-data-nap-lperez-nn/71faedc6-a6ec-485d-aa35-95634e1242e6/scratchpad/data_raw_extract/data_raw"
tot=collections.Counter()
for fam in sorted(glob.glob(root+"/*/*/*")):
    c=collections.Counter(); qual=collections.Counter()
    for fn in ("mhc_export_full.csv","tcell_export_full.csv"):
        p=os.path.join(fam,fn)
        if not os.path.exists(p) or os.path.getsize(p)==0: continue
        for r in csv.DictReader(open(p,newline='',encoding='utf-8')):
            a=(r.get("mhc_restriction__name") or "").strip()
            c[a]+=1; tot[a]+=1
            qual[(r.get("assay__qualitative_measurement") or "").strip()]+=1
    name="/".join(fam.split("/")[-3:])
    print(f"\n### {name}  filas={sum(c.values())}  alelos distintos={len(c)}")
    for a,k in c.most_common(8): print(f"     {k:8d}  {a[:60]}")
    if len(c)>8: print(f"     ... y {len(c)-8} más")
print(f"\n=== TOTAL alelos distintos en todo data_raw: {len(tot)} ===")
