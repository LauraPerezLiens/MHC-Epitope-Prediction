import csv, collections
csv.field_size_limit(10**9)
p="/data/nap/lperez_nn/reference/neoantigenpred_zip/neoantigenpred-master/media/downloadable_content/H2Kb_data.csv"
rows=list(csv.reader(open(p,newline='',encoding='utf-8',errors='replace')))
cat=rows[3]; data=rows[5:]
seen=collections.Counter(); pn=[]
for c in cat:
    pn.append(c if seen[c]==0 else f"{c}.{seen[c]}"); seen[c]+=1
i_ep, i_acc, i_as = pn.index("Epitope.2"), pn.index("Epitope.8"), pn.index("Assay.4")
g=lambda r,i: (r[i].strip() if i<len(r) else "")
print(f"0. filas de datos                        {len(data)}")
s1=[r for r in data if g(r,i_as)!="Negative"]
print(f"1. tras ~(Assay.4=='Negative')           {len(s1)}   (quita {len(data)-len(s1)} negativos explicitos)")
seen2=set(); s2=[]
for r in s1:
    k=g(r,i_ep)
    if k not in seen2: seen2.add(k); s2.append(r)
print(f"2. tras drop_duplicates(Epitope.2)       {len(s2)}")
rest=[r for r in s2 if not g(r,i_acc)]
main=[r for r in s2 if g(r,i_acc)]
print(f"3. IEDB  (con accession, va a Uniprot)   {len(main)}   <-- compara con '4.828 entradas IEDB' del paper")
print(f"   IEDB_rest (sin accession)             {len(rest)}")
print(f"   proteinas unicas a descargar          {len(set(g(r,i_acc) for r in main))}")
print(f"\n   de IEDB_rest, con len>=12 (se usan como positivos truncados): {sum(1 for r in rest if len(g(r,i_ep))>=12)}")
print(f"\n   longitudes de los {len(main)} epitopos con accession:")
print("  ", dict(sorted(collections.Counter(len(g(r,i_ep)) for r in main).items())[:10]))
