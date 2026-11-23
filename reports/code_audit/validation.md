# Validación

## Pruebas

Entorno `nap_env`, Python 3.10, CPU, CUDA oculto solo en el proceso de pruebas, BLAS y OpenMP con un hilo. Comando `python -B -m unittest discover -s tests -t . -v`.

| Fase | Total | Aprobadas | Fallidas | Omitidas | Tiempo |
|---|---:|---:|---:|---:|---:|
| Línea base | 152 | 150 | 0 | 2 | 46,84 s |
| Fixture nueva, antes del arreglo | 1 | 0 | 1 | 0 | 0,002 s |
| Lector, después del arreglo | 6 | 6 | 0 | 0 | 0,066 s |
| Suite final | 153 | 151 | 0 | 2 | 50,29 s |

Las omisiones corresponden a `test_multi_gpu_cli_and_portable_checkpoint` y `test_single_gpu_cli`, que requieren CUDA. El fallo deliberado previo al arreglo demostró que la fixture detecta la apertura y expulsión innecesarias. Se comprobó sintaxis Python 3.10 mediante AST y enlaces relativos desde los Markdown del snapshot.

## Benchmark

`OPENBLAS_NUM_THREADS=1 nice -n 15 python -B -m examples.benchmark_block_reader`, ocho archivos sintéticos por un total de 4 MiB, 32.768 filas por pasada. Las tasas son una comprobación acotada posterior al arreglo.

| Orden | Sin caché | Caché de cuatro aperturas |
|---|---:|---:|
| Secuencial | 1.386.866 filas/s | 10.545.402 filas/s |
| Aleatorio | 1.499.681 filas/s | 2.609.802 filas/s |

El pico RSS del proceso fue de 49,04 MiB. La apertura con validación promedió 55 µs. No se controló el estado de la caché del sistema operativo entre las mediciones históricas y esta ejecución, por lo que las cifras no demuestran una mejora de rendimiento general. La prueba de regresión compara directamente el número de aperturas.

## Artefactos y procesos

Se comprobó el estado de Git, la lista de rutas modificadas y la continuidad de la MLP por PID y registro. La suite se ejecutó con fixtures temporales. El examen de las rutas ignoradas fue nominal. No se recalcularon manifiestos, hashes de payload completos, embeddings, splits, etiquetas ni scalers.

## Continuación del bloque A

| Ejecución | Resultado |
|---|---|
| Línea base del bloque, reconstrucción, estructuras, etiquetas y archivado | 29 aprobadas, 1,25 s |
| Regresión de edición del original tras publicar el recibo, antes del arreglo | Fallo esperado. El código anterior permitió borrar la fuente modificada. |
| Archivado, concatenación y estructuras tras el arreglo | 39 aprobadas, 3,23 s |
| Suite CPU completa | 154 pruebas, 152 aprobadas, 0 fallos y 2 omitidas por CUDA, 45,17 s |

Las pruebas de archivado y concatenación trabajaron sobre archivos temporales. El cambio conserva los recibos existentes. Se verificaron sintaxis, imports, `git diff --check` y continuidad del proceso histórico.

## Reconstrucción y validador de splits

| Ejecución | Resultado |
|---|---|
| Línea base de reconstrucción, estructuras, recuperación y validación v2 | 21 aprobadas |
| Regresiones de protección de rutas y ranking antes de corregir | Fallos esperados en ambos casos |
| Pruebas afectadas tras las dos correcciones | 23 aprobadas |
| Suite CPU tras reconstrucción | 156 pruebas, 154 aprobadas, 2 omitidas por CUDA |
| Línea base de preparación y validación histórica de splits | 18 aprobadas |
| Regresión de arranque del validador antes de corregir | Falló `python -m` por el import; la invocación directa pasó |
| Pruebas afectadas tras el arreglo del import | 19 aprobadas |
| Suite CPU final | 157 pruebas, 155 aprobadas, 0 fallos, 2 omitidas por CUDA, 46,53 s |

Imports de los cinco módulos revisados, sintaxis Python 3.10 y `git diff --check` verificados. La MLP seguía activa (PID 3348177), con último bloque registrado 2.260/14.499 en la época 2. Las pruebas usaron fixtures y no se ejecutó el constructor o el validador sobre datos certificados.

## Particionado y metadatos

