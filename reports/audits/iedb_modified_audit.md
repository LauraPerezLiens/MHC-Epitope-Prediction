# Auditoría de la evidencia de péptidos modificados

## Alcance y procesamiento histórico

Se recorrieron los 1.985.260 registros de los 22 CSV MHC y T-cell archivados usando la tabla de procedencia que reproduce sus filas y claves originales. El descargador conservaba los metadatos químicos en el bruto. Al crear el CSV fusionado, la regex escogía el primer bloque de letras del nombre y descartaba el resto. La deduplicación por familia usaba ese bloque, inicio, fin, source y parent. La tabla fusionada perdía el identificador de estructura, la modificación y los vínculos de ensayo. Las referencias o posiciones distintas podían producir eventos diferentes incluso con la misma estructura. El signo + no se usó como clasificador.

[Normalización histórica](../../data_pipeline/scripts/data_download/build_iedb_dataset.py#L133) · [Fusión histórica](../../data_pipeline/scripts/data_download/build_iedb_dataset.py#L208) · [Manual de curación de IEDB](https://curationwiki.iedb.org/wiki/index.php/Curation_Manual)

## Entidades, esqueletos y equivalentes

Hay **147.985 registros modificados**, **147.985 ensayos con IRI distinto**, **95.177 IDs de epítopo modificado** y **81.679 esqueletos lineales** identificados. Entre los simples del archivo se identificaron **652.704 IDs** y **652.704 secuencias**. Quedaron 1 registros modificados sin ID y 15 sin esqueleto lineal resoluble con los datos recuperados.

**54.686 esqueletos modificados** tienen una entidad simple distinta en el catálogo consultado. **49.237** aparecen con respaldo positivo simple en los ensayos archivados. El nivel A consulta el catálogo de IEDB y mide existencia. B–D se limitan a positivos archivados de las once familias, con un IRI de ensayo independiente. La consulta del catálogo no demuestra positividad en una familia.

| Familia | Modificados únicos | A, simple en catálogo | B, positivo simple | C, misma referencia | D, locus verificado | Sin B con esqueleto conocido | % sin B | No determinado |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| HLA-A | 24.892 | 18.360 | 15.219 | 15.126 | 14.725 | 9.673 | 38,86% | 0 |
| HLA-B | 31.226 | 20.640 | 15.392 | 15.178 | 13.955 | 15.834 | 50,71% | 0 |
| HLA-C | 7.993 | 5.650 | 4.298 | 4.261 | 4.067 | 3.695 | 46,23% | 0 |
| HLA-DP | 6.429 | 5.306 | 5.175 | 5.095 | 4.997 | 1.254 | 19,51% | 0 |
| HLA-DQ | 2.103 | 1.442 | 1.203 | 1.192 | 1.088 | 900 | 42,80% | 0 |
| HLA-DR | 20.798 | 15.995 | 15.295 | 15.216 | 13.891 | 5.492 | 26,41% | 11 |
| H2-D | 2.344 | 1.618 | 829 | 823 | 612 | 1.515 | 64,63% | 0 |
| H2-K | 6.141 | 4.049 | 3.262 | 3.252 | 3.104 | 2.876 | 46,83% | 3 |
| H2-L | 1 | 1 | 1 | 1 | 1 | 0 | 0,00% | 0 |
| H2-IA | 2.469 | 1.375 | 1.000 | 974 | 569 | 1.469 | 59,50% | 0 |
| H2-IE | 7 | 7 | 6 | 6 | 2 | 1 | 14,29% | 0 |
| **Global, IDs deduplicados** | 95.177 | 65.876 | 57.269 | 56.774 | 52.743 | 37.894 | 39,81% | 14 |

C exige el mismo identificador source o parent con la versión y la isoforma intactas. D exige la misma referencia parent archivada, su hash y el mismo intervalo verificado para ambas evidencias. Se exige una anotación explícita para la referencia exacta, un remapeo previo validado o una proyección inequívoca desde la fuente. D es una cota de lo que se pudo verificar. La falta de coincidencia D no demuestra que no exista un locus equivalente.

Las consultas de IEDB registraron 0 lotes fallidos. Se observaron 0 respuestas con 1.000 o más filas en la caché. Los recuentos incompletos o las estructuras sin enlace quedan como desconocidos.

IDs con respaldo, sin respaldo o pendientes (`epitope_equivalents.csv`, artefacto retirado) · Equivalentes y ensayos trazables por registro (`modified_assays.csv`, artefacto retirado) · Distribución química original (`modifications.csv`, artefacto retirado) · Componentes de modificación (`modification_components.csv`, artefacto retirado)

## Origen de las duplicaciones

| Tipo | Registros implicados | IDs de epítopo | Eventos familiares |
|---|---:|---:|---:|
| Varios ensayos del mismo epítopo y clave | 1.284.106 | 255.152 | 301.025 |
| Distintas entidades modificadas fusionadas en la misma clave | 32.098 | 21.313 | 9.470 |
| Entidades simples y modificadas distintas fusionadas | 244.375 | 97.842 | 51.196 |
| Mismo epítopo en referencias o posiciones distintas | 808.703 | 117.961 | 284.570 |
| Otros casos con química o ID incierto | 34 | 1 | 1 |

Hay **51.196 claves mixtas demostradas** con IDs distintos. Añadir solo el estado simple/modificado a esas claves habría evitado al menos una fusión entre categorías por clave. Los registros implicados no son la cantidad de filas deduplicadas porque una clave puede reunir varios ensayos. Las categorías de auditoría pueden solaparse. Las referencias y posiciones distintas se conservaron como claves distintas y no producen duplicación en esa etapa.

Tabla de duplicaciones (`duplicate_sources.csv`, artefacto retirado)

## Posiciones positivas históricas

| Familia | Positivas históricas | Con simples | Con modificados | Ambas | Solo modificados | % solo modificados | Ambiguas sin simples |
|---|---:|---:|---:|---:|---:|---:|---:|
| HLA-A | 1.542.748 | 1.460.926 | 263.110 | 181.288 | 81.822 | 5,30% | 0 |
| HLA-B | 2.039.694 | 1.924.284 | 333.278 | 217.868 | 115.410 | 5,66% | 0 |
| HLA-C | 799.606 | 764.780 | 95.698 | 60.872 | 34.826 | 4,36% | 0 |
| HLA-DP | 243.947 | 238.030 | 27.060 | 21.143 | 5.917 | 2,43% | 0 |
| HLA-DQ | 108.383 | 104.712 | 8.674 | 5.003 | 3.671 | 3,39% | 0 |
| HLA-DR | 440.835 | 416.995 | 66.792 | 42.952 | 23.840 | 5,41% | 0 |
| H2-D | 181.137 | 173.489 | 18.129 | 10.481 | 7.648 | 4,22% | 0 |
| H2-K | 382.785 | 359.630 | 59.863 | 36.708 | 23.155 | 6,05% | 0 |
| H2-L | 99 | 99 | 17 | 17 | 0 | 0,00% | 0 |
| H2-IA | 50.779 | 47.251 | 7.659 | 4.131 | 3.528 | 6,95% | 0 |
| H2-IE | 1.269 | 1.260 | 45 | 36 | 9 | 0,71% | 0 |

Se cotejaron las filas positivas reales con el FASTA archivado y los eventos que pueden explicar la anotación seleccionada en esa posición. El respaldo simple histórico conserva esa regla local y su trazabilidad. No equivale a revalidar la referencia source de todos los eventos históricos. Se incorporaron además los remapeos ya verificados que disponen de ensayo simple independiente. Un positivo simple en otra familia preserva la etiqueta global.

## Impacto global y volumen de entrenamiento

De las **3.717.641 secuencias positivas actuales**, **3.558.191** conservan respaldo simple, **159.450** quedan respaldadas exclusivamente por evidencia modificada y **0** quedan ambiguas. La pérdida inequívoca bajo la regla de excluir solo los modificados representa **4,29%** de los positivos y **1,05%** de las secuencias del índice completo. Las ambiguas se mantienen aparte para revisión. Ninguna se declara negativa experimental.

| Métrica | Histórico | Escenario con evidencia simple y ambiguos aparte | Diferencia | % sobre el histórico |
|---|---:|---:|---:|---:|
| unique_global_positive | 3.717.641 | 3.558.191 | -159.450 | 4,29% |
| unique_global_unlabeled | 11.418.263 | 11.418.263 | 0 | 0% |
| positive_original_rows_global_label | 22.514.914 | 21.784.109 | -730.805 | 3,25% |
| operational_unlabeled_original_rows | 33.248.661 | 33.248.661 | 0 | 0% |
| original_rows_in_scenario | 55.763.575 | 55.032.770 | -730.805 | 1,31% |

Se trazaron **730.805 filas originales** de secuencias que perderían su respaldo y **0** de secuencias ambiguas. De ellas, 176.263 y 0 respectivamente tenían una anotación familiar positiva. Todas las apariciones en estos grupos tenían etiqueta global positiva, incluso cuando la etiqueta familiar era 0.

El manifiesto de BLOSUM62 es consistente con 26 filas por grupo original. A partir de los identificadores de origen, se estiman **19.000.930 filas** en grupos sin respaldo simple y **0** en grupos ambiguos. Se comprobó directamente en metadatos archivados la pertenencia y etiqueta familiar de **286 filas** de **11 grupos**. Las estimaciones no certifican cada grupo ni su asignación posterior a splits. Las variantes heredaron la etiqueta y carecen de respaldo experimental independiente.

Secuencias sin respaldo o ambiguas (`sequence_loss.csv`, artefacto retirado) · Trazabilidad de filas originales (`affected_original_groups.csv.gz`, artefacto retirado) · Muestra de direcciones BLOSUM62 (`blosum_address_sample.csv`, artefacto retirado) · Comparación global (`global_comparison.csv`, artefacto retirado)

## Comparación con las auditorías anteriores

Se cruzaron **42.809** de los 42.809 grupos modificados previamente verificados. **4.753** tienen un positivo simple de la misma secuencia y familia, y **3.411** tienen respaldo simple en el mismo locus verificado.

De las 167.119 secuencias del escenario estricto anterior, **159.450** continúan sin otro respaldo conocido, **0** quedan ambiguas y **7.669** conservan respaldo simple. Dentro de estas últimas, 0 tienen evidencia histórica identificable y 7.669 quedan respaldadas solo tras incluir remapeos simples verificados. Los remapeos se agregaron por secuencia y no se sumaron como casos nuevos independientes.

La auditoría no modifica etiquetas ni decide qué evidencia se usará para entrenar. Los conteos de sensibilidad son contrafactuales. Se preservaron los ficheros originales y no se reconstruyeron datasets, embeddings ni splits.

Resumen por familia (`by_family.csv`, artefacto retirado) · Cobertura de entidades (`entities.json`, artefacto retirado) · Impacto estructurado (`impact.json`, artefacto retirado)
