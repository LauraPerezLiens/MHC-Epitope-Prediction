# Cobertura de la auditoría

**Estado de cierre: 144/144 archivos originales revisados semánticamente y 1 archivo local adicional.** Las secciones intermedias conservan los puntos de continuación de cada sesión.

Snapshot inicial de `ml_model_comparison` en `49c343b`, árbol limpio al iniciar.

- **144 archivos y 47.121 líneas** leídos en su totalidad por el análisis automatizado. Se registraron tamaño y SHA-256, se analizó el AST de todos los Python, se resolvieron enlaces Markdown locales y se buscaron dependencias y candidatos a duplicación.
- **510.113 rutas ignoradas** enumeradas por Git y agregadas por raíz y extensión. El CSV agrega esas rutas para evitar versionar un listado de medio millón de artefactos. No se leyó su contenido ni se calculó su tamaño individual.
- La lectura automatizada no certifica el comportamiento de cada archivo línea a línea. El CSV identifica cada ruta incluida. Para revisión semántica completa siguen pendientes todas las rutas versionadas del CSV salvo `data_pipeline/block_reader.py`, `tests/test_block_reader.py` y `data_pipeline/nap_cnb_v2_batches.py`. Del resto se inspeccionaron contratos y secciones específicas cuando figuran en los hallazgos.
- El recuento y los hashes describen el estado anterior a las correcciones y a la creación de estos entregables.

## Continuación del bloque A

Árbol inicial con la corrección NPY y los informes previos sin commit, sobre `49c343b`. Se completó la revisión semántica de los siguientes seis archivos, **1.107 líneas en las versiones revisadas**.

| Archivo | Entradas, salidas y consumidores | Casos límite y cobertura |
|---|---|---|
| `rebuild_iedb/structures.py` | Indexa CSV por organismo e identificador normalizado, exige primaria exacta y referencia fijada, devuelve estado, predicción e identidad. `rebuild.py` consume la resolución y usa la codificación para contar pares. | La fixture de reconstrucción cubre ausencia, desajuste, ambigüedad, referencia sin verificar y recorte. La codificación depende de longitud fija en su consumidor. Conservar ubicación y contrato. |
| `rebuild_iedb/phase1_report.py` | Lee un resumen validado y tablas Parquet de evidencia, proteínas, holdouts y procedencia. Publica TSV, métricas JSON e informe Markdown. El README de reconstrucción documenta su CLI. | Verifica cardinalidades por posición, gaps, holdouts y footers. Falta fixture integral para el informe. Se identificó una escritura parcial posible y un caso límite de procedencia vacía. |
| `global_epitope_labels/build.py` | Compara cabeceras y manifiesto, lee CSV en lotes, actualiza conteos SQLite y su registro de lotes en la misma transacción, exporta Parquet y llama al validador. | Cubierto por fixtures de reconciliación, reinicio transaccional, respaldo desde RAM, alcance y protección de entradas. Revisar identificación de cambios de contenido en futuras versiones del manifiesto. |
| `global_epitope_labels/validate.py` | Reconstruye conteos en un índice independiente, coteja cada grupo Parquet, compara totales familiares y únicos y publica informes. CLI y constructor comparten `validate_locked`. | Las fixtures verifican evidencia exacta y detección de modificaciones del export. La comprobación independiente vuelve a recorrer las fuentes utilizadas. Su ubicación distingue validación de construcción. |
| `data_archiving/archive_inputs.py` | Comprime y verifica con Zstd, publica un recibo y solo entonces elimina el original. Consumido por el CLI propio y el concatenador rápido. | Revisados firma, fsync, recibos y reanudación. La corrección cubre edición de igual tamaño con fecha restaurada. Se conserva el formato del recibo y la ruta del módulo. |
| `tests/test_archiving.py` | Fixture temporal con Zstd, interrupciones simuladas y verificación de archivos antes y después. | Cubre corrupción, poco espacio, symlinks, límites de publicación y la nueva regresión de edición concurrente. Los mocks se limitan al punto de fallo. |

`rebuild_iedb/rebuild.py` tiene revisión parcial de configuración, recuperación por familia y publicación final. La siguiente lectura debe comenzar por sus líneas 1–599, que contienen normalización, adquisición, cachés, evidencia y extracción. Después revisar íntegramente el resto, `dataset_views.py`, `final_selection.py` y `recover_structures.py`, antes de dar por cerrado el bloque A.

## Constructor, módulos relacionados y comienzo de splits

Se completó el recorrido semántico de cinco archivos que sumaban **2.214 líneas** en la lectura inicial de esta tanda. Se conservan los registros de las tandas anteriores.

| Archivo | Responsabilidad, entradas y consumidores | Casos límite y cobertura |
|---|---|---|
| `rebuild_iedb/rebuild.py` | CLI de reconstrucción. Filtra exportaciones archivadas, resuelve referencias y evidencia, produce tablas por familia y reconcilia ventanas y procedencia. Agrega por primaria mediante SQLite. Sus firmas se consumen en recuperación y selección. | Fixtures de referencias y estructuras, elegibilidad, coordenadas, holdouts y reconciliación. El guardado transaccional del agregado acopla conteos y lotes completados. El directorio de trabajo y sus checkpoints presuponen entradas estables. A11 queda abierto. |
| `rebuild_iedb/final_selection.py` | Valida exclusiones y recuperaciones por ID, revisa C/H/E y recuentos, y publica el manifiesto y el informe por renombrado. El constructor de vistas consume el manifiesto. | Detecta suplementos superpuestos, sobrantes y cambios de recuento. Añadida prueba de informe con una familia sin positivos. La certificación real utiliza cardinalidades fijadas. |
| `rebuild_iedb/dataset_views.py` | Valida firmas de selección, une metadatos Arrow, conserva enlaces de procedencia, calcula vistas base y global y publica el conjunto desde un directorio temporal. El generador de splits reutiliza `load_manifest` y `require`. | Los chequeos rápidos cubren el contrato de lectura de las vistas. La prueba completa del constructor requiere insumos de producción o desacoplar cardinalidades y rutas en una fixture. La carga de familias y catálogos completos merece medición aislada. |
| `rebuild_iedb/recover_structures.py` | Lee gaps y referencias Parquet, poda grupos por estadísticas, cruza archivos de predicciones y escribe un overlay y su evidencia. La selección definitiva consume ese overlay. | `test_recover_structures` cubre la resolución y los recortes, con cobertura parcial de la publicación. Se deja pendiente la fixture de recuperación con inventario vacío. |
| `data_splitting/check_master_split.py` | Valida CSV históricos fila a fila en lotes, compara proporciones por clase y chunk y coteja metadatos NPY con mmap. Lo usa `neural_network/MLP/check_preparation.py` y puede invocarse desde shell. | Su contrato permite solapamiento histórico por grupo. La nueva prueba cubre arranque por ruta y por módulo. No se ejecutó contra CSV históricos. |

