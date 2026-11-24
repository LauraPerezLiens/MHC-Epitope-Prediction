import pandas as pd, collections
p="/data/nap/lperez_nn/reference/neoantigenpred_zip/neoantigenpred-master/media/downloadable_content/H2Kb_data.csv"
# dos lineas de comentario + fila de categorias + fila de nombres
df = pd.read_csv(p, skiprows=3, low_memory=False)
print("shape:", df.shape)
cols=list(df.columns)
print("\n=== las columnas que usa peptides_extraction.py ===")
for c in ["Epitope.2","Epitope.8","Assay.4","Reference.1"]:
    print(f"  {c!r:14} -> {cols[cols.index(c)] if c in cols else 'AUSENTE'}")
# map positional: Epitope.2 etc are pandas-dedup names; print their real header
import csv
raw=open(p).read().split("\n")
cat=next(csv.reader([raw[3]])); nam=next(csv.reader([raw[4]]))
print("\n=== cabecera real (categoria | nombre) para indices clave ===")
for i,c in enumerate(cols):
    if c in ("Epitope.2","Epitope.8","Assay.4","Reference.1"):
        print(f"  idx={i:3d}  {c!r:14} categoria={cat[i]!r:22} nombre={nam[i]!r}")
print("\n=== Assay.4 (lo que filtran por 'Negative') ===")
print(df["Assay.4"].value_counts(dropna=False).head(12))
print("\n=== organismo fuente del epitopo ===")
oc=[c for c in cols if c.startswith("Epitope")]
print(df["Epitope.9"].value_counts(dropna=False).head(15) if "Epitope.9" in cols else "n/a")
print("\n=== peptidos ===")
ep=df["Epitope.2"].dropna().astype(str)
print("filas con peptido:", len(ep), " unicos:", ep.nunique())
print("longitudes:", dict(sorted(collections.Counter(ep.str.len()).items())[:12]))
print("\n=== con accession de proteina (Epitope.8) ===")
print("no nulos:", df['Epitope.8'].notna().sum(), " nulos:", df['Epitope.8'].isna().sum(), " proteinas unicas:", df['Epitope.8'].nunique())
