# NAP-CNB · Integridad y procedencia de los artefactos históricos BLOSUM62

**Fecha de revisión** 23 de noviembre de 2026 (UTC).

Se partió del inventario existente y de sus rutas. La revisión cotejó archivos de control, recibos, referencias y cabeceras. La lectura completa de payloads se acotó al TAR de intermedios, a archivos de control pequeños y a una muestra dirigida de bloques e índices. Las cifras de filas históricas describen una mezcla de originales y derivados. [Inventario de partida](d1_blosum_existing_inventory.md)

## 1. Artefactos examinados

Las rutas de la tabla son relativas al repositorio. Las rutas absolutas de los recibos apuntan al mismo árbol bajo `/data/nap/lperez_nn`. Los tamaños en GB y TB son decimales.

| Identificador y ruta | Formato, dimensiones, tamaño y registros | Origen y generación documentados |
|---|---|---|
| Intermedios, `data/used_data/data_intermediate.tar.zst` | TAR.ZST de 5.078.332.109 B. El inventario localizó once CSV BLOSUM62. Cardinalidad de filas por CSV y unicidad sin certificar. SHA-256 del TAR en el lateral `.sha256` y el recibo `.verification.json`. | Copia archivada de `data/data_intermediate`, comparada con GNU tar el 10-11-2026. La auditoría sitúa el historial del generador BLOSUM62 desde `9731ea3`. El recibo certifica la operación de archivo y carece de revisión ejecutada, semilla y dependencias por CSV. |
| ProtT5 familiar, `data/data_input_nn/{especie}/{clase}/{familia}/*_blosum_ProtT5_chunks/chunk_*_X.npy.zst` | 14.503 NPY.ZST, ~3,589 TB, 1.024 float32 por fila según contrato histórico. 1.449.852.950 filas declaradas. Hay CSV.ZST por bloque (~3,219 GB) y recibos `.archive.json` con dos SHA-256, bytes y firma original. | Once fuentes de clasificación BLOSUM62. Se documenta `Rostlab/prot_t5_xl_half_uniref50-enc`. La revisión exacta, el tokenizador y la ejecución por lote quedan sin acreditar. |
| Índices maestros familiares, `master_index.csv.zst` en cada directorio ProtT5 anterior | Once CSV.ZST, ~2,033 GB según el inventario, con recibos de ambas huellas. Cinco columnas en las once cabeceras: `chunk_id,row_idx_in_chunk,y,protein_group_id,group_id`. Los recuentos por familia se publicaron en la auditoría de fuentes. | El manifiesto de reordenamiento identifica el CSV plano de cada familia por `source.id`. Cada índice conserva direcciones dentro de su propia familia. |
| SecondaryBERT familiar, `data/data_input_nn/{especie}/{clase}/{familia}/*_SecondaryBERT_by_group/` | 551 NPY.ZST canónicos `chunks/chunk_*_X_ss.npy.zst`, ~131,317 GB, 768 float32 por entrada, 55.763.575 entradas de grupo declaradas. Manifiestos CSV, configuración JSON, índices y arrays de IDs archivados con dos huellas por recibo. | Once fuentes familiares con `config_version=2` y bloques de hasta 102.400 grupos, `model/secondary_bert`, tokens C/H/E y pooling documentados. La huella de configuración y metadatos de pesos registrada es `7714351fc71dd4c3b929d9835d00bdb7d4869e982b9fb32054e4bf9c3846b72d`. La auditoría certificada posterior excluye `chunks_pooled`. |
| Vista reordenada, `data/data_input_nn_shuffled/` | Bajo `mixed/classification_mixed_ProtT5_chunks/`, 14.499 NPY.ZST de 1.024 float32, ~3,868 TB, arrays de metadatos por bloque y `master_index.csv.zst` de 26.080.827.296 B. Manifiesto con 1.449.852.950 filas, 100.000 por bloque nominal y 52.950 en el último. | `reorder_manifest.json.zst` identifica once índices maestros y once almacenes SecondaryBERT, con offsets de grupo, semilla 42 y 1.024 buckets. Archivo por fichero `verified_zstd_v1` y marcador `verified_zstd_tree_v1` fechado el 14-11-2026 por mtime. El marcador cuenta solo los archivos comprimidos en su ejecución. |
| Vista concatenada, `data/data_input_nn_shuffled_concatenate/` | Bajo `mixed/classification_mixed_ProtT5_chunks/`, 14.499 NPY directos, 1.792 float32, ~10,393 TB y 1.449.852.950 filas declaradas. Recibos `chunk_*_X.json`, arrays `chunk_metadata/*_{y,group_id,split_id}.npy`, `feature_layout.json` y copia de `reorder_manifest.json`. | Formato `primary_secondary_float32_v1`, `normalized=false`, `complete=true`. El layout apunta al árbol reordenado. Los recibos observados van del 10 al 13-11-2026 por mtime de los extremos. |
| Índice SecondaryBERT certificado, `results/nap_cnb_v2_secondarybert/index.sqlite` | SQLite de 416.288.768 B, con 551 rutas de shard. El informe certificado declara 1.847.436 claves C/H/E exactas para 49.123.503 ventanas originales. Usa digests de clave y, para vectores nuevos, de clave más vector. | Fase 3C cerrada el 20-11-2026. Combina referencias a bloques históricos con vectores del piloto y de la ejecución final. Su certificación se ciñe a la selección original. |

