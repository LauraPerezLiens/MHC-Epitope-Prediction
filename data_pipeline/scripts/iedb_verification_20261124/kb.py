import csv, collections
csv.field_size_limit(10**9)
root="/tmp/claude-7259/-data-nap-lperez-nn/71faedc6-a6ec-485d-aa35-95634e1242e6/scratchpad/data_raw_extract/data_raw/mouse/mhc-I/H2-K/"
rows=[]
for fn in ("mhc_export_full.csv","tcell_export_full.csv"):
    rows += list(csv.DictReader(open(root+fn,newline='',encoding='utf-8')))
kb=[r for r in rows if r["mhc_restriction__name"].strip()=="H2-Kb"]
print(f"filas H2-Kb: {len(kb)}")
print(f"referencias PMID distintas: {len(set(r['reference__pmid'] for r in kb))}")
print(f"epítopos (secuencia) distintos: {len(set(r['epitope__name'].strip().upper() for r in kb))}")
print(f"proteínas parent distintas: {len(set(r['epitope__molecule_parent_iri'].strip() for r in kb))}")
ln=collections.Counter(len(r['epitope__name'].strip()) for r in kb if r['epitope__name'].strip().isalpha())
print("longitudes:", dict(sorted(ln.items())[:14]))
c8_11=sum(v for k,v in ln.items() if 8<=k<=11)
print(f"filas con longitud 8-11: {c8_11} ({100*c8_11/len(kb):.1f}%)")
u8_11=len(set(r['epitope__name'].strip().upper() for r in kb if r['epitope__name'].strip().isalpha() and 8<=len(r['epitope__name'].strip())<=11))
print(f"péptidos únicos 8-11: {u8_11}")