| Ejecución | Resultado |
|---|---|
| Línea base de preparación, validación histórica y v2 | 27 aprobadas |
| Prueba independiente de asignación y tres regresiones iniciales antes de corregir | El oráculo coincidió; las tres regresiones reprodujeron sus fallos |
| Pruebas afectadas tras corregir particionado | 31 aprobadas |
| Suite CPU tras particionado | 161 pruebas, 159 aprobadas y 2 omitidas por CUDA |
| Regresión de metadatos antes de corregir | La fixture reprodujo la conversión de 256 a 0 tanto para y como para split |
| Pruebas afectadas tras corregir metadatos | 32 aprobadas |
| Suite CPU final | 162 pruebas, 160 aprobadas, 0 fallos y 2 omitidas por CUDA, 49,16 s |

La fixture temporal del constructor confirmó que la comprobación de configuración acepta una edición de igual longitud y fecha restaurada (A11). Se detuvo en la frontera de extracción. Se verificaron sintaxis, imports, `git diff --check` y proceso histórico. No se ejecutaron constructores ni escrituras sobre artefactos certificados.

## Firmas y recuperación histórica

La línea base anterior tenía 162 pruebas, con 160 aprobadas y 2 omitidas por CUDA. Se reprodujeron la sobrescritura parcial de FASTA y la truncación con un hueco en el prefijo. La prueba de modo estricto falló inicialmente porque la opción aún no existía. El caso de mismo tamaño y fecha restaurada ya se había reproducido en la tanda anterior contra la barrera original.

| Ejecución | Resultado |
|---|---|
| Pruebas afectadas tras firmas y publicación FASTA | 38 aprobadas |
| Suite CPU tras firmas y publicación FASTA | 164 pruebas, 162 aprobadas y 2 omitidas por CUDA |
| Pruebas afectadas finales | 39 aprobadas |
| Suite CPU final | 165 pruebas, 163 aprobadas, 0 fallos, 2 omitidas por CUDA, 45,55 s |

Las fixtures probaron reanudación interrumpida con entrada intacta, cambios de longitud, cambio de contenido de igual tamaño con fecha restaurada, compatibilidad histórica con aviso, rechazo de cambios de modalidad y mapa incompleto de hashes. La fixture de huecos comprueba que el fallo conserva el CSV y la cola, y que un prefijo completo permite el rollback esperado. No se iniciaron descargas ni reconstrucciones reales.

## Bloque B · ProtT5 y SecondaryBERT

La fixture de ProtT5 histórico falló antes del arreglo al reusar el directorio y perder el índice. La fixture v2 de shard ausente pasó con el código existente. La primera pasada afectada aprobó 36 pruebas. La primera suite completa terminó con un error al escanear registros de avisos después del import eager de Transformers, que activó un módulo opcional dependiente de torchvision. Se movió la importación al cargador de modelos y se repitieron las pruebas.

Se reprodujo el offset negativo de SecondaryBERT v2 mediante SQLite en memoria y un NPY sintético comprimido. No se escribieron catálogos ni embeddings reales. Los casos de orden y alineación ya cubiertos por las fixtures de concatenación se incluyeron en las regresiones de esta tanda. No se ejecutó inferencia real.

### Caché acotada

Se usaron dos NPY sintéticos de 64 × 768 en float32, generados con NumPy con semillas 0 y 1. Cada uno se comprimió con Zstd y recibió un recibo temporal con SHA-256 del contenido original. Se alternaron ocho veces ambos archivos mediante `OriginalBatches.historical_archive` y `cached`, comprobando la igualdad de la última fila en cada consulta. Cada ejecución partió con caché vacía, en CPU y con un hilo BLAS.

| Capacidad | Descompresiones | Tiempo |
|---|---:|---:|
| 1 matriz | 16 | 0,1659 s |
| 2 matrices | 2 | 0,0234 s |

El conteo demuestra el efecto en ese patrón adverso. Los tiempos incluyen procesos Zstd, verificación y prueba de igualdad. No representan la latencia, RSS ni tasa de fallos de caché de los archivos reales.

Las pruebas afectadas finales aprobaron **48** casos. La segunda suite CPU completa registró **167 pruebas, 165 aprobadas, 0 fallos y 2 omitidas por CUDA**. Pasaron la sintaxis Python 3.10, los imports de los cuatro módulos y `git diff --check`. No se modificaron artefactos certificados. La MLP histórica seguía activa con PID 3348177 y registró el bloque 2.310 de la época 2 durante la revisión.

## Offsets, manifiesto histórico y LRU

La prueba histórica inicial reprodujo la aceptación del campo fraccionario. La fixture del nuevo lector usa SQLite en memoria y Zstd temporal; cubre offsets −1, −3, 2 y 5 para una matriz de dos filas, offset válido repetido, shard sin archivo, referencia a un shard inexistente y matriz de cero filas.