Siguiente archivo pendiente del bloque A: `data_pipeline/scripts/data_splitting/split_nap_cnb_v2.py`, desde la línea 1. Quedan los demás scripts de particionado y los subdirectorios pendientes del bloque A.

## Particionado, metadatos históricos y descarga

Se revisaron semánticamente cuatro archivos, **1.113 líneas** del snapshot al iniciar la tanda. Cobertura acumulada: **18 archivos**.

| Archivo | Contrato, dependencias y consumidores | Cobertura y decisión |
|---|---|---|
| `data_splitting/split_nap_cnb_v2.py` | Asigna por primaria exacta con BLAKE2b, semilla de 64 bits y módulo 10. Asocia representaciones y vistas por catálogo, valida cardinalidades y coteja procedencia histórica. Publica Parquet y JSON tras reabrir y reproducir asignaciones. | La prueba compara con un cálculo independiente, reordena, usa un slice Arrow y repite una clave. Conserva semilla, hash, buckets, dtypes de salida y ruta. Los diagnósticos de solapamiento por proteína son distintos de la exclusividad por primaria. |
| `data_splitting/split_data.py` | Lee chunks consecutivos del CSV, asigna por clase con generador inicializado por semilla y chunk, y reemplaza el CSV al completar. Provee funciones al validador histórico. | Las fixtures cubren redondeo, lotes, orden, contigüidad y semilla. Se añadió rechazo de etiquetas matriciales. Mantener separado del contrato D1. |
| `data_splitting/prepare_chunk_metadata.py` | Proyecta cinco columnas de CSV, recompone chunks físicos y publica tres NPY consumidos por el lector histórico. Valida códigos, offsets y longitud antes de compactar. | Nueva fixture de códigos que desbordan `uint8`. La agrupación comparte intención con `iter_physical_chunks`, pero hoy difiere en proyección, dtypes y diagnósticos. Posponer la extracción hasta probar equivalencia y recuperación. |
| `data_download/build_iedb_dataset.py` | Usa requests con reintentos y offset, acumula páginas por familia, escribe los CSV completos y deduplica eventos para el flujo histórico. Auditores de descarga importan los helpers de normalización. | Se conserva la normalización histórica y su ruta. No se ejecutaron consultas remotas. Los tests de auditoría cubren consumidores parciales, no la descarga y publicación de extremo a extremo. |

Siguiente archivo pendiente: `data_pipeline/scripts/data_classification/fetch_parent_proteins_fastas.py`, línea 1. Después seguir con `epitope_classification.py`, aumento y reordenación. No se reabrieron como lecturas completas los archivos ya registrados.

## Clasificación, aumento y reordenación históricos

Cinco scripts revisados íntegramente, **1.898 líneas** antes de los cambios. Cobertura acumulada del snapshot: **23 de 144 archivos**. Se volvieron a examinar únicamente las secciones de firma y recuperación del constructor ya registrado.

| Archivo | Responsabilidad y consumidores | Casos límite y decisión |
|---|---|---|
| `data_classification/fetch_parent_proteins_fastas.py` | Recoge URLs únicas de CSV históricos, prepara una sesión con retries y timeouts, consulta proveedores y registra accesión solicitada y resuelta antes de exportar FASTA por especie. Lo consumen la clasificación y el registro de referencias archivadas. | Validación HTTP y de prefijo insuficiente para acreditar identidad, según A28. Escritura parcial reproducida y corregida con fixture. No se contactaron proveedores. |
| `data_classification/epitope_classification.py` | Carga el mapa de FASTA, verifica coordenadas, genera filas por ventana y evidencia, y asigna IDs dentro del archivo. Consumen sus resultados los flujos históricos de estructuras, etiquetas y aumento. | Hay pruebas de coordenadas y puntuación. El procesamiento acumula filas en memoria y la normalización URL coincide con el descargador. Se preserva el comportamiento histórico. |
| `data_augmentation/generate_blosum62_variants.py` | Lee CSV históricos, conserva IDs y etiqueta original, y exporta original y derivados con búfer. Su salida alimentó la preparación histórica de bloques. | Las pruebas existentes comprueban cardinalidad y orden de variantes. Escribe CSV por segmentos sin marcador de publicación. Se conservó la metodología y no se generó ningún dataset. |
| `data_shuffling/reorder_chunks.py` | Particiona filas y vectores por bucket, conserva direcciones de origen, asigna IDs de grupo sin solapamiento y publica chunks y un catálogo de referencias SecondaryBERT. Los splits históricos consumen el CSV mezclado. | El marcador `INCOMPLETE` protege el flujo normal. La RAM depende de un chunk fuente y de los metadatos de un bucket, además de la salida pendiente. El script de recuperación comparte formato y log. |
| `data_shuffling/resume_reorder_chunks.py` | Reconstruye un prefijo desde log, comprueba direcciones, unicidad, formas y muestras de embedding, y publica checkpoints de offsets CSV. El reordenador lo invoca con `--resume`. | Separación entre auditoría inicial y reuso de checkpoint. La regresión cubre un hueco entre bloques comprometidos y recuperación normal de una cola. La manipulación de los archivos se probó solo en fixtures temporales. |

Siguiente archivo pendiente del bloque B: `data_pipeline/scripts/embeddings/primary_structure/generate_prott5_embeddings.py`, línea 1.

## Generadores e índices de embeddings

Cuatro scripts revisados íntegramente, **2.502 líneas** antes de los cambios. Cobertura acumulada **27 de 144**.

| Archivo | Contrato, consumidores y decisión |
|---|---|
| `primary_structure/generate_prott5_embeddings.py` | Generador histórico por CSV, deduplica claves preprocesadas solo dentro del chunk y expande vectores en el orden de las filas válidas. El índice maestro enlaza los arrays de características y metadatos. Tokeniza con padding y truncamiento y promedia posiciones activas en la precisión del encoder. Se eliminó el reuso inseguro de directorios, conservando el esquema para destinos nuevos. |
| `primary_structure/prott5_v2.py` | Generador offline con pesos firmados, inventario por clave original, precisión y runtime registrados, 26 tokens activos con EOS y media en float32. Los shards preceden a la confirmación transaccional SQLite con checksum combinado de claves y vectores. El adaptador v2 usa ordinales. Se verificaron en fixtures corrupción de vector, shard ausente y reanudación. |
| `secondary_structure/generate_secondary_bert_embeddings.py` | Generador histórico por grupo, IDs directos C/H/E, CLS/SEP excluidos del pooling, salida de 768 dimensiones. Cada rank relee CSV, trabaja sobre sus chunks y publica tres NPY independientes. El rango cero crea manifiesto e índices. Se conservan limpieza, precisión, partición por rank y huella de pesos. |
| `secondary_structure/secondarybert_v2.py` | Indexa referencias históricas por C/H/E exacta con cotejo CSV e índice. Conserva vectores nuevos y SHA-256 asociado a clave en SQLite. Reutiliza el encoder histórico con el contrato numérico del piloto. Su lector propio descomprime por shard solicitado y no mantiene caché entre llamadas. Se reprodujo un offset negativo en fixture. |

