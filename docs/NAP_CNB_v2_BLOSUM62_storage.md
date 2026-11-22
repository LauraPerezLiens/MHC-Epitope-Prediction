# NAP-CNB v2 · Acceso al corpus histórico BLOSUM62

## Inventario y trazabilidad

La auditoría anterior documenta 55.763.575 grupos y 1.449.852.950 filas, originales incluidos. Esta fase comprobó cabeceras de cuatro catálogos familiares, HLA-B, HLA-DR, H2-D y H2-IE, y cabeceras y tamaños de tres NPY concatenados, `001942`, `008282` y `002412`. Los tres eran NPY 1.0 en orden C, con 100.000 × 1.792 valores float32 y 716.800.128 bytes por archivo. La muestra cubre las cuatro combinaciones especie/clase en los catálogos y no proporciona una estimación estadística de integridad. [Auditoría previa](NAP_CNB_v2_BLOSUM62_D2.md)

| Artefacto | Formato y acceso |
|---|---|
| `data/used_data/data_intermediate.tar.zst` | Archivo de intermedios. El recibo acredita la copia de `data/data_intermediate`. Los CSV históricos `classification_*_blosum.csv` contienen `original_seq`, `blosum_seq` y procedencia familiar según la auditoría anterior. La pertenencia de cada CSV al tar no se verificó en esta fase. |
| `data/data_input_nn/{especie}/{clase}/{familia}/*_blosum_ProtT5_chunks/` | 14.503 bloques documentados. En las cuatro familias muestreadas, `master_index.csv.zst` declara `chunk_id,row_idx_in_chunk,y,protein_group_id,group_id`. Hay bloques `chunk_*_X.npy.zst` y recibos `.archive.json`. En cada familia muestreada, la cabecera de `chunk_000000_metadata.csv.zst` confirma `protein_group_id,group_id,blosum_seq,contains_epitope,epitope_pos_score`. El catálogo de direcciones y los metadatos por chunk son archivos distintos. |
| `data/data_input_nn/{especie}/{clase}/{familia}/*_SecondaryBERT_by_group/chunks/` | 551 bloques canónicos documentados. La muestra contiene `chunk_*_X_ss.npy.zst`; se documentan arrays acompañantes con identificadores de grupo. La representación es por grupo y requiere su propia dirección. |
| `data/data_input_nn_shuffled/` | 14.499 chunks históricos en un árbol archivado al nivel de archivo, con `ARCHIVED.json` y `reorder_manifest.json.zst`. Los índices maestros conservan las direcciones de origen y destino. Su lectura es secuencial dentro de cada flujo comprimido. |
| `data/data_input_nn_shuffled_concatenate/mixed/classification_mixed_ProtT5_chunks/` | 14.499 matrices NPY de acceso directo, aproximadamente 10,398 TB ya almacenados. Los recibos `chunk_*_X.json` y los arrays `chunk_metadata/*_{y,group_id,split_id}.npy` permiten comprobar esquema e integridad. El manifiesto en la raíz del árbol documenta offsets y familias. |

La clave de grupo de procedencia es `(source_dataset_id, source_group_id)`. La posición de una fila se identifica por el bloque, el offset cero basado y la versión. El manifiesto de reordenamiento documenta la transformación del grupo local al grupo mezclado. Los números de grupo y de chunk pueden repetirse entre familias y entre modalidades. El NPY concatenado permite recuperar valores, pero carece de la procedencia de origen detallada que conservan los índices maestros archivados. Un puntero físico válido tampoco acredita correspondencia con D1, unicidad de secuencia, equivalencia entre versiones de embeddings ni identidad de estructura de una variante. [Diccionario de datos histórico](../data_pipeline/docs/data_and_models.md) · [Inventario de archivos](../reports/NAP_CNB_repository_audit.md)

**Contrato documental de etiquetas.** Las variantes BLOSUM62 conservan la etiqueta de la secuencia original independientemente de la sustitución. La observación corresponde a la secuencia original y los negativos históricos tienen interpretación operacional. Una etiqueta heredada identifica el origen de la anotación y carece de evidencia experimental independiente sobre la variante. Los valores históricos de `y` tienen su propio significado y procedencia. [Auditoría de etiquetas](NAP_CNB_v2_BLOSUM62_D2.md)