- Afectadas: **38 aprobadas**.
- Suite CPU: **169 pruebas, 167 aprobadas, 0 fallos y 2 omisiones por CUDA**, 53,59 s.
- Sintaxis, imports, huellas del piloto y `git diff --check` verificados. Sin lectura masiva ni escrituras en artefactos certificados.

### Caché acotada

Cuatro matrices sintéticas de 256 × 768 en float32 (0,75 MiB de valores cada una) con recibos SHA-256. Secuencia de 32 accesos: alternancia 0/1 ocho veces, luego 0/1/2/3 cuatro veces. Cada capacidad se midió en un proceso nuevo mediante `_load_secondary_archive` y la LRU `cached`. El tiempo cubre el bucle y el RSS es el pico de todo el proceso.

| Matrices | Accesos | Descompresiones | Tiempo | Pico RSS |
|---:|---:|---:|---:|---:|
| 1 | 32 | 32 | 0,6376 s | 121,83 MiB |
| 2 | 32 | 16 | 0,3189 s | 120,88 MiB |
| 4 | 32 | 4 | 0,0898 s | 121,16 MiB |

El pico pequeño incluye importación y generación de fixtures. Esa base domina y las diferencias no estiman el RSS incremental del corpus. Para un bloque histórico de 102.400 × 768, los valores ocupan 300 MiB. Las capacidades 1, 2 y 4 podrían retener 300, 600 y 1.200 MiB respectivamente, antes de buffers de descompresión y parseo NPY. El loader retiene temporalmente bytes descomprimidos y la matriz interpretada; la descompresión usa un subproceso, fuera del RSS del padre. Durante entrenamiento v2 el adaptador agrupa claves por shard dentro de cada llamada y expulsa la matriz menos recientemente usada. La selección por filas puede dispersar claves; la localidad entre lotes queda sin medir. `secondary_cache` admite 1–4 y conserva el valor predeterminado 1.

## Concatenación histórica

Las pruebas previas al cambio reprodujeron las permutaciones de grupo, etiqueta y split. La prueba de NaN/Inf pasó con el código original. Después del cambio se actualizó la fixture de clave ausente para que el índice fuente también declarase el grupo inexistente, y así siguiera comprobando el rechazo en SecondaryBERT. La primera corrida afectada detectó un error en la posición CSV que modificaba esa fixture y se corrigió la selección por nombre de columna.

- Pruebas afectadas finales: **47 aprobadas**.
- Suite CPU: **172 pruebas, 170 aprobadas, 0 fallos, 2 omisiones por CUDA**, 46,85 s.
- Sintaxis Python 3.10, imports del concatenador y `git diff --check` verificados. Se usaron NPY y CSV temporales. Se verificó continuidad de la MLP. No se ejecutaron conversiones sobre matrices reales ni se modificaron archivos certificados.

No se realizó un benchmark de los CSV reales. La nueva pasada de preparación valida la correspondencia fila a fila y la memoria queda limitada por los chunks de lectura, además de los buffers existentes de conversión.

## Entrenamiento, métricas y publicación MLM

Con tensores CPU se confirmó que la pérdida original con todas las etiquetas ignoradas es NaN. El validador anterior alcanzó la escritura de métricas con una fixture de cero máscaras. El constructor anterior dejó un directorio visible tras interrumpir la escritura de `train.parquet`. Las regresiones finales comprobaron el rechazo anterior al forward, la ausencia de publicación en validación inválida, la pérdida `ln(8)` y perplexity 8 para 25 tokens válidos, y la recuperación en un destino nuevo después de interrumpir el staging.

- Pruebas afectadas: **3 aprobadas**.
- Suite CPU: **175 pruebas, 173 aprobadas, 0 fallos y 2 omisiones por CUDA**, 47,68 s.
- Sintaxis Python 3.10, imports, huellas del piloto y `git diff --check` verificados. DDP/GPU no se ejecutaron. No se cargaron modelos reales ni se escribieron artefactos científicos.
- MLP histórica activa, PID 3348177, época 2 y bloque 2.480 de 14.499 en la última comprobación.

## UniRef30 y Gloo

El predictor original aceptó cuatro tensores inválidos y duplicados de ID en las fixtures nuevas. El código actualizado pasó esas comprobaciones y conservó el par anterior al rechazar el segundo ID. Con IDs distintos publicó secuencias en orden. El predictor se importó con TensorFlow simulado y no se ejecutó inferencia real.

