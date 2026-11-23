# NAP-CNB · Inventario de artefactos BLOSUM62 existentes

El corpus histórico tiene archivos de secuencias y metadatos, representaciones por modalidad y una vista concatenada. El manifiesto de reordenamiento registra **1.449.852.950 filas históricas** agrupadas en **55.763.575 grupos** según la auditoría previa. Las filas mezclan originales y derivados. La cobertura por secuencia única, la correspondencia entre revisiones y la cobertura de variantes respecto a D1 permanecen indeterminadas.

## Presencia física y cobertura documental

Los tamaños son aparentes y se expresan en unidades decimales. Los recuentos de archivos y la presencia de recibos se comprobaron en los árboles completos. Las cifras de filas y grupos proceden de los manifiestos y auditorías indicados. Cada vista histórica se cuenta por separado y sus filas pueden representar el mismo corpus.

| Conjunto y ruta | Formato y tamaño observado | Registros o claves documentados | Representación y evidencia |
|---|---|---|---|
| Intermedios históricos, `data/used_data/data_intermediate.tar.zst` | TAR.ZST de 5,078 GB, con SHA-256 y recibo `data_intermediate.verification.json` | El recibo histórico verifica la copia del árbol. El recuento de filas únicas queda indeterminado | El listado del TAR confirmó once miembros CSV de clasificación BLOSUM62. Los CSV históricos documentan la relación original–derivado y la procedencia familiar. El archivo no constituye un almacén de vectores. |
| Familias, `data/data_input_nn/*/*/*/*_blosum_ProtT5_chunks/` | 14.503 NPY.ZST, 3,589 TB de vectores. 14.503 CSV.ZST de metadatos, 3,219 GB. Once índices maestros comprimidos, 2,033 GB | 1.449.852.950 filas mixtas documentadas. Cardinalidad de primarias derivadas únicas sin certificar | ProtT5 histórico de 1.024 float32 por fila según la inspección previa. Existe recibo para cada bloque. La identidad y la revisión del embedding por variante siguen sin certificar para D1. |
| SecondaryBERT histórico, `data/data_input_nn/*/*/*/*_SecondaryBERT_by_group/chunks/` | 551 NPY.ZST, 131,317 GB de vectores | 55.763.575 filas de grupo documentadas | 768 float32 por entrada estructural según la inspección previa. Recibo para los 551 bloques. La representación se almacena por grupo y no acredita una estructura medida por variante. |
| Reordenado, `data/data_input_nn_shuffled/` | 14.499 NPY.ZST, 3,868 TB de vectores. Índice maestro comprimido de 26,081 GB y manifiesto comprimido presente | 1.449.852.950 filas mixtas documentadas | En esta vista los bloques corresponden a la modalidad primaria. El manifiesto histórico declara referencias a SecondaryBERT en otro almacén. Los 14.499 bloques tienen recibo. |
| Concatenado, `data/data_input_nn_shuffled_concatenate/` | 14.499 NPY directos, 10,393 TB de vectores. Manifiesto JSON, metadatos y recibos presentes | 1.449.852.950 filas mixtas declaradas en el manifiesto local | 1.792 float32 según contrato y cabeceras muestreadas en la inspección previa. Los 14.499 archivos tienen recibo. La completitud a nivel de bloque histórico no certifica correspondencia individual con D1. |
| Índice SecondaryBERT certificado, `results/nap_cnb_v2_secondarybert/index.sqlite` | SQLite de 416.288.768 bytes con referencias externas | 1.847.436 claves C/H/E de la selección original | Cobertura certificada para estructuras originales. La certificación tiene ese mismo alcance cuando se cita como evidencia. |

El manifiesto local del reordenamiento enumera once índices maestros familiares en CSV plano. Las once rutas planas están ausentes y las once copias `.zst` están presentes. Los índices de dirección y los CSV por bloque son artefactos distintos. Los identificadores de grupo se interpretan dentro de su fuente histórica. La presencia de un recibo junto a un archivo acredita que el recibo está disponible. Las comprobaciones de payload y cabeceras citadas pertenecen a las auditorías previas.

## Cobertura por fila y límites

| Categoría | Evidencia disponible |
|---|---|
| Registros aumentados encontrados | Se confirmó presencia de archivos históricos con metadatos de secuencia. El total mixto incluye originales. No hay un recuento certificado separado de derivados únicos. |
| Representación completa | La vista concatenada histórica declara ambas modalidades para el corpus mixto. La inspección previa confirmó el ancho combinado en sus bloques de muestra. La cantidad de variantes individuales con correspondencia certificada para D1 es indeterminada. |
| Representación parcial | Hay almacenes separados de ProtT5 por fila y SecondaryBERT por grupo. La presencia de estas modalidades por separado no cuantifica cuántas variantes tienen exactamente una de ellas. |
| Sin representación identificable | No hay un total certificado. Un registro sin enlace demostrado no implica que falte el archivo o el vector. |
| Correspondencia no verificada | Quedan indeterminados la correspondencia por variante con los originales certificados, la unicidad a escala del corpus y la versión de los embeddings históricos por lote. |
| Inventario aumentado certificado | La búsqueda de archivos y manifiestos no localizó una entrega D2 certificada. D1 y su catálogo corresponden a originales. |

El cotejo de esta fase se limitó a inventario físico y evidencia publicada. No se construyó un cruce de secuencias derivadas con embeddings ni un listado por variante de representaciones faltantes. Ese cruce prepararía un corpus de proteínas mutadas para el entrenamiento del predictor de epítopos y queda fuera del alcance de esta revisión. Los recuentos coincidentes se trataron como evidencia de cardinalidad, nunca como prueba de identidad.

- [Auditoría histórica y estado de D2](../../docs/NAP_CNB_v2_BLOSUM62_D2.md)
- [Inspección previa de cabeceras, direcciones y recibos](../../docs/NAP_CNB_v2_BLOSUM62_storage.md)
- [Manifiesto histórico de reordenamiento](../../data/data_input_nn_shuffled_concatenate/reorder_manifest.json)
- [Certificación del índice SecondaryBERT](../../results/nap_cnb_v2_secondarybert/secondarybert_report.md)
