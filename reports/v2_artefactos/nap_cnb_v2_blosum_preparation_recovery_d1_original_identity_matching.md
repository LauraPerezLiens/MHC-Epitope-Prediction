# NAP-CNB · Comparación de originales de D1 con las fuentes históricas

**Fecha** 23 de noviembre de 2026 (UTC).

Se compararon **15.100.592 observaciones** y **14.530.324 secuencias primarias únicas** de D1 con los originales históricos de las once familias. Se recorrieron **1.449.852.950 filas** de los once CSV BLOSUM del TAR, agrupadas en **55.763.575 registros originales**. Para cada registro se comprobó la igualdad exacta de `original_seq`, `group_id` y `protein_group_id` con la fila del Parquet histórico de esa familia. Las once comparaciones arrojaron **cero discrepancias** en los tres campos. Los Parquet añaden URL y coordenada de la ventana. [Inventario del TAR](inventory.json) · [Configuración de las fuentes originales](../../../data/global_epitope_labels/config.json)

## Resultado por observación D1

| Categoría | Observaciones D1 | Porcentaje |
|---|---:|---:|
| A. Coincidencia inequívoca | 13.079.742 | 86,6174 % |
| B. Coincidencia ambigua | 1.738.537 | 11,5130 % |
| C. Sin coincidencia | 282.313 | 1,8695 % |
| **TOTAL** | **15.100.592** | **100 %** |

Los porcentajes se redondean a cuatro decimales.

- **A.** Hay una primaria exacta y un único contexto biológico respaldado entre los enlaces de originales conservados. El contexto se define por la accession, la versión, el SHA-256 de la proteína canónica y la posición de inicio. Cada A tiene respaldo histórico por primaria completa de la proteína y recorte C/H/E exactos, además de la URL y la coordenada. Varias anotaciones familiares de la misma ventana se cuentan como un contexto. Dos accesiones distintas conservaron contextos separados incluso cuando el contenido de la proteína era idéntico.
- **B.** La primaria está presente, con más de un contexto biológico respaldado o con evidencia insuficiente para vincular la observación D1 a una ventana histórica concreta.
- **C.** La primaria exacta está ausente en los once CSV BLOSUM históricos, cuya proyección se verificó contra los Parquet de originales.

La clasificación A acredita el contexto único **entre los enlaces conservados**. Una observación D1 agregada puede incluir otros contextos canónicos sin enlace histórico publicado. La procedencia de una ventana se estableció mediante URL normalizada, posición y primaria exacta. Se comprobó además la evidencia de proteína completa y C/H/E donde el archivo la conservaba. La revisión numérica figura en los encabezados FASTA cuando la referencia original la declara. Los CSV de ventanas no incluyen un campo de versión por fila.

### Primarias únicas y causas de ambigüedad

- Primarias encontradas **14.249.139**. Primarias ausentes **281.185**.
- Agrupando las observaciones por primaria, hay **12.618.616** con al menos una A, **1.630.523** con coincidencia solo B y **281.185** C.
- **14.735.074 observaciones** tienen al menos un enlace que respalda proteína y ventana en su familia y especie de origen. Es un recuento de observaciones, con independencia del número de enlaces.
- **1.655.332 observaciones B** tienen varios contextos respaldados. De ellas, **1.643.813** tienen al menos dos identidades proteicas y **11.519** tienen varias posiciones dentro de una sola identidad proteica.
- **83.205 observaciones B** tienen coincidencia exacta de primaria sin un enlace histórico de ventana respaldado para su par D1. El índice de enlaces solo conserva coincidencias positivas. Un desglose causal de estos casos requeriría registrar el resultado de cada candidata por URL, posición y estructura canónica, incluidos los descartes.
- **12.356.366 observaciones** comparten primaria con originales de varias familias. En **11.340.818** se conserva evidencia de ventana en varias familias. De ellas, **9.700.305** corresponden a un único contexto biológico y se clasificaron en A.

## Desglose por familia MHC y especie