Siguiente archivo pendiente: `data_pipeline/scripts/embeddings/secondary_structure/check_secondary_embeddings.py`, línea 1. Quedan predicción estructural, concatenación y entrenamiento/validación del encoder. Las pruebas existentes de concatenación se ejecutaron como regresión, sin marcar su código como revisado semánticamente.

## Validación y predicción estructural

Tres archivos revisados completos, **2.237 líneas** antes del cambio. Cobertura semántica acumulada **30 de 144 archivos**.

| Archivo | Contrato y alcance |
|---|---|
| `embeddings/secondary_structure/check_secondary_embeddings.py` | Auditor histórico de NPY directos. Valida formas, recuentos, continuidad, IDs globales y de chunk, orden y unicidad. Mapea archivos y muestrea hasta 512 vectores por chunk. La prueba de finitud es muestral. Los CSV de índice y metadatos se comprueban por presencia, por lo que el checker no acredita correspondencia C/H/E por fila. El cambio impide convertir offsets fraccionarios de forma silenciosa. |
| `secondary_structure_prediction/add_secondary_structure.py` | Cruza URLs con predicciones completas y comprueba igualdad de la primaria en la ventana antes de anexar C/H/E. Produce CSV históricos, consumidos después por el generador. El último duplicado de URL domina en el mapa. Carga tablas completas y publica CSV directamente. |
| `secondary_structure_prediction/predict_secondary_structure.py` | Carga ProteinUnet, codifica secuencias completas en ventanas acolchadas y recompone probabilidades en solapamientos. Publica CSV que consume el paso de recorte. Verifica residuos y longitud del resultado. La forma y finitud del tensor devuelto por el modelo no tienen pruebas específicas. Se preserva el cálculo histórico. |

Se revisaron puntualmente el lector v2 y sus firmas para habilitar una ruta segura. El archivo protegido y el generador firmado conservan sus hashes. Siguiente archivo pendiente: `data_pipeline/scripts/embedding_concatenation/concatenate_primary_secondary.py`, línea 1.

## Concatenación y preparación del encoder

Tres archivos revisados íntegramente, **1.334 líneas** en las versiones de entrada. Cobertura acumulada: **33 de 144 archivos**.

| Archivo | Contrato y alcance |
|---|---|
| `embedding_concatenation/concatenate_primary_secondary.py` | El modo rápido lee ProtT5 por posición dentro del chunk y SecondaryBERT por ID de grupo. Contrasta referencias secundarias con manifiestos originales, escribe NPY por bloques y coteja todos los valores serializados. Publica recibos y retira `INCOMPLETE` al finalizar. Incluye modo histórico in-place, verificación solo lectura, caché SSD y archivo posterior. Se corrigió la falta de cotejo entre metadatos preparados e índices de origen. |
| `secondaryBERT/build_secondary_mlm_dataset.py` | Lee CSV de ProteinUnet, conserva C/H/E válido de longitud compatible, escribe representaciones tokenizadas y tres splits Parquet por fila con semilla. El entrenador y el validador consumen estos archivos. Retiene tablas completas, no impone exclusividad por proteína y publica cada archivo por separado. Preservado por compatibilidad. |
| `secondaryBERT/validate_secondary_mlm.py` | Planifica unidades Parquet, distribuye ventanas entre ranks, aplica máscara seudorrandómica y reduce pérdida, precisión y confusión C/H/E. Usa `val.parquet` y comprueba el número de ventanas. Se identificó el caso de cero posiciones enmascaradas y su dependencia de la partición por rank. No se cargó el modelo. |

Siguiente archivo: `data_pipeline/scripts/secondaryBERT/train_secondary_mlm.py`, línea 1.

## Entrenamiento MLM y auditoría de predicciones UniRef30

Dos archivos nuevos en cobertura, **1.652 líneas** en las versiones de entrada. Cobertura acumulada **35 de 144 archivos**. Se revisaron además los puntos de publicación y reducción de dos módulos ya registrados.

| Archivo | Contrato y alcance |
|---|---|
| `secondaryBERT/train_secondary_mlm.py` | Lee Parquet por unidades, elige hasta tres ventanas de 25 posiciones por registro, usa 27 tokens sin padding y forma etiquetas dinámicas con `-100` para posiciones ignoradas. Distribuye unidades y usa AdamW, clipping y GradScaler opcional. Construye un flujo VALIDATION para sanidad inicial, sin evaluación durante las épocas. Exporta pesos y tokenizer al final. Se añadió un rechazo coordinado de batches sin objetivos. |
| `secondaryBERT/audit_uniref30_secondary_structure_predictions.py` | Cruza FASTA con CSV por ID y clasifica ausencias por archivo faltante, residuo no estándar u otro motivo. Trabaja por chunk en RAM. Registra presencia de IDs, sin acreditar igualdad de secuencia ni validez de la predicción. Un ID FASTA repetido sobrescribe el previo en el diccionario y la auditoría publica el CSV directamente. Sin cambios de comportamiento. |

Siguiente archivo: `data_pipeline/scripts/secondaryBERT/predict_uniref30_secondary_structure.py`, línea 1.

## UniRef30 y verificación distribuida

Tres archivos revisados íntegramente, **842 líneas** en sus versiones de entrada. Cobertura acumulada **38 de 144**.

| Archivo | Contrato y alcance |
|---|---|
| `secondaryBERT/predict_uniref30_secondary_structure.py` | Lee FASTA en orden, conserva ID y secuencia con cada predicción, codifica un ejemplo por llamada y combina ventanas de 1.024 posiciones con solapamiento. La memoria depende de un registro, buffers de probabilidades y del conjunto de IDs del chunk. Publica dos CSV que consumen el constructor MLM y la auditoría. Se añadieron validaciones de IDs y tensores y staging. No lleva manifiesto de modelo, recibos de contenido ni reanudación. |
| `secondaryBERT/create_uniref30_fasta_chunks.py` | Reparte el FASTA representante por número de encabezados y conserva su orden literal. El predictor consume los chunks. Escribe directamente y un relanzamiento con menos registros puede dejar chunks viejos. Falta una prueba de publicación y retiro de residuos. Se conserva el formato. |
| `secondaryBERT/cluster_uniref50_to_uniref30_mmseqs.py` | Valida ejecutable e insumo, invoca MMseqs2 y comprueba presencia de dos resultados. El splitter usa el FASTA de representantes. No fija versión del binario, firma los insumos ni comprueba que los resultados correspondan a esta invocación. Sin cambios; no se ejecutó MMseqs2. |

Siguiente archivo del bloque C: `neural_network/MLP/dataset.py`, línea 1. Revisar en modo lectura mientras el motor histórico esté activo.