Las rutas familiares se identifican de forma unívoca por el siguiente ID del manifiesto y por el directorio indicado en la tabla anterior. Las filas de ProtT5 provienen de la auditoría de fuentes. Los grupos proceden de los intervalos SecondaryBERT.

| ID y familia | ProtT5, bloques / filas declaradas | Índice familiar, bytes comprimidos / planos | SecondaryBERT, bloques / grupos |
|---|---:|---:|---:|
| 0 · HLA-A | 2.656 / 265.581.108 | 382.265.020 / 6.822.216.988 | 100 / 10.214.658 |
| 1 · HLA-B | 2.767 / 276.639.038 | 400.186.530 / 7.128.633.822 | 104 / 10.639.963 |
| 2 · HLA-C | 2.025 / 202.499.934 | 284.309.256 / 5.117.133.274 | 77 / 7.788.459 |
| 3 · HLA-DP | 1.308 / 130.710.450 | 180.482.463 / 3.224.143.594 | 50 / 5.027.325 |
| 4 · HLA-DQ | 622 / 62.125.466 | 83.577.271 / 1.487.472.422 | 24 / 2.389.441 |
| 5 · HLA-DR | 1.973 / 197.293.902 | 274.432.458 / 4.950.076.800 | 75 / 7.588.227 |
| 6 · H2-D | 1.104 / 110.365.892 | 149.664.937 / 2.691.863.710 | 42 / 4.244.842 |
| 7 · H2-K | 1.566 / 156.593.450 | 215.759.547 / 3.886.794.274 | 59 / 6.022.825 |
| 8 · H2-L | 2 / 115.648 | 95.080 / 1.915.068 | 1 / 4.448 |
| 9 · H2-IA | 466 / 46.559.006 | 61.354.106 / 1.098.329.122 | 18 / 1.790.731 |
| 10 · H2-IE | 14 / 1.369.056 | 1.227.663 / 25.758.466 | 1 / 52.656 |

Los valores `source_signature` del archivo Zstandard contienen dispositivo, inodo, tamaño y mtime en nanosegundos del original. Las firmas de entrada de concatenación registran ruta, tamaño y mtime, o un SHA-256 de la lista serializada de esas ternas. El segundo mecanismo fija la lista de metadatos y tiene un alcance distinto del SHA-256 del payload. Los mtimes indican una generación observada en el filesystem. En el primer bloque de HLA-A los mtimes originales observados fueron 09-06-2026 para ProtT5 y 28-09-2026 para SecondaryBERT. En el primer bloque reordenado fue 29-10-2026 y en el manifiesto de reordenamiento, 07-11-2026. Las etiquetas de formato especifican el contrato de almacenamiento. [Fuentes históricas](../../results/nap_cnb_v2_embedding_audit/embedding_sources.tsv) · [Archivador](../../data_pipeline/scripts/data_archiving/archive_inputs.py) · [Concatenación](../../data_pipeline/scripts/embedding_concatenation/concatenate_primary_secondary.py) · [Auditoría BLOSUM62](../../docs/NAP_CNB_v2_BLOSUM62_D2.md)

## 2. Criterios de clasificación

Las categorías de integridad física y procedencia se aplican por separado. La clasificación indica el alcance concreto de la comprobación.

