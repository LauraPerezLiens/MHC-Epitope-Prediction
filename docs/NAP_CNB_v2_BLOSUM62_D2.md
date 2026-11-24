# NAP-CNB v2 · Auditoría histórica de BLOSUM62 y estado de D2

## Resultado de la revisión

D1 sigue siendo la entrega certificada de originales con etiqueta global. D2 sigue sin construirse. La documentación disponible acredita un corpus aumentado histórico y la existencia de sus representaciones y direcciones. Esos hechos no establecen una correspondencia completa con la selección corregida, las etiquetas o las particiones de v2. Esta revisión reutiliza los recuentos y las comprobaciones publicadas, sin volver a recorrer los vectores, los CSV comprimidos ni los catálogos completos.

## A. Antecedentes y trazabilidad

El historial local de `generate_blosum62_variants.py` se remonta a `9731ea3`. El repositorio documenta aumento BLOSUM62 y una producción nominal de 25 derivados por registro original. El manifiesto agregado es compatible con 26 filas por grupo, contando el original. En efecto, 55.763.575 grupos por 26 producen 1.449.852.950 filas. Una auditoría anterior comprobó 286 filas en 11 grupos. La aritmética y la muestra no certifican uniformidad a nivel de cada grupo, ausencia de repeticiones ni una versión ejecutada del código, semilla o dependencias fijadas en cada salida histórica.

El CSV histórico de aumento conserva `original_seq`, `blosum_seq`, `group_id`, `protein_group_id`, `contains_epitope`, `selected_epitope` y `epitope_pos_score`. La clasificación asigna `group_id` por fila original y `protein_group_id` por URL dentro del archivo familiar. Los números locales se reutilizan entre archivos. El reordenamiento añade offsets documentados y conserva direcciones de origen en los índices maestros archivados. El identificador histórico verificable debe incluir el archivo de origen. Un grupo por sí solo no establece identidad de proteína, identidad de variante, validez de etiqueta o pertenencia a una partición v2.

La fase 4B encontró 1.675.495 ventanas originales v2 con varios candidatos históricos y 1.563.062 sin enlace. Esos recuentos describen la comparación de **originales**, no la elegibilidad de las variantes. Esta revisión no atribuye a D2 ninguna tasa de colisiones, coincidencias con originales, conflicto de etiquetas, cobertura de variantes únicas o enlace inequívoco.

[Auditoría de etiquetas heredadas y muestra de grupos](../reports/audits/iedb_modified_audit.md) · [Historial técnico](NAP_CNB_technical_history.md) · [Procedencia y metadatos de chunks](../data_pipeline/docs/data_and_models.md) · [Métricas de enlaces 4B](../results/nap_cnb_v2_dataset_views/metrics.json)

## B. Inventario y cobertura

Las cifras de disco de los árboles son bloques asignados en el inventario 4E. Las del informe de embeddings tienen el alcance de las fuentes o almacenes que ese informe indica. No deben sumarse a los árboles superiores.