## Cargador, escalado y preflight histórico

Tres archivos revisados íntegramente, **1.845 líneas** de entrada. Cobertura acumulada **41 de 144**.

| Archivo | Contrato y alcance |
|---|---|
| `neural_network/MLP/dataset.py` | Descubre la disposición de características, lee metadatos por offset, accede a ProtT5 por posición y SecondaryBERT por grupo mediante LRU de mmap, restaura orden tras ordenar lecturas, selecciona batches 50/50 o naturales y calcula momentos por modalidad. El diagnóstico verifica cobertura por fila y finitud de batches, con limitaciones para árboles concatenados. El motor activo importa el módulo directamente, por lo que quedó en solo lectura. |
| `neural_network/MLP/fit_shuffled_scaler.py` | Ajuste TRAIN exhaustivo secuencial en modalidad separada. Usa contadores uint32 en disco y acumula por multiplicidad de grupo. Valida cobertura y publica un NPZ provisional mediante reemplazo. La preparación histórica invoca el script, pero no se ejecutó el CLI sobre datos reales. |
| `neural_network/MLP/check_preparation.py` | Preflight histórico de features, metadatos, scaler y comparación CSV opcional. Revisa dimensión, dominio de metadatos y concordancia del conjunto de chunks del scaler. No puede acreditar la población usada para ajustar el NPZ. Se mantuvo intacto por compatibilidad con el lanzador. |

Se inspeccionaron puntualmente imports, acumulación de métricas y ramas histórica/v2 de evaluación. El motor completo queda pendiente desde `neural_network/MLP/mlp_layernorm_shuffled_ladder100_dualeval.py`, línea 1.

## Motor compartido y ejecutables LR

Tres archivos revisados íntegramente, **2.332 líneas**. Cobertura semántica acumulada **44 de 144**.

| Archivo | Contrato y alcance |
|---|---|
| `neural_network/MLP/mlp_layernorm_shuffled_ladder100_dualeval.py` | Define LR afín y MLP 1792–512–128–1 para ambas modalidades, LayerNorm, ReLU y dropout. Usa BCE con logits sin pesos, AdamW y coseno con reinicios por época; el bucle no aplica AMP, clipping ni acumulación. Baraja chunks por época y balancea TRAIN por reciclaje y donantes TRAIN. Prefetch de un batch para CUDA histórico, SQLite v2 síncrono. El CLI vigente rechaza ejecución distribuida. Se revisaron ambas ramas de evaluación, cachés, acumuladores y recuperación. Sin cambios por ejecución activa. |
| `neural_network/logistic_regression/train.py` | Envoltorio LR balanceado, preflight, bloqueo, configuración y hash de scaler. Delega al motor compartido con monitor por chunk y dropout cero. La frecuencia de evaluación difiere de la MLP activa. |
| `neural_network/logistic_regression/train_natural.py` | Entrenamiento natural con una capa lineal, Adam y penalización L2 explícita, todos los TRAIN una vez por época. Selecciona por BCE de VALIDATION y evalúa TEST al final. ROC-AUC trapezoidal y average precision aproximados con 10.000 bins. Guarda estado de optimizador/cursor y exporta coeficientes. Sin cambios. |

Se revisó puntualmente la frontera de tipos del adaptador v2 ya cubierto. Siguiente punto: `neural_network/MLP/run_shuffled_pipeline.sh`, línea 1.

## Lanzadores históricos

Tres archivos revisados completos, **126 líneas** en las versiones de entrada. Cobertura acumulada **47 de 144**.

| Archivo | Contrato y alcance |
|---|---|
| `neural_network/MLP/run_shuffled_pipeline.sh` | Valida preparación existente y genera scaler TRAIN solo si falta. Bloquea el inode del propio script, configura hilos y reporta fase al fallar. No reconstituye splits ni inicia entrenamiento. |
| `neural_network/MLP/run_chunk_ladder100_dualeval.sh` | Valida layout y cantidad de chunks, fija un rank y defaults de GPU y semilla. Bloquea por directorio, lanza etapas en secuencia, prioriza recuperación sobre LAST y, para otra etapa nueva, inicializa con BEST anterior. Usa `tee` y marcadores por época. Protocolo histórico con selección TEST STAGE; preservado. |
| `neural_network/logistic_regression/run.sh` | Establece defaults de hilos y argumentos, delega a `train.py` y registra con `tee`. Python aplica el bloqueo del destino, mide hash del scaler y valida configuración al reanudar. Corregida la ruta del log al pasar `--output`. |

Se revisaron puntualmente los contratos de monitor y recuperación del motor ya inventariado. Siguiente punto: `data_pipeline/nap_cnb_v2.py`, línea 1, para auditar íntegramente la interfaz de contratos y planificación.


## Orquestación y preparación D1/v2

Cuatro archivos revisados íntegramente, **1.558 líneas de entrada**. Cobertura acumulada **51 de 144**.

| Archivo | Contrato y alcance |
|---|---|
| `data_pipeline/nap_cnb_v2.py` | CLI de lectura y planificación. Coteja manifiestos, sumas, nombres y tipos, footers, cabeceras NPY y consultas SQLite acotadas. Comprueba la clave y etiqueta declaradas de D1, dimensiones 1024 y 768, y el contrato publicado del split. Rechaza D2 por ausencia de un contrato actual. La comprobación de 25 caracteres en el catálogo secundario es puntual. No recorre filas para comprobar secuencias, etiquetas binarias, correspondencia por clave, variantes ni el determinismo de las asignaciones. |
| `data_pipeline/nap_cnb_v2_training_profiles.json` | Dos perfiles balanceados, semillas e hiperparámetros comunes y parámetros MLP de dropout y scheduler. Referencias relativas para scripts y evidencias. El JSON describe el preflight y carece de efectos operativos. Mantenerlo junto a su consumidor evita duplicar defaults del plan. |
| `docs/NAP_CNB_v2_training_guide.md` | Se cotejaron la unidad de observación de la base y de D1, el uso de TRAIN para el scaler, la ruta de datos común a LR/MLP y las políticas de evaluación. Los estados y medidas de recursos de la guía son observaciones fechadas. La guía documenta más garantías que las aplicadas por la CLI de metadatos. |
| `tests/test_nap_cnb_v2_training.py` | Fixtures de manifiestos, precedencia de perfiles y overrides, rechazo de combinaciones, aislamiento del preflight y cotejo de procedencia del scaler. El payload deliberadamente inválido en la prueba de procedencia fija el alcance de `METADATA_MATCH`. |

La CLI concentra presentación, consultas y planificación. Separar validadores especializados requeriría conservar los imports que usa el adaptador y las interfaces que usan las pruebas. Se conservó esa frontera. Siguiente archivo pendiente `tests/test_nap_cnb_v2_validation.py`, línea 1. Se añadió una prueba puntual sin contabilizar el resto del archivo.


## Pruebas de validación D1/v2

