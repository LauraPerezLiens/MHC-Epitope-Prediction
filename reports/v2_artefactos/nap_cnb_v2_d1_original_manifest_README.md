# NAP-CNB · Manifiesto de observaciones originales de D1

Esta exportación conserva el orden de filas de la vista global certificada y resuelve las referencias a las dos modalidades. El archivo `manifest.json` registra la procedencia, los recuentos y las huellas SHA-256. Las rutas de ese archivo se resuelven desde la raíz del repositorio.

## Fuentes

| Fuente | Función en el manifiesto |
|---|---|
| `results/nap_cnb_v2_dataset_views/d1_manifest.json` | Certificación D1, recuentos, contrato y huellas de insumos. |
| `results/nap_cnb_v2_dataset_views/global_dataset.parquet` | Observaciones originales con clave exacta `(sequence, secondary_structure)` y etiqueta global. |
| `results/nap_cnb_v2_dataset_views/global_labels.parquet` | Una etiqueta global por primaria y número de representaciones. |
| `results/nap_cnb_v2_dataset_views/splits/assignments.parquet` | Partición certificada por `effective_group_id`, igual a la primaria exacta. Los códigos 0, 1 y 2 corresponden a TRAIN, VALIDATION y TEST. |
| `results/nap_cnb_v2_embedding_audit/missing_prott5_sequences.parquet` | Inventario ordenado de ProtT5. El ordinal de la primaria determina el shard y el desplazamiento. |
| `results/nap_cnb_v2_prott5/final/` | Manifiesto, recibos SQLite y shards NPY de ProtT5. |
| `results/nap_cnb_v2_secondarybert/index.sqlite` | Índice exacto de estructuras C/H/E. Una referencia apunta a una fila en `embedding` o a un archivo de `shard` y un desplazamiento en `inventory`. |

## Esquema de original_observations.parquet

| Campo | Tipo | Contenido |
|---|---|---|
| `observation_id` | Binary fijo, 50 bytes | Concatenación reversible de la primaria ASCII de 25 bytes y la estructura secundaria ASCII de 25 bytes. Clave primaria independiente de la posición de la fila. |
| `original_sequence_id` | String | Primaria exacta. Clave lógica de `global_labels.sequence` y `assignments.effective_group_id`. Puede repetirse cuando una primaria tiene varias estructuras. |
| `sequence` | String | Secuencia de aminoácidos original de 25 posiciones. |
| `secondary_structure` | String | Representación C/H/E de 25 posiciones. |
| `label_global` | Int8 | Etiqueta binaria de la primaria. |
| `split` | String | TRAIN, VALIDATION o TEST según la asignación certificada. |
| `prott5_shard` | UInt16 | Número de shard, con nombre `shard-NNNN.npy`. |
| `prott5_row_offset` | UInt32 | Índice base cero dentro del shard. |
| `secondarybert_key` | String | Clave exacta `inventory.structure` del índice SQLite. |

El orden contractual es ProtT5 (1.024) seguido de SecondaryBERT (768), en float32. Los embeddings se referencian en sus almacenes certificados. El scaler E1 solo figura como referencia con su huella.

Para incorporar registros relacionados en el futuro, el esquema admite una tabla separada con clave primaria propia y una clave foránea `parent_observation_id` de 50 bytes hacia `original_observations.observation_id`. La clave de secuencia por sí sola puede apuntar a varias observaciones. Los atributos del original se consultan por la clave foránea. Para apuntar a una revisión concreta del catálogo, se puede fijar el SHA-256 de `original_observations.parquet` en los metadatos de la tabla relacionada.

## Recuentos verificados

| Partición | Observaciones | Etiqueta 0 | Etiqueta 1 |
|---|---:|---:|---:|
| TRAIN | 12.083.630 | 9.006.997 | 3.076.633 |
| VALIDATION | 1.507.558 | 1.123.719 | 383.839 |
| TEST | 1.509.404 | 1.125.248 | 384.156 |
| Total | 15.100.592 | 11.255.964 | 3.844.628 |

La exportación contiene 14.530.324 identificadores de secuencia y 1.847.436 claves de SecondaryBERT utilizadas. Las referencias de ProtT5 abarcan 146 shards.

## Comprobaciones

- Huellas de los diez insumos certificados, del manifiesto D1 y del scaler E1 antes y después de la preparación.
- Unicidad global de la clave de observación, unicidad de las primarias en sus catálogos y cobertura de las claves de partición e inventario.
- Coincidencia de la etiqueta global y del número de representaciones por primaria entre las tablas fuente. Coincidencia de filas y clases por partición con D1.
- Cobertura de cada clave de embeddings. Cabeceras, dimensiones y tamaño de archivo de los shards ProtT5. Referencias lógicas del índice SecondaryBERT, presencia de archivos archivados y tamaño de los vectores inline y sus checksums.
- La comprobación de SecondaryBERT usa el catálogo certificado para el contenido de los vectores y los límites efectivos de cada archivo archivado.
- Esquema y recuento del Parquet de salida. `manifest.json` conserva su huella.

`build.py` es el constructor reproducible. Se ejecuta desde la raíz, con el entorno Python del proyecto y `PYTHONPATH=.`, en un directorio nuevo para evitar sobrescrituras. `build.log` y `resources.txt` registran la ejecución.

La lectura posterior con `verify.py` cotejó las 15.100.592 filas de salida con sus claves y etiquetas en la vista original, reconstruyó el identificador binario por fila y confirmó los recuentos de partición y la huella publicada. El resultado consta en `readback_verification.log`. `baselines_verification.log` registra el cotejo de las huellas publicadas de E1 y E2.

El índice SecondaryBERT registra 551 archivos históricos en su tabla de shards. D1 referencia 549 de ellos para 1.819.032 claves. Las otras 28.404 claves de D1 tienen su vector en SQLite. La construcción tardó 204,27 s y produjo un Parquet de 189 MiB.