## Arquitectura propuesta

Usar un catálogo versionado de archivos, otro de bloques y referencias por intervalo. Registrar una vez por archivo su ID, ruta relativa, formato, modalidad, origen, tamaño y SHA-256 con su alcance (flujo comprimido, original o ambos). Por bloque registrar ID, archivo, versión, dimensiones, dtype, inicio y número de filas. Un intervalo contiene `(block_id, offset, count)` y, cuando su procedencia está acreditada, `(source_dataset_id, source_group_id)`. En comprimidos el offset es una fila lógica. La búsqueda de grupo puede devolver varios rangos. Las claves de índice se deben declarar únicas solo a su escala, con la versión en la identidad y con las referencias verificadas contra el catálogo.

Empezar por un catálogo solo de bloques. Las lecturas contiguas del NPY independiente usan un seek por rango. Para muchas referencias dispersas, agrupar por bloque y ordenar por offset dentro de cada ventana de trabajo acotada, conservando la posición de solicitud cuando haya que recomponer el orden. La caché propuesta guarda hasta cuatro descriptores y cabeceras. Para `.npy.zst`, `.csv.zst` y tar comprimido, agrupar solicitudes por archivo y decodificar secuencialmente desde un límite disponible. Un offset del NPY descomprimido no es un offset útil en Zstandard. La muestra no acredita índices de frames seekables. El lector implementado cubre el NPY directo.

| Opción | Tamaño estimado inicial | Construcción, RAM, lectura y recuperación |
|---|---:|---|
| SQLite con tablas de archivos/bloques y claves primarias | 6–15 MB para aproximadamente 29.553 bloques a 200–500 bytes efectivos por bloque, con ruta y hash en el catálogo | Escaneo de cabeceras/recibos y transacciones breves por fuente. Punto/rango por B-tree con caché de páginas configurable, por ejemplo 8 MiB. Integridad referencial habilitada, unicidad y punto de reanudación confirmados en la misma transacción. Adecuado para catálogos pequeños y enlaces dispersos. |
| Parquet particionado por fuente/modalidad, con catálogo pequeño de particiones | 3–9 MB a 80–250 bytes efectivos por bloque más hasta ~1 MB de catálogo y footers en particiones agrupadas | Recorrido por fuente y escritura por lotes. Escanea columnas y grupos de filas relevantes. Para consultas puntuales precisa podar por partición y rango de claves. RAM proporcional al grupo decodificado más buffers. Un grupo de 65.536 filas de 32 bytes implica 2 MiB crudos de datos de índice. Reanudar desde particiones terminadas, verificadas y publicadas por renombrado en el mismo filesystem. La unicidad entre particiones requiere comprobación explícita. |

Los tamaños son presupuestos de planificación, con 14.503 + 551 + 14.499 bloques de las tres modalidades/árboles principales y sin inventariar aquí todas las vistas auxiliares. Un índice opcional a nivel de fila cambia el orden de magnitud. Para 1.449.852.950 filas, 32 bytes de campos fijos por fila representan 46,4 GB crudos antes de compresión. Un escenario Parquet de 16–32 bytes efectivos por fila representa 23–46 GB y un escenario SQLite de 48–96 bytes efectivos, 70–139 GB. Son supuestos para dimensionamiento, sin medición de tamaños en el corpus. Un índice denso solo se justificaría si un piloto de consultas mostrara que los intervalos y catálogos existentes resultan insuficientes.