Tres archivos revisados por completo, **549 líneas de entrada**. Cobertura acumulada **54 de 144**.

| Archivo | Alcance y calidad de las pruebas |
|---|---|
| `tests/test_nap_cnb_v2_validation.py` | Fixtures de aritmética y referencias, códigos de salida, presupuesto de lectura Parquet, esquema y recuentos. Los catálogos usan claves repetidas y etiquetas de relleno; los NPY y SQLite simulados del manifiesto D1 son marcadores. Son fixtures estructurales, no evidencia de correspondencia científica. Se amplió la cobertura de esquemas, mutaciones de filas y corrupción de cabecera. |
| `tests/test_nap_cnb_v2_specialized_validation.py` | Usa NPY con cabecera real, SQLite real y Parquet de prueba; intercepta la apertura SQLite para verificar modo inmutable y rechazo de escritura. Cubre ausencia de archivos, formatos, recuentos y evidencia. Los bloques históricos y varios valores de blobs son marcadores. Se aisló cada causa de fallo del certificado SecondaryBERT y se probó pérdida de un recibo. |
| `tests/test_nap_cnb_v2_status.py` | Cubre enrutamiento de CLI, estados y restricciones de efectos secundarios mediante audit hook en subproceso. Los marcadores de texto evidencian que el estado rápido no lee payloads. Se contrastaron firma estadística, mutación y reemplazo por inode. |

Se mantuvo la reutilización de fixtures por composición entre módulos. La fragilidad principal es que varios casos solo cotejaban el estado global con múltiples causas de fallo. Se arregló un caso concreto. Se añadió una prueba puntual en `tests/test_nap_cnb_v2_batches.py`; la revisión integral de ese archivo sigue pendiente desde la línea 1.


## Batches y pruebas de preparación

Dos archivos revisados íntegramente, **506 líneas de entrada**. Cobertura acumulada **56 de 144**.

- `tests/test_nap_cnb_v2_batches.py`, líneas 1–387. Las fixtures pequeñas sustituyen solo el contrato de lanzamiento; el lector abre Parquet, NPY, SQLite y Zstd reales. Las pruebas verifican ordinals deliberadamente desordenados, concatenación, lotes cortos, almacenamiento retenido, TRAIN para escalado y ambas rutas CPU de integración. La fixture de release ejercita la fuente explícita con selección VALIDATION y TEST final. La prueba de barrera de checkpoints ya documentada no se amplió.
- `tests/test_preparation_validation.py`, líneas 1–119. La fixture compartida comprueba momentos TRAIN con multiplicidad secundaria, constantes y exclusión de filas retenidas; los mocks verifican cuándo se exige comparación CSV completa. Los casos negativos cubren ausencia, columnas, metadatos inválidos e inventario del scaler. Las dos rutas de ajuste tienen una cobertura complementaria y la preparación histórica quedó intacta.

Continuar en `tests/helpers.py`, línea 1. Es la fixture compartida de preparación que figura en el inventario.


## Fixtures compartidas y lanzadores de preparación

Dos archivos revisados íntegramente, **179 líneas**, para **58 de 144** acumulados.

- `tests/helpers.py`, líneas 1–59. Genera seis filas deterministas en un directorio temporal por prueba, con limpieza registrada antes de escribir. Emite CSV y NPY con grupo int64 en orden distinto del catálogo secundario, etiqueta int8, split uint8 y matrices float32 de 1024 y 768 columnas. El oráculo concatena mediante un orden explícito. El split sintético cruza grupos entre particiones para ejercitar el layout histórico. Parquet, NPZ y manifiestos D1 se crean en otras fixtures. El import de compatibilidad antepone una ruta a sys.path del proceso y puede influir en el orden de imports. Se conservó por sus consumidores del alias histórico.
- `tests/test_preparation_launcher.py`, líneas 1–120. Cubre ausencia, formato y conservación de fuentes con rutas temporales y Bash real. El stub de LR verifica destino de log y código de salida sin ejecutar el entrenador. Las instantáneas comparan bytes y excluyen locks. La ruta MLP prueba preparación y ajuste diminuto con la fixture, con exclusión del bloqueo concurrente como caso independiente.

El lector Zstd recibió pruebas puntuales en el archivo de batches ya revisado. Continuar en `tests/test_dataset_and_mlp.py`, línea 1.


## Pruebas de entrenamiento y evaluación LR/MLP

Tres archivos revisados íntegramente, **394 líneas de entrada**. Cobertura acumulada **61 de 144**.

- `tests/test_dataset_and_mlp.py`, líneas 1–94. Oráculo de embeddings exactos con orden arbitrario y petición duplicada, modalidades separadas/concatenadas, momentos TRAIN ponderados por ocurrencia, marcador incompleto y paso CPU de MLP. El roundtrip manual coteja modelo, RNG y scheduler. Se añadió cotejo de cursor y momentos AdamW y comprobación de gradientes presentes.
- `tests/test_logistic_regression.py`, líneas 1–108. CLI natural temporal con batch final incompleto de TRAIN, VALIDATION por época, TEST al final, extensión de corrida y rechazo al cambiar tasa de aprendizaje. El oráculo de métricas calcula confusión, ROC-AUC y average precision de histograma. El caso multi-GPU usa un checkpoint temporal portable.
- `tests/test_logistic_regression_balanced.py`, líneas 1–192. Verifica métricas compartidas, agregación exacta ROC-AUC con empate, sampler y donante, monitor TEST estratificado, launcher y extensión de corrida. Se incorporó conservación de etiqueta por fila y rechazo implícito de filas ajenas a TRAIN para la fixture de un chunk.

Los tests de paso elemental no recorren las ramas de AMP, clipping ni reanudación completa. El motor histórico revisado previamente no aplica AMP ni clipping en esta ruta. Se dejó la selección histórica y el hook v2 bajo sus tests existentes. Siguiente punto `tests/test_data_preparation.py`, línea 1.


## Pruebas de preparación y seguimiento

Dos archivos revisados completos, **214 líneas de entrada**. Cobertura acumulada **63 de 144**.

- `tests/test_data_preparation.py`, líneas 1–176. Revisa restauración CSV/chunks, publicación interrumpida con fallo inyectado, fixtures de aumento, asignación por primaria y reparto histórico por fila, tipos de metadatos y coordenadas inclusivas. Las pruebas usan datos temporales y oráculos explícitos. No recorren datasets certificados. Se reforzaron el tamaño de lote y los códigos uint8 fuera de dominio.
- `tests/test_audit_followup.py`, líneas 1–38. Verifica solapamiento y coordenadas, ausencia parcial, límite de igualdad de vectores, distancias y coseno indefinido. Sus fixtures comprueban cálculos locales sin depender de artefactos externos. No se detectó duplicación que justificara extraer utilidades.

Se añadió una prueba puntual de average precision al archivo de LR natural previamente contabilizado. Siguiente archivo pendiente `tests/test_embedding_concatenation.py`, línea 1.