| Categoría | Criterio |
|---|---|
| Integridad física verificada | Se releyó el archivo completo y se reprodujo la huella esperada, o se verificó la estructura interna cuando se indica expresamente ese alcance, como en SQLite. Para Zstandard, se especifica si se verificaron los bytes archivados y los descomprimidos. |
| Integridad documentada, pendiente de verificación | Existe recibo, manifiesto o validación anterior. Puede haber comprobaciones actuales de presencia, tamaños, cabeceras y sintaxis. Sigue pendiente reproducir la comprobación del contenido completo para ese archivo. |
| Procedencia parcialmente documentada | Hay fuentes identificadas, configuración o firmas de entrada, con eslabones históricos todavía sin fijar mediante huellas de contenido y versiones ejecutadas. |
| Procedencia no acreditada | La evidencia disponible es insuficiente para demostrar una correspondencia concreta, por ejemplo, variante–embedding o una equivalencia de revisiones. |
| Archivo ausente | La ruta literal carece del archivo esperado. Se indica si hay representación comprimida o si el árbol de origen quedó vacío tras el archivo. |

## 3. Garantías verificadas

- El TAR de intermedios coincide con los 5.078.332.109 B del recibo y con el SHA-256 de ambos registros, `17d7dfe210c1f6a10454a7d5747c5d2d36ed0778f5865c1c222a0ff657b879fe`. La comprobación releyó el TAR comprimido.
- El manifiesto de reordenamiento reproduce ambas huellas de su recibo. Su flujo descomprimido coincide byte a byte con la copia local de la vista concatenada. El layout resuelve el árbol reordenado y coincide con el manifiesto en número de bloques y filas.
- Los archivos de control SecondaryBERT se cotejaron en ambos flujos, con los SHA-256 del comprimido y del contenido expandido. Se incluyeron once configuraciones, once manifiestos familiares y el manifiesto mezclado.
- Las once cabeceras de los índices maestros familiares comparten el esquema de cinco columnas. Se releyó completo el índice de H2-L, el menor por bytes comprimidos. Coincidieron ambos SHA-256 y los 1.915.068 B descomprimidos. Se contaron 115.648 líneas de datos tras la cabecera.
- Reprodujeron ambas huellas el CSV de metadatos de ProtT5 HLA-A `000000` (3.875.658 B expandidos), el índice de IDs SecondaryBERT mezclado (55.763.575 enteros int64, 446.108.728 B expandidos) y el array `group_id` de SecondaryBERT HLA-A `000000` (102.400 enteros int64, 819.328 B expandidos).
- Los seis arrays concatenados `y`, `group_id` y `split_id` de los bloques `000000` y `014498` reproducen las huellas originales registradas en los recibos de archivo de la vista reordenada.
- Para el bloque `000000` de ProtT5 HLA-A, SecondaryBERT HLA-A y ProtT5 reordenado se verificaron ambos SHA-256, los tamaños descomprimidos y las cabeceras NPY. Las formas observadas fueron 100.000 × 1.024, 102.400 × 768 y 100.000 × 1.024, respectivamente, en float32. Los NPY concatenados `000000` y `014498` también reproducen el SHA-256 de su recibo, con 716.800.128 B y 379.545.728 B.
- SQLite devolvió `ok` en `PRAGMA quick_check` en modo de solo lectura e inmutable. Las 551 rutas planas del catálogo tienen copia `.zst` y recibo, comprobados por existencia. La comprobación de SQLite cubre su estructura interna y la resolución de rutas comprimidas.
- Los once manifiestos SecondaryBERT familiares concatenados por número acumulado de filas reproducen las 551 rutas y los intervalos del manifiesto mezclado. Los intervalos cubren 55.763.575 posiciones sin huecos. Los `group_id_offset` del manifiesto de reordenamiento se aplican a identificadores de grupo, mientras que los límites `start` y `end` se refieren a posiciones de almacenamiento.
- Se reconstruyeron 1.128 ternas de dependencias de la concatenación a partir de los recibos de archivo. Incluyen el índice maestro mixto, el índice y el manifiesto SecondaryBERT mezclados, los vectores canónicos, el manifiesto de reordenamiento y los índices, manifiestos e IDs de grupo familiares que enumera el procedimiento. El SHA-256 de las ternas serializadas es `0cfa8281af79228fc1d0b0f39b63014e58b3b1b788e4963a6a464892e458f99e`. Coincide con las 150 listas explícitas de los recibos `000000`–`000149`. También coincide con las 14.349 firmas compactas restantes. Se trata de coherencia de metadatos entre generaciones de recibo.