En el diseño inicial, agregar el catálogo y un manifiesto pequeño requiere del orden de decenas de MB. Las cuatro aperturas de la caché no crean archivos y usan solo descriptores y metadatos en proceso. El lector limita el payload a 1 MiB por lote por defecto. Los temporales pueden acotarse a una transacción SQLite por fuente o una partición Parquet en escritura. Para una hipotética partición Parquet de un millón de referencias a 32 bytes crudos por fila, reservar 32 MB de payload más buffers y metadatos del escritor. El tamaño del WAL o de índices secundarios futuros depende del presupuesto de transacción y debe medirse. `df -B1` mostró 21.800.871.657.472 bytes disponibles en el workspace y 514.649.186.304 en `/tmp`. Estas cifras reflejan disponibilidad del filesystem en ese momento.

## Implementación y medición sintética

[BlockReader](../data_pipeline/block_reader.py) abre NPY 1.0/2.0 en modo lectura y devuelve vistas NumPy de solo lectura sobre un buffer de bytes del rango solicitado. Mantiene el orden de los rangos y el byte order del dtype. Valida duplicados en el catálogo de bloques, referencias, offsets, forma, dtype y tamaño exacto de archivo. Comprueba la longitud declarada de la cabecera antes de leerla y la limita a 10.000 bytes. Un SHA-256 explícito lee todo el bloque por tramos acotados. Los fallos se registran con ID o rango y se propagan al llamador. El límite de memoria cubre cada payload. El consumo total depende de los lotes que el consumidor conserve. La reanudación usa el siguiente offset confirmado por el consumidor tras reabrir el lector. El checkpoint persistente y los catálogos en disco son parte del diseño propuesto.

Ejecutar `OPENBLAS_NUM_THREADS=1 nice -n 15 python -m examples.benchmark_block_reader` con NumPy. Se leen 32.768 filas por pasada, repartidas entre ocho NPY sintéticos de 4 MiB totales, con 32 columnas y rangos de 64 filas. Mediana de tres pasadas, orden aleatorio con semilla 42 y caché del sistema operativo sin vaciar. Las tasas miden filas entregadas al lector y excluyen el trabajo del consumidor. [Benchmark](../examples/benchmark_block_reader.py)

| Orden | Caché de aperturas | Filas/s | Mediana por rango, µs |
|---|---:|---:|---:|
| Secuencial | 0 | 1.429.977 | 42,86 |
| Secuencial | 4 | 9.208.452 | 5,59 |
| Aleatorio | 0 | 1.432.242 | 42,16 |
| Aleatorio | 4 | 2.539.708 | 7,43 |

Abrir y validar una cabecera tomó 54,37 µs de media. La resolución de un ID mediante diccionario tomó 0,043 µs de media. El pico de RSS del proceso entero, medido con `VmHWM`, fue 49,1 MiB e incluye el intérprete, NumPy, fixtures y medición. Cada rango entregó 8 KiB. La mediana de apertura y lectura del bloque sintético entero de 512 KiB fue 115,36 µs. La caché aumentó el rendimiento secuencial 6,4 veces y el aleatorio 1,8 veces en esta muestra. Las cifras no predicen disco frío, ancho de banda de árboles históricos, descompresión ni rendimiento de SQLite o Parquet. Las [pruebas sintéticas](../tests/test_block_reader.py) verifican recuperación por ID y offset, orden, dtype, límites, registro de errores, integridad y reanudación.

## Operaciones pendientes y coste

1. Medir un catálogo piloto de cabeceras y recibos en las cuatro combinaciones especie/clase con presupuesto de archivos, CPU y E/S. El catálogo de ~29.553 bloques necesita del orden de 30.000 aperturas por cada tipo de artefacto inspeccionado. Leer hasta 4 KiB de cabecera por bloque serían ~121 MB lógicos, más recibos y operaciones de metadatos. Los tiempos del filesystem histórico siguen por medir.
2. Medir SQLite y Parquet con la misma muestra de claves y con consultas puntuales y secuenciales. Reservar decenas de MB para los catálogos de bloques. Un índice completo por fila necesitaría al menos una pasada por los metadatos de procedencia y comprobaciones de unicidad. Su tiempo exige medir antes bytes comprimidos, descompresión y tasa de inserción.
3. Verificar integridad pesada únicamente con presupuesto separado. Un SHA-256 exhaustivo de las matrices concatenadas leería ~10,398 TB, unas 5,8 horas a un ancho de banda sostenido hipotético de 500 MB/s o 28,9 horas a 100 MB/s, sin sumar CPU ni contención. Las comprobaciones de cabecera de esta fase no revalidan ese contenido.