Las columnas de coincidencia por primaria cuentan presencia en esa familia. Las de contexto registran enlaces verificados por proteína completa, posición y C/H/E. Una observación puede aparecer en varias filas. La especie es la del ámbito MHC del fichero, que por sí sola no determina el taxón de cada proteína fuente. Los contextos de la última columna se deduplican dentro de cada familia por observación D1, identidad proteica y comienzo de ventana.

| Familia | Especie | Filas originales históricas | Primarias D1 encontradas | Observaciones D1 por primaria | Observaciones D1 con contexto respaldado | Pares observación–contexto |
|---|---|---:|---:|---:|---:|---:|
| HLA-A | humano | 10.214.658 | 9.042.814 | 9.584.809 | 8.959.350 | 9.220.252 |
| HLA-B | humano | 10.639.963 | 9.045.249 | 9.585.654 | 8.929.413 | 9.252.660 |
| HLA-C | humano | 7.788.459 | 7.391.724 | 7.877.695 | 7.270.155 | 7.373.149 |
| HLA-DP | humano | 5.027.325 | 4.386.678 | 4.691.818 | 4.187.935 | 4.237.649 |
| HLA-DQ | humano | 2.389.441 | 2.141.365 | 2.300.395 | 2.001.069 | 2.036.603 |
| HLA-DR | humano | 7.588.227 | 6.272.555 | 6.679.450 | 5.628.611 | 5.731.554 |
| H2-D | ratón | 4.244.842 | 3.629.896 | 3.909.393 | 2.855.195 | 2.878.461 |
| H2-K | ratón | 6.022.825 | 5.448.724 | 5.857.597 | 5.259.452 | 5.310.178 |
| H2-L | ratón | 4.448 | 4.421 | 5.254 | 4.421 | 4.421 |
| H2-IA | ratón | 1.790.731 | 1.635.103 | 1.760.782 | 1.445.324 | 1.463.150 |
| H2-IE | ratón | 52.656 | 52.261 | 56.869 | 52.279 | 52.364 |

## Comprobación de proteína completa y estructura histórica

- Para **14.735.074 observaciones D1** con contexto enlazado se igualó el SHA-256 de la primaria completa de la proteína con un registro histórico de la misma URL y especie del fichero. **13.079.742** pertenecen a A. Al cotejar el C/H/E de esos mismos registros, **14.735.074 observaciones** tienen al menos una ventana con estructura idéntica, incluidas **13.079.742** de A.
- Se leyeron directamente los once `*_ss.csv` del TAR. Las **55.763.575 filas** contenían C/H/E y conservaron los mismos ordinales, primaria, URL y coordenada que su original. Cada recorte de C/H/E almacenado coincidió con la predicción histórica de su proteína completa y con la primaria de la misma posición. El cotejo de ventanas D1 contra esas predicciones respaldó las **47.560.441 ventanas canónicas por familia** y por transitividad sus **51.593.373 enlaces históricos**, con cero discrepancias de C/H/E.
- Coincidieron por SHA-256 los once CSV de clasificación original del TAR con sus copias en `data/used_data/contradiction_sources/`. Coincidieron también los dos CSV de proteína completa y estructura con las copias de fase 1. Los miembros `human_parent_protein_fasta.csv` y `mouse_parent_protein_fasta.csv` conservan URL, accession resuelta y secuencia FASTA; la versión depende del identificador o encabezado archivado. La huella de la secuencia se calculó sobre los residuos de la proteína histórica. [Predicciones históricas](../../../results/nap_cnb_v2_phase1_structure/) · [Constructor de referencias](../../../data_pipeline/scripts/rebuild_iedb/rebuild.py)
- En el cruce de los FASTA con los Parquet canónicos de referencias se verificaron **86.025 pares familia–proteína** por URL y SHA-256 completo. Coincidió también el taxón explícito en esos pares. En **84.480** coincidieron asimismo accession y versión explícita. Para **143.664** de los **229.689** pares canónicos evaluados faltó un FASTA histórico inequívoco para la URL. Esta comprobación usa referencias de fase 1 como unidad. Las cifras anteriores usan observaciones D1. [Referencias de fase 1](../../../results/nap_cnb_v2_phase1/references/)