- Los 14.499 NPY concatenados tienen cabecera NPY 1.0, float32 little-endian, orden C y 1.792 columnas. Los tamaños suman 10.392.547.801.472 B y las cabeceras suman 1.449.852.950 filas. Se cotejaron tamaño y filas de salida, sintaxis del SHA-256 y firma primaria de los 14.499 recibos. Están presentes los tres arrays auxiliares de cada bloque.
- Coinciden los tamaños comprimidos de los 14.503 bloques ProtT5 familiares, sus 14.503 CSV por bloque, los once índices familiares, los 551 bloques SecondaryBERT canónicos y los 14.499 bloques reordenados con sus recibos. Los tamaños originales declarados para las matrices, descontando 128 B de cabecera según el esquema observado, son compatibles con 1.449.852.950 filas en cada vista primaria y 55.763.575 en SecondaryBERT. Para los archivos comprimidos fuera de la muestra, esta comprobación se basa en los tamaños declarados en los recibos.

## 4. Garantías respaldadas por documentación

- El recibo y el log del 10-11-2026 registran que `GNU tar --compare` cotejó contenido y metadatos del árbol de intermedios antes de retirar el original. La igualdad actual del TAR con su SHA-256 conserva esa copia documentada. Faltan huellas independientes de cada CSV y un acta de ejecución que vincule su generación a entradas y versiones concretas. [Recibo del TAR](../../data/used_data/data_intermediate.verification.json) · [Log de archivo](../../data/used_data/archive_20261110.log)
- El archivador `verified_zstd_v1` registra la huella del fichero original y la de la copia comprimida, comprueba la copia descomprimida y protege la operación con firmas de estado. El recibo registra ese procedimiento para los archivos cuyo contenido queda por verificar en esta revisión. [Implementación del archivador](../../data_pipeline/scripts/data_archiving/archive_inputs.py)
- La fase 3C documenta una auditoría previa de los 551 bloques SecondaryBERT canónicos y comprobaciones numéricas sobre 264 claves C/H/E exactas de once bloques. Esa evidencia se refiere a la modalidad y a sus claves de entrada. La huella histórica de configuración usa metadatos de pesos. El SHA-256 posterior de los pesos locales y la identidad numérica de la muestra tienen alcances propios. [Informe certificado de SecondaryBERT](../../results/nap_cnb_v2_secondarybert/secondarybert_report.md)
- Las cifras de 1.449.852.950 filas y 55.763.575 grupos se cotejaron como cardinalidades declaradas. La proporción de 26 filas por grupo es compatible con el procedimiento nominal de aumento. La uniformidad efectiva y la unicidad quedan indeterminadas. [Auditoría de aumento](../../docs/NAP_CNB_v2_BLOSUM62_D2.md)

## 5. Discrepancias y archivos ausentes

- Faltan las once rutas familiares `master_index.csv` que declara el manifiesto. En su mismo directorio se conservan las once copias `master_index.csv.zst` y sus recibos. Los identificadores de fuente son 0 HLA-A, 1 HLA-B, 2 HLA-C, 3 HLA-DP, 4 HLA-DQ, 5 HLA-DR, 6 H2-D, 7 H2-K, 8 H2-L, 9 H2-IA y 10 H2-IE.
- Los 551 shards NPY históricos referenciados por SQLite faltan en la ruta plana. Están disponibles las 551 copias comprimidas y los recibos. Los manifiestos SecondaryBERT conservan rutas previas al archivo para vectores y arrays de IDs. Las 1.128 dependencias de la firma común de concatenación faltan en su ruta plana. Cada una tiene copia comprimida con tamaño coincidente con el recibo. Los 551 shards citados están incluidos en ese conjunto de dependencias.
- `data/data_intermediate/` existe como directorio vacío. El árbol de origen del TAR está ausente en forma expandida. El log documenta su retirada después de la comparación. Los once `source_csv` de la configuración SecondaryBERT apuntan a CSV `*_ss.csv` de ese árbol, ausentes como archivos planos. Su presencia individual en el TAR queda sin revalidar. El directorio del modelo que indican esas configuraciones está presente.
- El README de concatenación anuncia copia de índices CSV. En el árbol concatenado actual faltan `master_index.csv` y `master_split.csv`, también en su forma `.zst`. Ambos se conservan comprimidos en el árbol reordenado. Los tamaños comprimidos coinciden con sus recibos. El índice de split ocupa 26.558.892.102 B. Las cabeceras conservan las direcciones `source_dataset_id,source_chunk_id,source_row_idx_in_chunk,source_group_id`. El índice de split añade `split_id`. Esta diferencia reduce la autonomía de la copia concatenada para consultar direcciones y splits históricos. [README histórico](../../data/data_input_nn_shuffled_concatenate/README.md) · [Layout](../../data/data_input_nn_shuffled_concatenate/feature_layout.json)
- Los recibos concatenados observados usan lista explícita o digest compacto de dependencias bajo la misma etiqueta de formato. El cotejo de la firma de 1.128 ternas concilia ambas formas en todo el conjunto. La versión exacta del ejecutable queda sin fijar en el recibo.

