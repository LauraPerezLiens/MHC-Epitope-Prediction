# Verificación de descarga IEDB

- Descarga nueva: `data/data_raw_20261124`
- Snapshot histórico: extraído de `data/used_data/data_raw.tar.zst` (snapshot del 10 nov 2026, 3,2 GB al extraer).
  Se extrajo a un directorio temporal que ya no existe; es re-extraíble con `zstd -dc ... | tar xf -`.
- Dataset de Wert2021: `/data/nap/lperez_nn/reference/neoantigenpred_zip/neoantigenpred-master/media/downloadable_content/H2Kb_data.csv`

## 1. Nuevo frente al histórico, por `assay_id`

| Familia | Export | Viejo | Nuevo | Dup. viejo | Solo viejo | Solo nuevo | Intercalado | Común |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| human/mhc-I/HLA-A | mhc | 522162 | 569013 | 0 | 0 | 46851 | 0 | 522162 |
| human/mhc-I/HLA-A | tcell | 10197 | 10484 | 0 | 0 | 287 | 10 | 10197 |
| human/mhc-I/HLA-B | mhc | 593273 | 664053 | 0 | 0 | 70780 | 0 | 593273 |
| human/mhc-I/HLA-B | tcell | 1045 | 1114 | 0 | 0 | 69 | 0 | 1045 |
| human/mhc-I/HLA-C | mhc | 136838 | 139852 | 0 | 0 | 3014 | 0 | 136838 |
| human/mhc-I/HLA-C | tcell | 313 | 320 | 0 | 0 | 7 | 0 | 313 |
| human/mhc-II/HLA-DP | mhc | 161793 | 162186 | 0 | 0 | 393 | 0 | 161793 |
| human/mhc-II/HLA-DP | tcell | 345 | 347 | 0 | 0 | 2 | 0 | 345 |
| human/mhc-II/HLA-DQ | mhc | 47617 | 50191 | 0 | 0 | 2574 | 0 | 47617 |
| human/mhc-II/HLA-DQ | tcell | 777 | 780 | 0 | 0 | 3 | 0 | 777 |
| human/mhc-II/HLA-DR | mhc | 346917 | 405608 | 0 | 0 | 58691 | 0 | 346917 |
| human/mhc-II/HLA-DR | tcell | 6297 | 6375 | 0 | 0 | 78 | 23 | 6297 |
| mouse/mhc-I/H2-D | mhc | 45517 | 45583 | 0 | 0 | 66 | 0 | 45517 |
| mouse/mhc-I/H2-D | tcell | 519 | 528 | 0 | 0 | 9 | 0 | 519 |
| mouse/mhc-I/H2-K | mhc | 87256 | 87593 | 0 | 0 | 337 | 0 | 87256 |
| mouse/mhc-I/H2-K | tcell | 1050 | 1076 | 0 | 0 | 26 | 0 | 1050 |
| mouse/mhc-I/H2-L | mhc | 44 | 44 | 0 | 0 | 0 | 0 | 44 |
| mouse/mhc-I/H2-L | tcell | 114 | 114 | 0 | 0 | 0 | 0 | 114 |
| mouse/mhc-II/H2-IA | mhc | 20679 | 29895 | 0 | 0 | 9216 | 0 | 20679 |
| mouse/mhc-II/H2-IA | tcell | 2101 | 2113 | 0 | 1 | 13 | 0 | 2100 |
| mouse/mhc-II/H2-IE | mhc | 233 | 233 | 0 | 0 | 0 | 0 | 233 |
| mouse/mhc-II/H2-IE | tcell | 173 | 173 | 0 | 0 | 0 | 0 | 173 |

**Totales.** Viejo 1985260 filas (0 duplicadas), nuevo 2177675. Solo en el viejo 1, solo en el nuevo 192416 (33 intercaladas), común 1985259.

> Cómo leerlo: `Dup. viejo` > 0 indicaría que el paginado por `offset` sin `order` repetía filas. `Intercalado` cuenta los `assay_id` nuevos **por debajo** del máximo del snapshot viejo: esos sí serían filas que el paginado antiguo se saltó. Si `Intercalado` ≈ 0, lo nuevo es crecimiento real de IEDB.

## 2. Nuestro mouse/mhc-I/H2-K frente al H-2Kb de Wert2021, por péptido

| Magnitud | Valor |
|---|---:|
| wert peptidos unicos | 12394 |
| wert positivos | 9827 |
| wert positivos con accession | 8903 |
| wert negativos explicitos | 2567 |
| nuestros peptidos unicos | 45150 |
| positivos de wert presentes | 5504 |
| positivos de wert presentes pct | 56.01 |
| positivos de wert ausentes | 4323 |
| nuestros que wert no tiene | 39646 |
| negativos de wert presentes | 0 |

> La clave de comparación es la **secuencia de péptido**, no el ensayo: el CSV de Wert procede de otro export de IEDB. `negativos de wert presentes` debe ser 0 en el perfil `legacy` (no descarga negativos) y >0 en el perfil `full`.

