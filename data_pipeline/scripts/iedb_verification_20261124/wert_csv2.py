import csv, collections, itertools, sys
csv.field_size_limit(10**9)
p="/data/nap/lperez_nn/reference/neoantigenpred_zip/neoantigenpred-master/media/downloadable_content/H2Kb_data.csv"
rows=list(csv.reader(open(p,newline='',encoding='utf-8',errors='replace')))
# fila 0,1 comentarios; 2 vacia; 3 categorias; 4 nombres; 5+ datos
cat, nam = rows[3], rows[4]
data = rows[5:]
# reconstruir los nombres estilo pandas (header=categorias con dedup)
seen=collections.Counter(); pnames=[]
for c in cat:
    pnames.append(c if seen[c]==0 else f"{c}.{seen[c]}")
    seen[c]+=1
idx={n:i for i,n in enumerate(pnames)}
print(f"columnas: {len(cat)}   filas de datos: {len(data)}")
print("\n=== columnas que usa peptides_extraction.py ===")
for key in ["Epitope.2","Epitope.8","Assay.4","Reference.1"]:
    i=idx.get(key)
    print(f"  {key:12} idx={i:3}  categoria={cat[i]!r:18} NOMBRE REAL = {nam[i]!r}")
def col(key):
    i=idx[key]; return [(r[i].strip() if i<len(r) else "") for r in data]
print("\n=== Assay.4  (el campo que filtran por 'Negative') ===")
for v,k in collections.Counter(col("Assay.4")).most_common(10): print(f"   {k:7d}  {v!r}")
# organismo fuente
for key in ["Epitope.9","Epitope.10"]:
    i=idx.get(key)
    if i is not None:
        print(f"\n=== {key} = {nam[i]!r} ===")
        for v,k in collections.Counter(col(key)).most_common(12): print(f"   {k:7d}  {v[:60]!r}")
ep=[x for x in col("Epitope.2") if x]
print(f"\n=== peptidos ===\nfilas con peptido: {len(ep)}   unicos: {len(set(ep))}")
print("longitudes:", dict(sorted(collections.Counter(len(x) for x in ep).items())[:12]))
acc=col("Epitope.8")
print(f"\n=== Parent Protein Accession ===\nno vacios: {sum(1 for x in acc if x)}  vacios: {sum(1 for x in acc if not x)}  proteinas unicas: {len(set(x for x in acc if x))}")
# MHC allele column
for key,n in idx.items():
    if 'MHC' in cat[n] or 'MHC' in nam[n]:
        print(f"\n=== {key} idx={n} categoria={cat[n]!r} nombre={nam[n]!r} ===")
        for v,k in collections.Counter(col(key)).most_common(8): print(f"   {k:7d}  {v[:50]!r}")
