# NAP-CNB v2 · validación ampliada ProtT5

Se compararon **576 secuencias crudas distintas de v2** en **32 bloques y once familias**. Cumplieron los criterios **572/576 comparaciones válidas (99,306 %)**. Se observaron **4 fallos válidos** y **0 comparaciones inválidas**.

## Protocolo y alcance

Antes de la inferencia se fijaron coseno ≥ 0,99999, L2 relativa ≤ 0,5 %, diferencia absoluta máxima ≤ 0,002, dimensión 1.024, finitud y asociación verificada. Los máximos de la fase 3A dejan margen frente a los tres umbrales. FP32 redujo el error en el control anterior sin establecer su causa. Los umbrales conservan su carácter provisional. Configuración fijada (`validation_config.json`, artefacto retirado) · Plan y hash previo (`sampling_plan.json`, artefacto retirado)

El inventario incluyó **14.503 bloques** de las once familias. Se sortearon hasta tres por familia, uno por tercio de orden temporal de archivo. Se usó la fecha de modificación archivada como aproximación del orden histórico. Se evitó reutilizar bloques del piloto cuando había alternativa. Todas las entradas limpias que se compararon positivamente son ajenas a 3A. Se seleccionaron 384 secuencias en los sorteos internos aleatorios y las restantes mediante estratos dirigidos. Se cubrieron entradas raras, frecuentes, duplicadas, variantes históricas ya existentes y residuos especiales cuando estuvieron disponibles. La muestra incluye 501 secuencias presentes en varias familias de v2, 70 filas de variantes históricas y 0 secuencias con residuos especiales o limpieza aplicada. La muestra no es proporcional al tráfico de ventanas ni a las fechas.

Se presupuestaron y leyeron **7.753 GB** de matrices comprimidas canónicas, frente a **3.589 TB** del inventario. Se verificaron los recibos, dimensiones, tipo y alineación de índices CSV y NPY. Los lotes de 32 se reconstruyeron con el generador de 3A, incluidos los contextos de lote. Solo se compararon positivamente claves de la selección definitiva. La singularidad de claves por bloque se midió en los bloques abiertos. El inventario previo aporta las multiplicidades globales por clave. El solapamiento exacto entre todos los pares de bloques quedó fuera del alcance.

Se reutilizó el checkpoint local fijado en 94a6abc029ae13029317b140b7424e012bf8dfbf y se verificaron sus hashes. Se ejecutó en una RTX 3090, con el tokenizador legado y FP16 de 3A. El contexto sigue sin acreditar la revisión y biblioteca de cada lote histórico. Fecha de ejecución 2026-11-19T12:49:23.321260+01:00. Entorno y huellas (`execution_environment.json`, artefacto retirado)

## Controles e incertidumbre

En las secuencias especiales hubo 0 aprobadas y 0 fallos válidos. En las estándar hubo 572 aprobadas y 4 fallos válidos. Esta comparación es descriptiva y combina estratos dirigidos y aleatorios.

| Control | Total | Aceptados |
|---|---:|---:|
| cross_family_random | 576 | 0 |
| nearest_vector_in_block | 576 | 0 |
| one_residue | 103 | 0 |

Hubo **0 controles aceptados con entrada limpia distinta**. Las colisiones con entrada limpia idéntica se registran aparte. La identidad cruda y la dirección verificada son requisitos independientes de la proximidad numérica. Se cotejaron 40 pares de ocurrencias históricas detectadas en la pasada de bloques muestreados. 40 fueron exactos y 0 cumplieron los umbrales sin identidad exacta. El cotejo de duplicados abarca una parte de las ocurrencias globales y puede omitir apariciones en bloques anteriores a la selección de una clave.

| Precisión | Filas | L2 relativa mediana | L2 relativa máxima | Máx. absoluto |
|---|---:|---:|---:|---:|
| history_fp16 | 11 | 0,060 % | 0,154 % | 0.00036621094 |
| history_fp32 | 11 | 0,053 % | 0,119 % | 0.00027967989 |
| fp16_fp32 | 11 | 0,055 % | 0,194 % | 0.00044440478 |

Las diferencias FP16/FP32 se midieron sobre entradas de las once familias. La comparación identifica sensibilidad al cálculo. Los entornos históricos siguen indeterminados.

Kruskal–Wallis exploratorio de la L2 relativa en las porciones aleatorias por bloque dio p=0.0531. Por tercio temporal, comparando medianas de bloque, dio p=0.198. El análisis no separa efectos de fecha, composición y familia. Los intervalos de Wilson del TSV usan solo el estrato aleatorio de cada bloque y describen esa población elegible. La regla A exigía límite inferior ≥95 %, además de controles adecuados y comparaciones aprobadas. Con 12 ensayos y todos aprobados, el límite inferior es 75,751 %.

| Categoría | Bloques | Secuencias únicas | Ventanas | Con SecondaryBERT verificado |
|---|---:|---:|---:|---:|
| A | 0 | 0 | 0 | 0 |
| B | 29 | 104.928 | 523.440 | 523.410 |
| C | 14.471 | 14.155.239 | 48.212.129 | — |
| D_only | 3 | 0 | 0 | — |
| conflict | — | 0 | 0 | — |
| missing | — | 270.157 | 387.934 | — |

Del total histórico de 1.449.852.950 filas, los bloques A contienen 0 (0,000 %) y los B 2.784.704 (0,192 %). Es una fracción de direcciones históricas, incluidas variantes, y se distingue de la cobertura de entradas v2.