- Afectadas: **5 aprobadas**.
- Suite CPU: **177 pruebas, 175 aprobadas, 0 fallos y 2 omitidas por CUDA**, 46,11 s.
- Prueba Gloo acotada: dos procesos CPU, rendezvous por archivo temporal, timeout 10 s en el grupo y 30 s en el padre. Validó rechazo coordinado con un rank sin máscaras, aceptación cuando ambos tienen objetivos y validación global de dos ventanas y 25 tokens cuando un rank tiene cero máscaras. Modelo simulado; no prueba pasos de optimizador, scheduler, AMP ni NCCL. El programa de prueba quedó como fixture de sesión en `/tmp/nap_mlm_gloo_probe.py`.
- Sintaxis Python 3.10, imports pure-CPU, huellas del piloto y `git diff --check` verificados. No se escribieron artefactos certificados ni se hicieron descargas.

## Cargador, scalers y métricas LR/MLP

- Afectadas: **12 aprobadas**. Se verificaron dos acumuladores TRAIN con un arreglo de cuatro filas TRAIN y dos filas retenidas con NaN. Se comprobó la multiplicidad del grupo secundario repetido, la escala de constantes y la varianza poblacional. Las pruebas de métricas combinaron batches de una y tres observaciones y verificaron conteos y tasas calculables manualmente, además de clase única.
- Una fixture independiente reprodujo truncamiento de identificadores fraccionarios, Inf con escala cero y media incorrecta con pesos fraccionarios. Los tres casos quedan documentados pendientes; no se escribieron cambios sobre los módulos históricos.
- Suite CPU: **180 pruebas, 178 aprobadas, 0 fallos y 2 omisiones por CUDA**, 60,53 s. Sintaxis 3.10, imports, huellas del piloto y `git diff --check` verificados.
- La MLP histórica seguía activa (PID 3348177) en época 2, bloque 2.530 de 14.499. No se recalcularon scalers ni se ejecutaron diagnósticos que recorran archivos científicos.

## Motor LR/MLP y tipos de splits v2

- La fixture reprodujo la aceptación de `int8` negativo y `float64` antes del arreglo. Las asignaciones `uint8` y las pruebas de VALIDATION natural y TEST final siguieron pasando.
- Dos cachés sintéticas independientes construyeron el mismo manifiesto TEST, sin filas repetidas y con igual número por clase. La prueba de AUC confirmó el efecto de agregar puntuaciones globalmente frente a promediar chunks y la equivalencia entre acumuladores exactos con empate de cero.
- Se reprodujeron en temporales la identidad de caché sin cambio tras editar un NPY de split in situ y el alias cuando se retienen batches CPU. No se tocaron las cachés existentes.
- Afectadas finales: **28 pruebas, 26 aprobadas y 2 omitidas por CUDA**. Suite CPU: **183 pruebas, 181 aprobadas, 0 fallos y 2 omisiones por CUDA**, 46,93 s.
- Sintaxis 3.10, imports y `git diff --check` verificados. Los cuatro manifiestos de filas históricos se compararon en solo lectura bajo un límite de 4 MiB por archivo. No se abrieron checkpoints activos ni se recalcularon embeddings o scalers.

## Lanzadores, caché y reanudación

- Launcher LR: los dos casos de override fallaron antes de corregir la ruta. Pasaron después con rutas que contienen espacios y propagación del código 23 a través de `tee`.
- Ladder MLP: intérprete simulado y dos archivos de checkpoint falsos en temporales reprodujeron la aceptación de la etapa con origen y scaler distintos. No se leyó ni alteró ningún checkpoint real.
- Caché: fixture con archivo intacto, edición de igual tamaño, fecha restaurada, cambio de longitud, reemplazo y caché truncada. Se comprobó además el reuso incorrecto de bytes de igual tamaño y el alias de lotes CPU retenidos.
- Reanudación: fixture real CPU pequeña de dos chunks/dos épocas, con interrupción inyectada después de confirmar recuperación. Pesos, tensores AdamW, scheduler y RNG Torch coincidieron exactamente solo en esa configuración. La entrada directa aceptó batch distinto en otra reanudación de la misma fixture.
- Afectadas: **24 pruebas, 23 aprobadas y 1 omitida por CUDA**. Suite CPU: **184 pruebas, 182 aprobadas, 0 fallos y 2 omitidas por CUDA**, 49,44 s. Pasaron `bash -n`, sintaxis Python 3.10, import de fixtures y `git diff --check`.
- Manifiestos históricos STAGE/ALL leídos con un límite de 4 MiB por archivo. La MLP seguía activa en época 2, bloque 2.580 de 14.499. No hubo escrituras en artefactos certificados ni cambios del motor activo.

## CLI de metadatos y planificación D1/v2