## Concatenación y almacenamiento ProtT5

Dos archivos revisados íntegramente, **437 líneas de entrada**. Cobertura acumulada **65 de 144**.

- `tests/test_embedding_concatenation.py`, líneas 1–338. Compara matrices completas con oráculo independiente, grupos no consecutivos, metadatos intercambiados, formas y finitud. Las pruebas de publicación cubren interrupción, reanudación, bloqueo y verificación rápida frente a SHA-256 completo, con comprobantes nuevos y antiguos. Las fixtures ejercitan archivos reales temporales y los mocks limitan fallos, argumento CLI o instrumentación de hash. Se añadieron distintas longitudes de lote con NPY Fortran y un intercambio que aísla el payload.
- `tests/test_prott5_v2.py`, líneas 1–99. El encoder simulado registra claves y produce matrices deterministas. Se comprueban reanudación por lote, corrupción posterior, shard ausente, direcciones fraccionarias, preservación del índice histórico y diferencia entre entrada normalizada e identidad original. No cubre inferencia del modelo ni su procedencia científica.

Continuar en `tests/test_source_audits.py`, línea 1.


## Pruebas de fuentes y observaciones modificadas

Dos archivos revisados íntegramente, **206 líneas de entrada**. Cobertura acumulada **67 de 144**.

- `tests/test_source_audits.py`, líneas 1–167. Las fixtures CSV/FASTA/Parquet verifican isoformas, versiones y ausencia de transferencia entre padres. NPY, pandas y SQLite verifican colisión de digest, distinción por modalidad y etiqueta, filtro de originales y comparación por dirección. Se añadió rechazo de posición destino inválida. No se ejecutaron auditorías sobre datos reales.
- `tests/test_iedb_modified_audit.py`, líneas 1–39. Cubre clasificación de anotación modificada, clave con referencia/versiones y coordenadas, y distinción de ensayos repetidos y entidades distintas. La fixture SQLite evita dependencias remotas. Los recuentos de clases tienen oráculo explícito.

Siguiente ruta `tests/test_iedb_download_audit.py`, línea 1.


## Descarga y evidencia pendiente IEDB

Dos archivos revisados íntegramente, **123 líneas de entrada**. Cobertura acumulada **69 de 144**.

- `tests/test_iedb_download_audit.py`, líneas 1–65. Fixtures en memoria para preservación de versión de fuente, coordenadas ausentes, nombre ambiguo, diferencia de filtro, límites de ventana y paginación. Se comprueba orden, identidad y manifiesto de páginas, además de rechazo de objetos que no son registros. El callable local simula el límite de transporte. No prueba la red ni escribe datos.
- `tests/test_iedb_pending_evidence.py`, líneas 1–58. Referencias y consultas representadas por diccionarios y objetos `Reference`. Oráculos explícitos de posición, falta de referencia, contexto incompatible y alcance familiar de claves. La fixture no valida formatos HTTP, la completitud del corpus ni la identidad de vectores. Mantener independientes los casos evita acoplar sus mutaciones.

Siguiente ruta `tests/test_global_epitope_labels.py`, línea 1, según el inventario.


## Etiquetas globales y reconciliación estructural

Dos archivos revisados íntegramente, **192 líneas de entrada**. Cobertura acumulada **71 de 144**.

- `tests/test_global_epitope_labels.py`, líneas 1–143. CSV temporal para todas las familias, preservación de texto, agrupación exacta, conflictos y evidencia agregada. Prueba recuperación de exportación y del índice SQLite en disco/RAM, manipulación de Parquet, límites por fuente y separación de directorios. Las nuevas aserciones comparan pares de etiquetas por fila y tipos físicos; se añadió cobertura de CSV vacío y tokens inválidos.
- `tests/test_rebuild_iedb_structures.py`, líneas 1–49. Gzip, CSV y Parquet temporales con un registro local simulado. Verifica ambigüedad, incompatibilidad, ausencia y requisito de referencia verificada. La reconciliación coteja recorte, etiqueta y cardinalidad de pares. No verifica valores de embeddings.

Siguiente ruta `tests/test_recover_structures.py`, línea 1.


## Recuperación estructural e integridad de SecondaryBERT

Dos archivos revisados íntegramente, **177 líneas de entrada**. Cobertura **72 de 144** del inventario base, más un archivo local fuera del inventario.

- `tests/test_recover_structures.py`, líneas 1–38. Cubre alias por identidad completa, conflicto de estructuras, longitud, coordenadas y rechazo de sobreescritura de una predicción. Las nuevas fixtures prueban publicación sin pendientes y Parquet de posiciones dispersas con recuento esperado.
- `tests/test_secondary_mlm_integrity.py`, líneas 1–139. Archivo local fuera del inventario. Cubre máscaras vacías, pérdida y perplejidad de logits simulados, interrupción y repetición del constructor, predicciones malformadas e IDs duplicados. Se ejecutan operaciones CPU, ramas de publicación y mocks de transporte al modelo. Las pruebas no cargan pesos ni comprueban DDP real, identidad de vectores o recuperación de checkpoints.

Siguiente ruta del inventario `tests/test_rebuild_iedb.py`, línea 1.


## Reconstrucción y documentación de pruebas

Dos archivos del inventario revisados íntegramente, **273 líneas de entrada**. Cobertura **74 de 144**, más un archivo local adicional revisado anteriormente.

- `tests/test_rebuild_iedb.py`, líneas 1–242. Las fixtures locales cubren referencias exactas, proyección, evidencia ambigua, límites de ventanas, duplicados de evidencia, holdouts, agrupación global, configuración de reanudación y separación de entradas y salidas. El stub de registro mantiene fuera la red y deja reales JSONL gzip, Parquet y reconciliación. El oráculo recorre ahora todas las ventanas del caso simple.
- `tests/README.md`, líneas 1–31. Documenta dependencias, tests sintéticos, checksums rápidos frente a completos, preparación y checkpoints. Se añadió el alcance de las pruebas de reconstrucción y staging.

Se amplió puntualmente `tests/test_recover_structures.py`, ya contabilizado. Siguiente ruta `data_pipeline/docs/data_and_models.md`, línea 1.


## Inventario de datos y entrada del pipeline

Dos documentos revisados íntegramente, **176 líneas de entrada**. Cobertura **76 de 144** del inventario, más un archivo local revisado anteriormente.

- `data_pipeline/docs/data_and_models.md`, líneas 1–123. Revisadas procedencia, formatos, rutas, ventanas, splits, embeddings, integridad, modelos y métricas de validación. Contraste con reconstrucción, vistas D1, motor, lectores y tests previos. No se recertificaron cifras de logs históricos.
- `data_pipeline/README.md`, líneas 1–53. Revisado diagrama, rutas de módulos, entorno, interpretación de datos y alcances de partición.

Siguiente ruta `data_pipeline/scripts/README.md`, línea 1.