## Piloto real del 22 de noviembre de 2026

Muestra dirigida de 14 referencias. En el árbol concatenado se probaron los NPY
`000000`, `001942`, `002412`, `008282`, `014497` y `014498`. Los primeros
cinco contienen 100.000 filas y ocupan 716.800.128 bytes cada uno. El último
contiene 52.950 filas y ocupa 379.545.728 bytes. Todos tienen 1.792 columnas.
Se comprobó que cada NPY directo tenía recibo JSON junto al archivo.

En HLA-B, HLA-DR, H2-D y H2-IE se comprobó la cabecera del primer bloque
`NPY.ZST` de cada modalidad. Se cerró el flujo de descompresión tras la
cabecera. ProtT5 tenía 100.000 × 1.024 por bloque, entre 227 y 265 MB
comprimidos. SecondaryBERT tenía 102.400 × 768, salvo H2-IE con 52.656 × 768,
entre 139 y 262 MB comprimidos. Las tasas que siguen corresponden a NPY
directo.

Cada pasada leyó 20 rangos consecutivos de ocho filas por bloque, para 960
filas y 6.881.280 bytes. El orden aleatorio permutó los mismos rangos con
semilla 42. Se calentó una vez la caché del sistema operativo, sin descartarla
entre pasadas. La tabla recoge la mediana de tres pasadas. El tiempo incluye
resolución, aperturas y lectura efectiva. Por separado, 60 aperturas con
validación promediaron 226 µs y 6.000 resoluciones de rango promediaron 4,91 µs.

| Orden | Caché | ms/pasada | Filas/s | MB/s | Aperturas |
|---|---:|---:|---:|---:|---:|
| Secuencial | 0 | 13,67 | 70.227 | 503 | 120 |
| Secuencial | 4 | 3,59 | 267.079 | 1.914 | 6 |
| Aleatorio | 0 | 9,53 | 100.774 | 722 | 120 |
| Aleatorio | 4 | 5,23 | 183.623 | 1.316 | 34 |

SQLite y Parquet Zstandard (cuatro filas por grupo) se crearon en un
directorio temporal con los mismos 14 registros y seis columnas
(ID, ruta, filas, ancho, bytes y formato). Se verificó que devolvieran las
mismas filas ordenadas por ID. Cada latencia es el promedio de 100 consultas
que materializaron los resultados. SQLite mantuvo su conexión y PyArrow abrió
el archivo en cada consulta. La creación de Parquet incluyó inicialización
del proceso de conversión y escritura.

| Medición | SQLite | Parquet |
|---|---:|---:|
| Tamaño | 8.192 B | 8.074 B |
| Creación | 3,31 ms | 523,50 ms |
| Consulta puntual (1 fila) | 7,88 µs | 2.312 µs |
| Consulta múltiple (3 filas) | 12,56 µs | 3.164 µs |
| Consulta por rango (5 filas) | 11,37 µs | 3.333 µs |
| Escaneo (14 filas) | 20,28 µs | 4.064 µs |
| Pico de RSS acumulado del proceso | 78,3 MiB | 133,6 MiB |

El RSS acumulado incluye imports, lector y fases anteriores. Para comparar
memoria atribuible a cada formato hacen falta procesos aislados. Los tiempos
reflejan el patrón de reapertura observado y una muestra con caché caliente.
Para resolución puntual por ID se recomienda SQLite. Parquet sigue siendo
una opción para escanear columnas de lotes más grandes. Queda por medir la
lectura en frío, descomprimir a escala controlada y repetir la comparación
con un catálogo mayor e inicialización separada.

La suite de regresión en `nap_env` ejecutó 152 pruebas en 48,7 s. Pasaron 150
y se omitieron dos que requieren CUDA. Los hilos de BLAS y OpenMP se limitaron
a uno y se ocultó CUDA solo para el proceso de pruebas.