- Antes del arreglo, el footer de dos columnas homónimas fue aceptado y las dos configuraciones con `true` y `1.0` pasaron la comprobación de versión. Las dos pruebas se ejecutaron con PyArrow disponible y configuraciones temporales.
- Afectadas **34 aprobadas**. Suite CPU **186 ejecutadas, 184 aprobadas, 0 fallos y 2 omitidas por CUDA**, 49,99 s.
- Sintaxis Python 3.10, imports, JSON de perfiles y `git diff --check` verificados. `validate-d1` devolvió PASS en modo de metadatos. Git no registró cambios en `data`, `model`, `results` ni en el scaler histórico versionado. La integridad de payloads grandes queda fuera de esta comprobación.
- La MLP seguía activa con PID 3348177. Último avance observado en el log durante la validación, época 2 de 10 y chunk 2.600 de 14.499. PID anterior de LR ausente. No se lanzaron entrenamientos reales ni se alteraron sus archivos.

## Mutaciones, footers y barrera de reanudación D1/v2

- Antes del arreglo, la lectura acotada aceptó magia inicial corrupta y los comandos aceptaron versiones JSON no enteras. Las correcciones pasaron las regresiones. Las pruebas adicionales usan Parquet, NPY y SQLite temporales, con checkpoints simulados fuera del repositorio.
- Afectadas **40 aprobadas**. Suite CPU **192 ejecutadas, 190 aprobadas, 0 fallos y 2 omitidas por CUDA**, 49,38 s.
- Pasaron sintaxis Python 3.10, imports, `git diff --check` y `validate-d1` en modo metadatos. SHA-256 del manifiesto D1 y del informe de splits coincidieron antes y después. Git no mostró cambios en `data`, `model` ni `results`. La verificación de huellas quedó limitada a esos dos documentos.
- MLP activa, PID 3348177, época 2/10, bloque 2.610/14.499 en el último log leído. PID anterior de LR ausente. No se escribieron artefactos científicos ni se interrumpieron procesos.

## Mutaciones del lector y preparación

- Reproducción anterior al arreglo: float64 e int64 binarios aceptados y booleano rechazado indirectamente por Arrow. Regresión de tipo físico aprobada tras la corrección.
- Afectadas **21 aprobadas**. Suite CPU **195 ejecutadas, 193 aprobadas, 0 fallos y 2 omitidas por CUDA**. El ensayo puntual de sustitución de código uint8 se ejecutó por separado.
- Sintaxis Python 3.10, imports y git diff --check aprobados. SHA-256 del manifiesto D1 y del informe de splits coincidieron antes y después. Git no registró cambios en data, model ni results.
- MLP histórica activa con PID 3348177, época 2/10, bloque 2.660/14.499 observado en lectura del log. No se ejecutaron entrenamientos reales ni se modificaron archivos operativos.

## Capacidad de caché y archivos comprimidos

- La regresión reprodujo aceptación de 1.5, 2.5 y true antes del cambio. Las pruebas con Zstd real cubrieron hits, evicción, relectura, truncamiento, formato inválido, tamaño discrepante, recibo incompatible, bloque válido de otra ruta y restauración.
- Pasaron **32 afectadas**. Suite CPU **197 ejecutadas, 195 aprobadas, 0 fallos y 2 omitidas por CUDA**. Los mensajes de Zstd por archivos inválidos fueron esperados.
- Pasaron sintaxis Python 3.10, imports, git diff --check y validate-d1 en modo metadatos. Coincidieron las huellas SHA-256 de manifiesto D1 e informe de splits. Git no mostró cambios en data, model ni results.
- MLP histórica activa con PID 3348177. Último log leído en época 2/10, bloque 2.660/14.499. PID histórico de LR ausente. Las escrituras de pruebas se limitaron a temporales.

## Pruebas LR/MLP y oráculos de entrenamiento

- Afectadas **15 ejecutadas, 13 aprobadas y 2 omitidas por CUDA**. Suite CPU **197 ejecutadas, 195 aprobadas, 0 fallos y 2 omitidas por CUDA**.
- Sintaxis Python 3.10, imports y git diff --check aprobados. Coincidieron las huellas SHA-256 del manifiesto D1 y del informe de splits. Git no mostró cambios en data, model, results ni neural_network/MLP.
- MLP activa con PID 3348177, época 2/10 y bloque 2.670/14.499 en el último log leído. PID histórico de LR ausente. Las ejecuciones de prueba fueron sintéticas y temporales.

## Preparación y métricas agregadas