## Guías de ejecución y particionado

Dos archivos revisados íntegramente, **119 líneas de entrada**. Cobertura **78 de 144** del inventario, más un archivo local revisado en tandas anteriores.

- `data_pipeline/scripts/README.md`, líneas 1–83. Contraste de secuencia de módulos, prerrequisitos, rutas y argumentos de los cuatro diagnósticos con los parsers y rutas de salida. Las referencias de entrenamiento y embeddings se cotejaron con el inventario técnico existente.
- `data_pipeline/scripts/data_splitting/README.md`, líneas 1–36. Contraste de las tres CLI, ratios y semilla, escritura del CSV y arrays, chequeo posterior y escalado ajustado a TRAIN. Fixtures existentes de preparación cubren estas fronteras.

Siguiente ruta `data_pipeline/scripts/data_archiving/README.md`, línea 1.


## Archivado y restauración

Dos documentos revisados íntegramente, **47 líneas de entrada**. Cobertura **80 de 144** del inventario, más un archivo local revisado anteriormente.

- `data_pipeline/scripts/data_archiving/README.md`, líneas 1–28. Contraste con CLI, selección, compresión, recibos, retirada y restauración histórica.
- `data/used_data/README.md`, líneas 1–19. Contraste de checksum y extracción GNU tar con el flujo de archivos históricos y alcance de publicación.

Se inspeccionaron puntualmente archivador y tests ya contabilizados. Siguiente ruta `data/README.md`, línea 1.


## Inventarios de datos y pesos locales

Dos archivos revisados íntegramente, **32 líneas de entrada**. Cobertura **82 de 144**, más un archivo local revisado anteriormente.

- `data/README.md`, líneas 1–18. Cotejados árboles, exclusión Git, procedencia documental, metadatos, marcadores, archivos históricos y consumo de la MLP. Se enlazó el contrato D1 y se separó del histórico y de D2.
- `model/README.md`, líneas 1–14. Cotejados formatos, entornos, rutas, exclusión Git y carga de checkpoints. Se distinguió la ruta local y verificada de ProtT5 v2 de la ruta histórica.

Siguiente archivo `reports/README.md`, línea 1.


## Inventario de informes y resultados

Dos archivos revisados íntegramente, **29 líneas de entrada**. Cobertura **84 de 144**, más un archivo local revisado anteriormente.

- `reports/README.md`, líneas 1–12. Cotejados columnas, cardinalidades y alcance del CSV histórico agregado. Se enlazaron procedencia e interpretación de resultados.
- `results/README.md`, líneas 1–17. Cotejados rutas y artefactos de la MLP histórica con las auditorías del motor y lanzadores, y contraste con v2 y LR natural. Se documentaron selección, solapamiento y requisitos de trazabilidad.

Siguiente ruta `docs/mlp_experiment_history.md`, línea 1.


## Historial experimental y ejemplo sintético

Dos archivos revisados, **992 líneas de entrada**. Cobertura **86 de 144**, más un archivo local revisado anteriormente.

- `docs/mlp_experiment_history.md`, líneas 1–968. Revisados cronología, tablas, definiciones de poblaciones, decisiones, comandos históricos y disponibilidad de fuentes. Se cotejaron mediante lectura y comprobación numérica las tres trayectorias TEST de la sección 17 y la suma de las matrices de confusión Best/Last.
- `examples/README.md`, líneas 1–24. Revisados requisitos, opciones y distinción de inferencia CPU sintética, entrenamiento y prueba de recuperación. No hubo cambios en este documento.

Siguiente ruta `examples/synthetic_mlp.py`, línea 1.


## Ejemplo sintético y CI CPU

Dos archivos revisados íntegramente, **198 líneas de entrada**. Cobertura **88 de 144**, más un archivo local revisado anteriormente.

- `examples/synthetic_mlp.py`, líneas 1–145. Generación sintética en dos chunks, loader por filas, alineamiento, scaler TRAIN, inferencia CPU, semillas, argumentos y temporales. Se añadió la comprobación de split por ID al oráculo.
- `.github/workflows/cpu-checks.yml`, líneas 1–53. Revisados disparadores, permisos, cancelación, dependencias instaladas, pruebas CPU, sintaxis e inferencia. La lectura estática no acredita ejecución en GitHub. No se modificó CI.

Siguiente ruta `env/README.md`, línea 1.

## Entornos, contratos operativos y diagnósticos


### Entorno, formato y ejemplo

- `env/README.md` — líneas 1–52
- `env/nap_env.yml` — líneas 1–237
- `env/proteinunet_env.yml` — líneas 1–11
- `env/requirements-ci.txt` — líneas 1–8
- `.gitignore` — líneas 1–62
- `pyproject.toml` — líneas 1–7
- `examples/benchmark_block_reader.py` — líneas 1–72
- `tests/__init__.py` — archivo vacío, marcador de paquete

### Guías de modelos y preparación histórica

- `neural_network/README.md` — líneas 1–7
- `neural_network/logistic_regression/README.md` — líneas 1–31
- `neural_network/MLP/README.md` — líneas 1–69
- `data_pipeline/scripts/data_download/README.md` — líneas 1–23
- `data_pipeline/scripts/embedding_concatenation/README.md` — líneas 1–56
- `data_pipeline/scripts/data_shuffling/README.md` — líneas 1–32
- `data_pipeline/scripts/data_augmentation/README.md` — líneas 1–31
- `data_pipeline/scripts/data_classification/README.md` — líneas 1–38
- `data_pipeline/scripts/secondary_structure_prediction/README.md` — líneas 1–36
- `data_pipeline/scripts/embeddings/README.md` — líneas 1–88
- `data_pipeline/scripts/secondaryBERT/README.md` — líneas 1–89

### Fuentes y reconstrucción

- `data_pipeline/scripts/global_epitope_labels/README.md` — líneas 1–66
- `data_pipeline/scripts/source_audits/README.md` — líneas 1–60
- `data_pipeline/scripts/rebuild_iedb/README.md` — líneas 1–67
- `data_pipeline/scripts/rebuild_iedb/pilot_selection.json` — líneas 1–41
- `docs/nap_cnb_v2_secondarybert.md` — líneas 1–34

### Evidencia y diagnósticos

- `reports/reorder_chunk_label_counts_20261110.csv` — líneas 1–14500
- `data_pipeline/scripts/check_group_splits.py` — líneas 1–134
- `data_pipeline/scripts/check_sampled_modalities.py` — líneas 1–195

Se contrastaron formato de snapshots, paquetes directos, exclusiones de artefactos, opciones CLI y límites de publicación. El benchmark lee únicamente NPY sintéticos temporales, informa medianas y RSS de proceso y no acredita rendimiento en producción. Se revisaron fases históricas, correspondencia de claves, muestras, reanudación y relación con D1 y D2. El CSV se verificó registro por registro, incluidos orden, consistencia, porcentaje y chunk final. Los diagnósticos comparan grupos o vectores muestreados mediante referencias locales y escriben informes por archivo.