| Tipo | Ruta | Recuento documentado | Almacenamiento documentado | Cobertura y estado |
|---|---|---:|---:|---|
| Originales históricos y grupos | `data/global_epitope_labels/` | 55.763.575 filas, 15.135.904 primarias únicas en el catálogo histórico original | 1,084 GB asignados | Catálogo original histórico. Sus etiquetas y universo difieren de v2 |
| Primarias históricas y archivos de origen | `data/data_input_nn/*/*/*/*_blosum_ProtT5_chunks/` | 1.449.852.950 filas en 14.503 bloques, mezcla de originales y derivados | 3,731 TB asignados para **todo** `data/data_input_nn/` | Recibos y CSV por bloque comprobados en auditorías anteriores. Cardinalidad de primarias únicas del corpus aumentado sin certificar |
| SecondaryBERT canónico histórico | `data/data_input_nn/*/*/*/*_SecondaryBERT_by_group/chunks/` | 55.763.575 filas en 551 bloques | 131,317 GB comprimidos en el alcance auditado | Vectores por grupo, clave C/H/E exacta. Los `chunks_pooled/` son otro payload |
| Corpus histórico reordenado | `data/data_input_nn_shuffled/` | 1.449.852.950 filas en 14.499 chunks mezclados | 3,927 TB asignados | Índices, offsets y metadatos históricos. Split por fila |
| Corpus histórico concatenado | `data/data_input_nn_shuffled_concatenate/` | 1.449.852.950 filas, 256.244.222 positivas históricas y 1.193.608.728 negativas operacionales históricas | 10,398 TB asignados | Float32, 1.792 dimensiones. Entradas de los experimentos LR y MLP históricos |
| ProtT5 original certificado | `results/nap_cnb_v2_prott5/final/` | 14.530.324 primarias únicas, 146 shards | 59.523.387.389 bytes de almacén | Completo para la selección v2. Identidad por primaria exacta |
| SecondaryBERT certificado | `results/nap_cnb_v2_secondarybert/index.sqlite` | 1.847.436 claves C/H/E, 1.819.032 históricas y 28.404 nuevas | 416.288.768 bytes SQLite, más referencias externas | Completo para las estructuras de la selección original |
| Splits y D1 | `results/nap_cnb_v2_dataset_views/` | 14.530.324 asignaciones, 15.100.592 pares D1 | 164.425.896 bytes el Parquet de asignaciones | Certificados para v2. Las particiones históricas no son intercambiables |
| Scaler histórico | `neural_network/MLP/standardizer_all_train_chunks.npz` | Estadísticas de dos modalidades, 14.499 chunks registrados | 421.906 bytes aparentes en la inspección anterior | Ajuste del TRAIN histórico aumentado con sus features. Sin certificación para otro conjunto |

[Auditoría de almacenamiento](../reports/NAP_CNB_repository_audit.md) · [Recuentos históricos por chunk](../reports/reorder_chunk_label_counts_20261110.csv) · [Auditoría de embeddings](../reports/audits/nap_cnb_v2_embedding_audit.md) · [ProtT5 certificado](../results/nap_cnb_v2_prott5/final_report.md) · [SecondaryBERT certificado](../results/nap_cnb_v2_secondarybert/secondarybert_report.md)

## C. Reutilización y límites

| Componente | Evidencia disponible | Límite |
|---|---|---|
| Primarias derivadas y direcciones históricas | El corpus y las direcciones por fuente, chunk y fila existen. La muestra previa comprueba procedencia a su escala | Sin cifra certificada de variantes únicas elegibles para v2 o de colisiones entre orígenes y particiones |
| ProtT5 aumentado | Los bloques históricos contienen embeddings de sus entradas primarias, con 1.024 float32 por fila según recibos y muestras | Las auditorías no vinculan revisión exacta, tokenizador y configuración a cada lote. 14.260.167 coincidencias de clave se midieron en el conjunto **original v2**, no en variantes elegibles. No se certificó reutilización de esos vectores históricos para v2 |
| SecondaryBERT histórico | El encoder usa exclusivamente la entrada C/H/E y el corpus legado comparte la representación estructural por grupo | La equivalencia por clave solo establece la identidad de la representación de esa entrada C/H/E. No prueba que una proteína modificada tenga la misma estructura |
| Catálogos y metadatos | Índices familiares, manifiesto de reordenamiento, recibos, `group_id` con ámbito de archivo, procedencia v2 y asignaciones certificadas | Los vínculos entre versiones pueden ser ambiguos. La existencia de una dirección no certifica la validez científica de una anotación |

Los vectores certificados de una primaria original corresponden a esa clave. Su historial no justifica reasignarlos a una primaria diferente. Tampoco hay una cifra verificada de embeddings adicionales requeridos, reutilizables o faltantes para D2. Los valores agregados del corpus legado no permiten inferirla.

[Auditoría de procedencia ProtT5](../reports/audits/prott5_audit_3a3.md) · [Auditoría numérica de compatibilidad](../reports/audits/prott5_audit_3a2.md)

## D. Etiquetas y contrato de evaluación

`label_original` describe la evidencia verificada en el contexto familiar de una ventana original. `label_global` es el máximo de las etiquetas originales observadas para una primaria exacta. Ambas etiquetas se fijan por la evidencia y la unidad de observación, no por el origen sintético de una fila. La etiqueta que porta un registro histórico derivado fue heredada. Eso conserva la trazabilidad de su experimento y no añade evidencia experimental independiente para la secuencia resultante. Los negativos son operacionales.