- Antes de la corrección se reprodujo uint8 128 contado como TRAIN. Después pasaron la guarda de dominio, la comparación entre lotes y el oráculo AP.
- Afectadas **25 ejecutadas, 24 aprobadas y 1 omitida por CUDA**. Suite CPU **199 ejecutadas, 197 aprobadas, 0 fallos y 2 omitidas por CUDA**, 48,94 s.
- Sintaxis Python 3.10, imports, git diff --check y validate-datasets/validate-splits en modo metadatos aprobados. Coincidieron las huellas de manifiesto D1 e informe de splits. Git no mostró modificaciones en data, model, results ni neural_network/MLP.
- MLP histórica activa, PID 3348177, época 2/10 y bloque 2.700/14.499 en el último log leído. PID histórico de LR ausente. Pruebas confinadas a fixtures temporales.

## Concatenación y almacenamiento de embeddings

- Fixture de intercambio exclusivo de filas primarias: publicación y verificación completa aceptaron el archivo, con vectores primarios permutados y secundaria/etiquetas intactas. La fixture de tamaño de lote y orden Fortran reprodujo exactamente ambas modalidades.
- Afectadas **37 aprobadas**. Suite CPU **201 ejecutadas, 199 aprobadas, 0 fallos y 2 omitidas por CUDA**.
- Pasaron sintaxis Python 3.10, imports y git diff --check. SHA-256 del manifiesto D1 y del informe de splits coincidieron. Git no mostró modificaciones en data, model, results ni neural_network/MLP.
- MLP histórica activa, PID 3348177, época 2/10 y bloque 2.720/14.499 en el último log leído. PID histórico de LR ausente. No se escribieron artefactos de producción.

## Pruebas de procedencia y direcciones

- Antes del arreglo, el offset -1 leyó la última fila y el offset igual al tamaño produjo IndexError. La regresión exige rechazo explícito en ambas variantes.
- Afectadas **15 aprobadas**. Suite CPU **202 ejecutadas, 200 aprobadas, 0 fallos y 2 omitidas por CUDA**.
- Pasaron sintaxis Python 3.10, imports y git diff --check. SHA-256 de manifiesto D1 e informe de splits coincidieron. Git no mostró modificaciones en data, model, results ni neural_network/MLP.
- MLP activa con PID 3348177, época 2/10 y bloque 2.720/14.499 del último log leído. PID histórico de LR ausente. Se usaron fixtures temporales.

## Paginación e integridad de descargas

- El código anterior aceptó los tres payloads malformados de la fixture. Tras el cambio, los tres se rechazaron y los registros válidos y sus recibos conservaron el orden.
- **12 afectadas aprobadas**. Suite CPU **203 ejecutadas, 201 aprobadas, 0 fallos y 2 omitidas por CUDA**.
- Pasaron sintaxis Python 3.10, imports y git diff --check. Coincidieron los SHA-256 del manifiesto D1 y del informe de splits. Git no mostró cambios en data, model, results ni neural_network/MLP.
- MLP histórica activa, PID 3348177, época 2/10 y bloque 2.730/14.499 según el último log leído. PID histórico de LR ausente. Sin descargas reales.

## Etiquetas globales y reconciliación

- CSV vacío reprodujo StopIteration antes del arreglo. Pasaron la regresión, los siete tokens inválidos y las comprobaciones de tipo y etiquetas por fila.
- Afectadas **9 aprobadas**. Suite CPU **205 ejecutadas, 203 aprobadas, 0 fallos y 2 omitidas por CUDA**.
- Sintaxis Python 3.10, imports y git diff --check aprobados. Coincidieron las huellas del manifiesto D1 y del informe de splits. Git no mostró cambios en data, model, results ni neural_network/MLP.
- MLP histórica activa, PID 3348177, época 2/10 y bloque 2.740/14.499 según el último log leído. PID histórico LR ausente. Pruebas confinadas a temporales.

## Recuperación estructural y pruebas SecondaryBERT

- Reproducido IndexError con inventario sin pendientes. Después del cambio, overlay vacío y cabeceras válidas, cobertura conservada. La fixture con ventanas dispersas aprobó para recuento correcto y rechazó una fila ausente.
- **11 afectadas aprobadas**. Suite CPU **207 ejecutadas, 205 aprobadas, 0 fallos y 2 omitidas por CUDA**.
- Sintaxis Python 3.10, imports y git diff --check aprobados. Coincidieron SHA-256 del manifiesto D1 y del informe de splits. Git no mostró modificaciones en data, model, results ni neural_network/MLP.
- MLP histórica activa, PID 3348177, época 2/10 y bloque 2.790/14.499 según el último log leído. PID histórico LR ausente. Pruebas en temporales y sin inferencia real.

## Reconstrucción y publicación estructural