## 6. Limitaciones de procedencia

| Conjunto | Clasificación de la evidencia |
|---|---|
| TAR de intermedios | Integridad física verificada para el TAR. Procedencia parcialmente documentada por el recibo de copia. |
| ProtT5 familiar e índices | Integridad física verificada para el bloque y el CSV HLA-A de la muestra y el índice H2-L. Integridad documentada, pendiente de verificación de contenido para los demás. Procedencia parcialmente documentada a nivel de fuente. |
| SecondaryBERT histórico | Integridad física verificada en los archivos de control y la muestra citada. El resto conserva evidencia documental. Procedencia parcialmente documentada por fuente. La certificación 3C se limita a la selección original. |
| Vista reordenada | Integridad física verificada para el manifiesto y el bloque de muestra. Integridad documentada, pendiente de verificación para los demás vectores e índices maestros. Procedencia parcialmente documentada por el manifiesto de origen. |
| Vista concatenada | Integridad física verificada para los dos bloques y sus arrays muestreados. Integridad documentada, pendiente de verificación de contenido para el resto. Procedencia parcialmente documentada a nivel de dependencias. |
| SQLite SecondaryBERT | Integridad física verificada en el alcance estructural de `quick_check`. La correspondencia certificada se remite a la evidencia 3C para originales. |
| Rutas históricas expandidas | Archivo ausente en las rutas detalladas en la sección 5. |
| Correspondencia de variantes | Procedencia no acreditada para la correspondencia variante–embedding y para su equivalencia respecto a D1. |

Los SHA-256 válidos acreditan identidad de bytes respecto al recibo comprobado. La correspondencia entre un vector y una entrada biológica requiere evidencia independiente del orden y de la ejecución que produjo ese vector. Para ProtT5 faltan el vínculo de cada lote con una revisión exacta de pesos y tokenizador, el identificador de la ejecución y el anclaje por contenido de su manifiesto de entrada. Para el aumento siguen sin acreditarse la revisión ejecutada, la semilla y los hashes de origen por entrega. La evidencia SecondaryBERT es más específica para las claves C/H/E y para sus bloques canónicos. La correspondencia de un grupo con una estructura medida en una variante individual sigue sin acreditarse.

El reordenamiento conserva direcciones y offsets históricos. La concatenación hereda esa procedencia y acredita dependencias mediante metadatos de archivo. La revisión cubre la conservación de ese conjunto de evidencias. La cobertura, identidad y equivalencia respecto a D1 siguen indeterminadas.

## 7. Comprobaciones adicionales

1. Completar en una ventana de E/S acordada el cotejo de los SHA-256 de los payloads pendientes. Procesar por lotes reanudables y registrar por archivo el algoritmo, el alcance comprimido o expandido, los bytes y el resultado. Los NPY concatenados por sí solos requieren leer ~10,393 TB.
2. Para los NPY.ZST restantes, cotejar al descomprimir tamaño, cabecera y huella original, además de comprobar la huella del flujo comprimido. Completar el cotejo de huellas y dimensiones de los arrays auxiliares y de ambos índices maestros mixtos, que suman ~52,640 GB comprimidos.
3. Verificar una copia restaurada fuera de los árboles de trabajo para confirmar que los lectores resuelven las rutas planas archivadas y que se conservan tamaños, hashes y formatos. Conservar en un registro fechado el vínculo entre ruta histórica y ruta archivada.
4. Recuperar, si existen, manifiestos y logs de ejecución de las generaciones históricas con entrada y salida fijadas por digest, revisión de código, modelo, tokenizador y configuración. La conclusión sobre correspondencia sigue condicionada a esa evidencia. Estas comprobaciones de conservación pueden hacerse a nivel de archivo y de bloque.

## 8. Conclusión

El conjunto histórico conserva archivos, manifiestos y recibos suficientes para identificar sus vistas y comprobar parte de su integridad física. Los manifiestos y las firmas de dependencias enlazan fuentes y generaciones a nivel de archivo. La verificación completa de bytes sigue pendiente para la mayor parte de los vectores e índices. La procedencia histórica es parcial y la correspondencia variante–embedding sigue sin acreditarse. La disponibilidad de las vistas históricas deja indeterminada la cobertura de D1.