### Ejemplos comprobados por observación

- **A.** `MANLGYWLLALFVTMWTDVGLCKKR` · C/H/E `CCHHHHHHHHHHHHHHHHHHCCCCC`. `P04925` (versión 2, SHA-256 `1cab5dc12399…`), posición 1, familias H2-D, H2-IA, H2-K, H2-L. Un enlace verificable es el grupo local `741307` de H2-D.
- **B.** `LCKKRPKPGGWNTGGSRYPGQGSPG` · C/H/E `CCCCCCCCCCCCCCCCCCCCCCCCC`. Se encontraron 2 contextos canónicos enlazados. `P04156` (versión 1, SHA-256 `956f05d9f4f9…`), posición 21, familias HLA-A, HLA-B, HLA-C, HLA-DP, HLA-DQ, HLA-DR. Un enlace verificable es el grupo local `1593193` de HLA-A. `P04925` (versión 2, SHA-256 `1cab5dc12399…`), posición 21, familias H2-D, H2-IA, H2-K, H2-L. Un enlace verificable es el grupo local `741327` de H2-D.
- **C.** `AAAAAAAAAAAAAAGEAINPTYYDC` · C/H/E `HHHHHHHHHHHHHHCCCCCCCCCCC`. La primaria exacta está ausente en las once familias.
- **Duplicados de origen.** En HLA-B, 10.261.739 enlaces se resolvieron en 9.252.660 ventanas canónicas. Los 1.009.079 enlaces adicionales apuntan a ventanas canónicas ya contadas.

## Fuentes y comprobaciones de consistencia

1. Se leyó la clave binaria de las observaciones de [D1 original](../../../results/nap_cnb_v2_d1_original_manifest/README.md). La clave concatena la primaria exacta y la cadena C/H/E exacta. Se comprobaron su unicidad y los recuentos de observaciones y primarias.
2. Se leyó el TAR secuencialmente. Cada grupo de 26 filas conservó los dos ordinales y la primaria, y empezó por su única fila con `original_seq == blosum_seq`. Se cotejaron por orden los tres campos de cada original con el Parquet y se comprobó la presencia exacta de las primarias D1 en esas proyecciones. La fuente histórica registra `protein_url`, `window_start`, el ámbito familiar y el ordinal local `protein_group_id`. La URL y la coordenada se conservan también en los CSV originales de `data/used_data/contradiction_sources/`. Las fuentes canónicas previas a D1 registran URL, accession, versión, SHA-256 de la proteína, posición, familia, organismo y estructura, con recuperaciones documentadas en la selección final. [Selección canónica](../../../results/nap_cnb_v2_final_selection/selection.json)
3. Se reutilizó la evidencia publicada de enlaces de **originales** y de procedencia de ventanas en `legacy_group_links.parquet`, `window_provenance.parquet` y `base_dataset.parquet`. Se comprobaron el ámbito familiar y la especie, la cardinalidad de los enlaces de ventana y que todos los pares canónicos así resueltos pertenecieran a D1. Se deduplicaron las anotaciones equivalentes por accession canónica, versión, SHA-256 y posición inicial de base uno. Las accesiones distintas conservaron su propia identidad, incluso si compartían SHA-256. Para una accession vacía se aplicó la URL canónica como identificador. Los ordinales locales quedaron fuera del criterio de identidad.
4. El cálculo cruzó índices de ventanas por familia, mantuvo una máscara de coincidencia de primarias y los contextos extremos por observación D1 para distinguir cero, uno o varios contextos. El denominador suma 15.100.592 observaciones. A más las B con algún enlace coincide con el total con procedencia. B se descompone exactamente en observaciones con varios contextos y coincidencias de primaria sin enlace. El cálculo leyó exclusivamente CSV y columnas de metadatos Parquet. El cruce de D1 y procedencia tomó **507.2 s**, más la lectura y verificación secuencial del TAR.