- Se reprodujo aceptación de una sustitución de posición válida con recuento conservado. Un fallo inyectado durante el informe dejó el destino ausente y limpió staging; una ejecución nueva publicó. El oráculo de reconstrucción pasó para todas las filas del caso simple.
- **18 afectadas aprobadas**. Suite CPU **207 ejecutadas, 205 aprobadas, 0 fallos y 2 omitidas por CUDA**.
- Pasaron sintaxis Python 3.10, imports y git diff --check. Coincidieron las huellas del manifiesto D1 y el informe de splits. Git no mostró cambios en data, model, results ni neural_network/MLP.
- MLP histórica activa, PID 3348177, época 2/10 y bloque 2.800/14.499 en el último log leído. PID histórico LR ausente. Escrituras de prueba confinadas a temporales.

## Contratos de datos y modelos

- Enlaces y anclas locales de ambos documentos comprobados. Revisados CLI de planificación y validate-d1 en modo metadatos, con PASS. No se ejecutaron comandos operativos de preparación ni se recertificaron cifras históricas.
- Afectadas **22 ejecutadas, 21 aprobadas y 1 omitida por CUDA**. Suite CPU **207 ejecutadas, 205 aprobadas, 0 fallos y 2 omitidas por CUDA**.
- Sintaxis Python 3.10, imports y git diff --check aprobados. Coincidieron SHA-256 del manifiesto D1 y del informe de splits. Git no mostró cambios en data, model, results ni neural_network/MLP.
- MLP histórica activa, PID 3348177, época 2/10 y bloque 2.830/14.499 en el último log consultado. PID anterior LR ausente.

## Guías de ejecución y particionado

- Comprobados enlaces, anclas, rutas y opciones CLI por lectura estática de los parsers. No se ejecutaron los comandos operativos de ejemplo.
- **28 pruebas afectadas aprobadas**. Suite CPU **207 ejecutadas, 205 aprobadas, 0 fallos y 2 omitidas por CUDA**.
- Sintaxis Python 3.10, imports y git diff --check aprobados. SHA-256 del manifiesto D1 y del informe de splits coincidieron. Git no mostró cambios en data, model, results ni neural_network/MLP.
- MLP histórica activa, PID 3348177, época 2/10, bloque 2.870/14.499 en el último log leído. PID anterior LR ausente.

## Archivado y restauración

- Antes de la guarda, el reemplazo irrecuperable posterior al recibo no impidió la retirada. Después, la misma regresión conservó el original.
- **44 afectadas aprobadas**. Suite CPU **208 ejecutadas, 206 aprobadas, 0 fallos y 2 omitidas por CUDA**.
- Pasaron sintaxis Python 3.10, imports y git diff --check. Coincidieron los SHA-256 de manifiesto D1 e informe de splits. Bajo data, model, results y neural_network/MLP, el único cambio observado fue documental en data/used_data/README.md.
- MLP histórica activa, PID 3348177, época 2/10, bloque 2.880/14.499 en el último log consultado. PID anterior de LR ausente. Archivado y corrupción probados exclusivamente en temporales.

## Inventarios locales

- Comprobados enlaces, anclas, rutas de datos y opciones de checkpoint. validate-d1 dio PASS en modo metadatos.
- **29 pruebas afectadas aprobadas**. Suite CPU **208 ejecutadas, 206 aprobadas, 0 fallos y 2 omitidas por CUDA**.
- Pasaron sintaxis Python 3.10, imports y git diff --check. Coincidieron las huellas SHA-256 del manifiesto D1 y del informe de splits. Cambios de esta tanda limitados a documentación e informes.
- MLP histórica activa, PID 3348177, época 2/10 y bloque 2.880/14.499 en el último log consultado. PID previo LR ausente.

## Inventario de informes y resultados

- Pasaron enlaces, recuentos del CSV histórico, sintaxis Python 3.10, imports y git diff --check. Coincidieron SHA-256 de manifiesto D1 e informe de splits.
- Afectadas **25 ejecutadas, 23 aprobadas y 2 omitidas por CUDA**. Suite CPU **208 ejecutadas, 206 aprobadas, 0 fallos y 2 omitidas por CUDA**.
- Cambios de la tanda limitados a documentación e informes. MLP histórica activa, PID 3348177, época 2/10 y bloque 2.890/14.499 en el último log leído. PID anterior LR ausente.

## Historial experimental MLP

- Pasaron enlaces locales, coherencia aritmética de las 24 matrices de confusión Best/Last y comprobación de los tres mínimos TEST STAGE y de su cobertura de épocas. Las métricas publicadas a partir de archivos eliminados no se recomputaron.
- Afectadas **12 ejecutadas, 11 aprobadas y 1 omitida por CUDA**. Suite CPU **208 ejecutadas, 206 aprobadas, 0 fallos y 2 omitidas por CUDA**.
- Pasaron sintaxis Python 3.10, imports, git diff --check y huellas del manifiesto D1 y del informe de splits. Cambios limitados a documentación e informes.
- MLP histórica activa, PID 3348177, época 2/10 y bloque 2.900/14.499 en el último log consultado. PID anterior LR ausente.