La fila D contabiliza bloques incompatibles y claves cuyos candidatos son exclusivamente D. Hay **11.306 claves (54.638 ventanas)** con algún candidato D, incluidas claves que admiten otra categoría. Cuando se detecta un candidato D para una clave A/B, se retiene la clave en conflicto. Las cifras A/B se calcularon mediante claves exactas y filas direccionables. Las claves C incluyen bloques sin comparación o con evidencia insuficiente. Ningún bloque sin muestreo recibió una categoría favorable por cercanía a otro.

## Escenarios

| Escenario | Entradas por inferir | Ventanas afectadas | GB float32 | Horas ilustrativas a 100 entradas/s |
|---|---:|---:|---:|---:|
| A · solo bloques A | 14.530.324 | 49.123.503 | 59.516 | 40.36 |
| B · A y B sin conflicto | 14.425.396 | 48.600.063 | 59.086 | 40.07 |
| C · regeneración con evidencia insuficiente | 14.530.324 | 49.123.503 | 59.516 | 40.36 |

Las tasas son escenarios de planificación, sin benchmark de producción. El escenario conservador preserva solo candidatos con evidencia A. El ampliado acepta incertidumbre por bloque y guarda punteros históricos para su revisión. Una regeneración con checkpoint y entorno fijados resolvería la trazabilidad de los casos restantes, con coste de cómputo y almacenamiento. La estrategia operativa depende del nivel de evidencia que se acepte. Los escenarios se estimaron sin ejecutarlos.

## Resultados y archivos

- HLA-DR/1350 fila 14984 con coseno 0.999871786, L2 relativa 1,606 % y estado fail.
- HLA-DQ/31 fila 22158 con coseno 0.999926545, L2 relativa 1,213 % y estado fail.
- HLA-DR/876 fila 41398 con coseno 0.999971982, L2 relativa 0,754 % y estado fail.
- HLA-DR/876 fila 58506 con coseno 0.999989457, L2 relativa 0,459 % y estado fail.
- HLA-B/139 fila 57450 con coseno 0.999990928, L2 relativa 0,426 % y estado pass.

Con el criterio prerregistrado, **0 secuencias y 0 ventanas** alcanzaron cobertura A. La evidencia B, si existe, es una base para ampliar los ensayos por bloque y revisar las fuentes antes de autorizar reutilización a escala.

Manifiesto de muestras (`sample_manifest.parquet`, artefacto retirado) · Comparaciones (`embedding_comparisons.parquet`, artefacto retirado) · Controles negativos (`negative_controls.parquet`, artefacto retirado) · Precisión (`precision_control.parquet`, artefacto retirado) · Duplicados (`historical_duplicate_checks.parquet`, artefacto retirado) · Resumen por bloque (`block_validation_summary.tsv`, artefacto retirado) · Estadísticas (`metric_statistics.tsv`, artefacto retirado) · Cobertura (`prott5_coverage_3a2.tsv`, artefacto retirado)

Los vectores se conservaron en memoria durante el piloto. El resultado consiste en metadatos y métricas. Los datos v2 y los archivos históricos se abrieron en lectura. No se generaron los embeddings pendientes ni se abrió una fase de entrenamiento.

## Investigación de los fallos

Se repitió FP16 para las cuatro filas fallidas y se verificó su asociación con el registro original usando el Parquet histórico, el grupo, la secuencia cruda exacta y su fila en el bloque. Los cuatro errores FP16 se reprodujeron. El control focalizado reabrió solo los tres bloques afectados. La clasificación sigue el protocolo original en FP16.

| Familia y bloque | Fecha del archivo | Fila | L2 relativa FP16 | L2 relativa FP32 | Estado en FP32 |
|---|---|---:|---:|---:|---|
| HLA-DQ/31 | 2026-06-23 | 22158 | 1.21322 % | 1.49290 % | fail |
| HLA-DR/876 | 2026-06-19 | 41398 | 0.75406 % | 0.16886 % | pass |
| HLA-DR/876 | 2026-06-19 | 58506 | 0.45920 % | 0.07455 % | pass |
| HLA-DR/1350 | 2026-06-20 | 14984 | 1.60631 % | 2.32906 % | fail |

Los dos casos de HLA-DR/876 pasaron en FP32. Los casos de HLA-DQ/31 y HLA-DR/1350 empeoraron en FP32. La asociación histórica verificada y la repetición de FP16 descartan un error de dirección en estas cuatro filas. La causa de la discrepancia numérica sigue indeterminada. Control de los fallos (`failure_controls.parquet`, artefacto retirado)

En la selección completa hay **0 secuencias con símbolos fuera del alfabeto estándar y candidato histórico** y **0 sin candidato**. Ese subgrupo está ausente de la selección definitiva de v2.

## Recomendación

Mantener fuera los tres bloques D y conservar el resto de candidatos para trazabilidad. Los 29 bloques B son candidatos a una validación posterior por bloque. En el escenario ampliado cubrirían el **1.066 %** de las ventanas v2 y ahorrarían **0,430 GB** de float32. La evidencia disponible es insuficiente para reutilizar el corpus histórico en conjunto. Los resultados tampoco justifican ordenar de inmediato la regeneración masiva. La decisión sobre B y la ampliación de evidencia anteceden a cualquier cálculo de producción.

La lectura adicional de matrices comprimidas para el control focalizado fue de 0.759 GB. El plan enumeró todos los bloques antes de la selección de la muestra.