### Diagnósticos históricos adicionales

- `data_pipeline/scripts/find_label_contradictions.py` — líneas 1–191. Extracción de CSV, firmas de reanudación, acumulación transaccional SQLite, exportación de filas y procedencia.
- `data_pipeline/scripts/measure_primary_mutations.py` — líneas 1–160. Muestreo fijo, chequeo de direcciones, comparación descriptiva, escalado e informes. Reutiliza el orden histórico y depende de la correspondencia declarada.

Total de esta tanda **29 archivos y 16.397 líneas de entrada**. Cobertura **117 de 144**, más un archivo local previo. Continuar en `data_pipeline/scripts/iedb_download_audit/audit.py`, línea 1.


## Auditoría de descarga IEDB y diagnósticos

Revisados íntegramente cinco archivos del inventario. Cobertura acumulada **122 de 144**, con un archivo local contabilizado por separado.

- `data_pipeline/scripts/iedb_download_audit/audit.py` — líneas 1–327. Relectura del tar, preservación de claves y procedencia, filtros comparativos, recuentos y publicación.
- `data_pipeline/scripts/iedb_download_audit/impact.py` — líneas 1–96. Agrupación de ventanas por padre y estado, consulta de referencias locales y salida JSON.
- `data_pipeline/scripts/iedb_download_audit/supplement.py` — líneas 1–113. Continuidad de índices por origen, vínculos y transformación de archivos de resultados.
- `data_pipeline/scripts/iedb_download_audit/live.py` — líneas 1–150. Parámetros, transporte con timeout y reintento acotado, verificación de rangos y recibos JSON.
- `data_pipeline/scripts/iedb_download_audit/report.py` — líneas 1–112. Uniones de resúmenes, comprobaciones de recuentos y texto de una campaña histórica.

Se revisaron puntualmente dos diagnósticos ya contabilizados para reproducir y corregir C28 y C29. Continuar en `data_pipeline/scripts/iedb_modified_audit/audit.py`, línea 1.


## Auditoría IEDB modificada

Cuatro archivos revisados íntegramente, **843 líneas de entrada**. Cobertura acumulada **126 de 144**, más un archivo local previo.

- `data_pipeline/scripts/iedb_modified_audit/audit.py` — líneas 1–320. Ingesta SQLite, marcadores, caché HTTP, unión de evidencias, intervalos y exportación. Se corrigió el orden de validación del marcador.
- `data_pipeline/scripts/iedb_modified_audit/blosum.py` — líneas 1–49. Selección por familia y motivo; cotejo de direcciones históricas y de metadatos por bloque.
- `data_pipeline/scripts/iedb_modified_audit/impact.py` — líneas 1–219. Consulta de Parquet, agregados por posición y clave, contrafactual y huella estimada del layout.
- `data_pipeline/scripts/iedb_modified_audit/report.py` — líneas 1–255. Agregados, tablas y relato de la campaña histórica, con comprobaciones de recuento y publicaciones individuales.

Se retomó puntualmente `iedb_download_audit/audit.py` para los dos riesgos solicitados. Continuar en `data_pipeline/scripts/iedb_pending_audit/audit.py`, línea 1.


## Evidencia pendiente y contratos publicados

Siete archivos revisados íntegramente, **1.120 líneas de entrada**. Cobertura acumulada **133 de 144**. El archivo local previo sigue separado.

- `data_pipeline/scripts/iedb_pending_audit/audit.py`, 1–413. Claves, caché, reintentos, enlaces, evidencia por coordenadas y publicación por archivo.
- `data_pipeline/scripts/iedb_pending_audit/impact.py`, 1–202. Reconciliación por posición, contrafactual, apoyo independiente y agregación por clave.
- `data_pipeline/scripts/iedb_pending_audit/report.py`, 1–139. Coherencia del resumen, tablas y límites de la campaña.
- `README.md`, 1–139 de entrada. Comandos de metadatos, estados, preflight, setup y evaluación histórica/v2.
- `docs/nap_cnb_v2_prott5.md`, 1–97. Identidad por clave, hashes y ordinals, recibos, comandos históricos y dependencias locales.
- `docs/nap_cnb_v2_consistencia_estructural.md`, 1–60. Evidencia limitada a la muestra, recortes e identidad de predicciones frente a vectores.
- `docs/NAP_CNB_v2_BLOSUM62_D2.md`, 1–70. Inventario, trazabilidad, límites de reutilización y distinción explícita entre estimaciones, observaciones y escenario planificado.

Siguiente ruta `data_pipeline/scripts/source_audits/exact_embeddings.py`, línea 1.

## Auditorías de fuentes

Cuatro archivos revisados íntegramente, 1.125 líneas de entrada. Cobertura acumulada **137 de 144**.

- `data_pipeline/scripts/source_audits/exact_embeddings.py`, 1–428. Direcciones originales, igualdad exacta, metadatos de barajado y almacenamiento intermedio.
- `data_pipeline/scripts/source_audits/investigate_embedding_cases.py`, 1–193. Correspondencia estructural, clases de representación, métricas y resultados vacíos.
- `data_pipeline/scripts/source_audits/omitted_epitopes.py`, 1–286. Desambiguación de FASTA, límites de intervalo, evidencia y deduplicación de ventanas.
- `data_pipeline/scripts/source_audits/recover_epitope_coordinates.py`, 1–218. Ocurrencias solapadas, conciliación de categorías y agrupación de candidatos.

Siguiente ruta `docs/NAP_CNB_pipeline_refactoring_plan.md`, línea 1.

## Cierre del inventario original

Siete archivos documentales revisados íntegramente, 1.240 líneas de entrada.

- `docs/NAP_CNB_pipeline_refactoring_plan.md`, 1–232. Dependencias, etapas de migración y alcance de los validadores propuestos.
- `docs/NAP_CNB_technical_history.md`, 1–156. Cronología, definiciones de evidencia, comparabilidad de métricas y límites de D1.
- `docs/NAP_CNB_v2_BLOSUM62_storage.md`, 1–112. Formatos, unidades, estimaciones, mediciones y límites de caché.
- `docs/nap_cnb_v2_dataset_organization.md`, 1–265. Claves, procedencia, cardinalidades, asignación y contrato D1.
- `docs/nap_cnb_v2_organizacion.md`, 1–112. Inventario de fase 3B, clasificación y dependencias de conservación.
- `docs/nap_cnb_v2_reutilizacion.md`, 1–90. Alcance histórico de costes, mediciones y propuestas previas a la certificación.
- `reports/NAP_CNB_repository_audit.md`, 1–273. Alcance de la medición, dependencias, huellas y escenarios de recuperación.

Cobertura acumulada **144 de 144**. El archivo local adicional se contabiliza por separado. No queda una ruta de continuación en el inventario original.