## Ejemplo sintético y CI

- El intercambio de dos filas de validación y test con misma clase pasó antes del arreglo y se rechazó después. Ejecución del ejemplo aprobada. Dos generaciones con semilla 42 produjeron NPY idénticos.
- **5 afectadas aprobadas**. Suite CPU **209 ejecutadas, 207 aprobadas, 0 fallos y 2 omitidas por CUDA**. Workflow revisado estáticamente.
- Pasaron sintaxis Python 3.10, imports y git diff --check. Coincidieron los SHA-256 del manifiesto D1 y del informe de splits. Motor histórico sin cambios.
- MLP histórica activa, PID 3348177, época 2/10 y bloque 2.920/14.499 del último log consultado. PID histórico LR ausente.

## Entorno, guías y diagnósticos

- Pasaron 51 pruebas relacionadas con guías y preparación. Para C27, 19 pruebas afectadas aprobadas. Validación global final **210 ejecutadas, 208 aprobadas, 0 fallos y 2 omitidas por CUDA**.
- Pasaron benchmark sintético de bloques, verificación registro por registro del CSV agregado, sintaxis Python 3.10, imports, lectura local de YAML/TOML/JSON, enlaces de las guías comprobadas y git diff --check. No se crearon entornos ni se ejecutaron comandos operativos de producción.
- Coincidieron los SHA-256 del manifiesto D1 y del informe de splits. Motor histórico sin cambios. La MLP seguía activa (PID 3348177), época 2/10 y bloque 2.940/14.499 en el último log consultado.

## Auditoría IEDB y regresiones de diagnósticos

- Antes de los cambios, la prueba de recuento reemplazó el CSV previo y los tres NPZ no finitos atravesaron la validación. Las regresiones pasan tras la corrección. **16 pruebas afectadas aprobadas**.
- Suite CPU **212 ejecutadas, 210 aprobadas, 0 fallos y 2 omitidas por CUDA**. Pasaron sintaxis Python 3.10, imports y git diff --check.
- Coincidieron los SHA-256 del manifiesto D1 y del informe de splits. No hubo red, descargas ni cambios en artefactos del entrenamiento. MLP histórica activa, PID 3348177, época 2/10 y bloque 3.660/14.499 en el último log leído.

## Publicación IEDB y checkpoint de ingesta

- Se reprodujeron un miembro ausente aceptado, residuos de publicación ante fallo y un marcador de ingesta escrito antes de la validación. Pasaron las fixtures temporales con tar comprimido, error de informe, destino preexistente y SQLite.
- **14 pruebas afectadas aprobadas**. Suite CPU **214 ejecutadas, 212 aprobadas, 0 fallos y 2 omitidas por CUDA**. Sintaxis Python 3.10, imports y git diff --check aprobados.
- Coincidieron los SHA-256 del manifiesto D1 y del informe de splits. MLP activa, PID 3348177, época 2/10, bloque 3.690/14.499 en el último log consultado. No se ejecutaron consultas reales ni se modificaron archivos operativos de la MLP.

## Evidencia y auditorías de fuentes

Evidencia pendiente: 9 pruebas dirigidas aprobadas. Suite CPU intermedia: 213 aprobadas, 2 omitidas por CUDA. SHA-256 D1 y splits coincidentes. PID histórico 3348177 observado en época 2/10, bloque 3700/14499.

Auditoría de fuentes: la regresión de muestra vacía falló con IndexError antes del cambio. Después, 12 pruebas dirigidas aprobadas.

## Validación global de cierre

- Suite CPU en Python 3.10: 216 pruebas ejecutadas en 48,697 s, 214 aprobadas, 0 fallos y 2 omitidas por CUDA.
- Sintaxis Python 3.10: 91 archivos Python del inventario analizados. Imports de los siete módulos de auditoría de esta sesión correctos.
- Inventario: 144 rutas versionadas únicas. `git diff --check` sin incidencias.
- SHA-256 del manifiesto D1 y de `splits/validation.json` iguales a la referencia tomada al inicio. La verificación se limita a esos dos archivos.
- MLP histórica observada en lectura, PID 3348177 activo, época 2/10, bloque 3710/14499. Rama `ml_model_comparison`, HEAD `49c343b`. Cambios locales sin commit ni push.