Una política conservadora de evidencia mantiene separadas las anotaciones observadas, las anotaciones heredadas y las identidades sin evidencia suficiente. Un registro ambiguo o contradictorio no se convierte automáticamente en positivo o negativo. La coincidencia de una entrada o la existencia de un vector no resuelve un conflicto de etiqueta. No se aprobó incorporar registros derivados con etiquetas inferidas ni redefinir el índice global.

Como condición de comparabilidad, cualquier conjunto futuro que se compare con D1 debe conservar exactamente su VALIDATION y TEST originales, con sus identidades, etiquetas y asignaciones. D1 TRAIN cuenta con 12.083.630 filas, 3.076.633 positivas y 9.006.997 negativas operacionales. VALIDATION y TEST cuentan con 1.507.558 y 1.509.404 filas respectivamente. Las comparaciones deben auditar identidad exacta entre particiones además de procedencia, porque el split histórico por fila fragmentó 55.595.967 de 55.763.575 grupos. Etiquetas diferentes y orígenes distintos deben mantenerse trazables en una revisión de duplicados. La exclusión por identidad con evaluación no debe provocar reasignación de las filas de evaluación ni depender de sus etiquetas. La partición D1 mide generalización a primarias exactas no vistas bajo su protocolo y no acredita independencia por proteína.

BLOSUM62 con etiqueta original tampoco tiene una entrega v2 certificada. Su replay legado usa una anotación, representación y partición históricas; sigue siendo un experimento distinto de una vista familiar corregida. Una comparación de cualquier nuevo conjunto con los perfiles balanceados exigiría su propio scaler ajustado solo con la población TRAIN efectiva, prevalencias observadas por tipo de registro y una evaluación fija. Los scalers histórico, base y D1 representan poblaciones diferentes.

[D1 y firmas](../results/nap_cnb_v2_dataset_views/d1_manifest.json) · [Validación de particiones](../results/nap_cnb_v2_dataset_views/splits/validation.json) · [Auditoría de solapamiento histórico](../reports/audits/group_split_check_summary.json) · [Perfiles y scalers](NAP_CNB_v2_training_guide.md)

## E. Capacidad y decisiones pendientes

- **Medido en D1.** 12.083.630 originales en train. Los otros dos conjuntos permanecen fijos.
- **Techo aritmético.** 302.090.750 filas adicionales a 25 por original TRAIN. Un vector float32 de 1.024 dimensiones por cada fila implicaría como máximo 1.237.363.712.000 bytes de payload, antes de índices, metadatos y espacio temporal. Es un escenario de máxima cardinalidad, no una proyección medida.
- **Referencia medida.** ProtT5 original generó y verificó 14.530.324 entradas en unas 7,12 horas. Ese tiempo no permite inferir la duración de un corpus con cardinalidad, procedencia, patrón de lectura y escritura aún desconocidos.
- **Capacidad observada.** `df -B1` mostró 21.800.871.395.328 bytes disponibles en `/data/nap` y 514.659.946.496 en el sistema de archivos de `/tmp` durante la revisión. La disponibilidad no constituye una reserva ni garantiza cuota o espacio temporal suficiente.
- **Sin estimación certificada.** Cardinalidad única de derivados, reutilización efectiva, metadatos por fila, RAM y CPU de un procesamiento y GPU y tiempo. Dar un único número exigiría suponer tasas de coincidencia e I/O que no se observaron.

Quedan por resolver la suficiencia de la evidencia para cualquier etiqueta sintética, el tratamiento de relaciones ambiguas, el alcance de evaluación y la compatibilidad verificable de los almacenes. Esta entrega cubre inventario y evidencia de auditoría de solo lectura. D2 permanece pendiente y no hay comandos de construcción, pilotos de variantes ni certificación nueva. Las ocho combinaciones conservan los estados declarados en la guía general.

[Medición original ProtT5](../results/nap_cnb_v2_prott5/final_report.md) · [Estado vigente y limitaciones de 4D](nap_cnb_v2_dataset_organization.md)
