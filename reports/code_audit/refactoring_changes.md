# Cambios y compatibilidad

| Archivos | Antes | Después | Pruebas y alcance |
|---|---|---|---|
| `data_pipeline/block_reader.py`, `tests/test_block_reader.py` | Una solicitud fuera del presupuesto de bytes abría un archivo nuevo y alteraba la LRU antes de fallar. El cálculo de tamaño de fila estaba duplicado. | La solicitud falla antes de tocar la caché o el disco. El cálculo de bytes de fila se comparte entre apertura, lectura y planificación de lotes. | Fixture con caché de un descriptor y fixture de lotes existentes. Los rangos válidos, el formato NPY y la API pública conservan su contrato. |
| `docs/README.md`, `docs/architecture/README.md`, `README.md` | Las rutas y los puntos de entrada estaban dispersos. | Índice y mapa de dependencias con las rutas históricas intactas. | Verificación de enlaces locales. |
| `reports/code_audit/` | Sin inventario de cobertura de este snapshot. | Inventario, hallazgos, validación y límites de revisión. | Comprobación de filas y referencias de los informes. |

Se mantienen las rutas de todos los scripts. Durante este trabajo no se modificaron el motor histórico, sus configuraciones, checkpoints ni artefactos certificados. Los cambios quedan en el árbol local.

## Continuación del bloque A

`data_pipeline/scripts/data_archiving/archive_inputs.py` compara también `ctime_ns` durante la compresión y antes de eliminar el original. El cambio evita borrar una fuente con edición del mismo tamaño y fecha de modificación restaurada. `source_signature` en los recibos mantiene sus cuatro valores previos y los reintentos mantienen la comprobación SHA-256 del comprimido. El contrato de árbol inactivo sigue vigente: comprobar y eliminar son operaciones separadas y no ofrecen exclusión frente a un escritor externo.

`tests/test_archiving.py` simula la edición tras publicar el recibo, comprueba la conservación del original y rechaza reusar el comprimido obsoleto en un reintento.

## Reconstrucción y validador de splits

- `rebuild.py` extiende la barrera de separación de entrada y salida a los directorios opcionales. Conserva firmas y formatos de manifiestos existentes.
- `final_selection.py` omite denominadores cero en el ranking del informe. Conserva las filas y cálculos de selección.
- `check_master_split.py` admite import por paquete y mantiene el import que usa la invocación como script. Conserva la lógica y el contrato histórico de los splits.
- `tests/test_rebuild_iedb.py` y `tests/test_data_preparation.py` reproducen los tres fallos con fixtures temporales y `--help`.

## Particionado y metadatos

- `split_nap_cnb_v2.py` rechaza claves nulas y etiquetas fuera del dominio binario. El histograma no necesita materializar pesos unitarios en el caso no ponderado. Una prueba de referencia verifica la asignación histórica de las claves válidas.
- `split_data.py` exige un vector de etiquetas. El generador histórico, sus semillas y el redondeo siguen iguales.
- `prepare_chunk_metadata.py` lee valores de etiqueta y split en `int64` para poder validar antes de convertir a `uint8`. Se conservan los nombres y dtypes de los NPY válidos.
- `tests/test_data_preparation.py` incluye el oráculo de hash y las cuatro regresiones. No se movieron scripts.

## Firmas y publicaciones

- `rebuild.py` añade `--verify-input-content`. Si se usa en un destino nuevo, el manifiesto v2 recibe una sección opcional `input_sha256` asociada a las rutas resueltas. Las listas históricas `[ruta, tamaño, mtime_ns]` conservan su forma y los consumidores `recover_structures` y `final_selection` mantienen sus contratos. Una reanudación debe conservar la modalidad original. En modalidad de metadatos se acepta el manifiesto histórico y se emite un aviso. Pasar de metadatos a contenido exige un destino nuevo porque los hashes leídos hoy no acreditan la entrada anterior.
- El CLI lee los archivos seleccionados en bloques de 1 MiB y repite la verificación antes de la finalización. El presupuesto de I/O es dos pasadas completas en una ejecución que llega a finalizar. El archivo crudo local mide 110.874.377 bytes según `stat`, lo que implica unos 222 MB decimales de lectura adicional por ese archivo, más FASTA y estructuras. El coste en otros proyectos depende del tamaño. No se leyó el contenido del archivo crudo real ni se generaron hashes de producción.
- `fetch_parent_proteins_fastas.py` crea el directorio en el punto de publicación, escribe un CSV temporal contiguo y lo renombra al final. Una excepción limpia el temporal y conserva un CSV previo. Una terminación abrupta puede dejar un temporal sin publicar. No se añadió fsync ni se promete durabilidad frente a pérdida de energía.
- `resume_reorder_chunks.py` comprueba todos los nombres canónicos comprometidos antes de truncar o limpiar. No se cambiaron formatos, algoritmo de mezcla ni configuraciones científicas.

## Generador ProtT5 histórico

`generate_prott5_embeddings.py` reserva su directorio de salida con creación exclusiva. Se eliminan el borrado del índice maestro y el salto de chunks por mera presencia del NPY. El cambio exige un destino nuevo incluso si el directorio preexistente está vacío. Las ejecuciones válidas conservan cálculo, formatos, nombres y jerarquía de salida. La prueba de regresión ejecuta el rechazo antes de cualquier tokenización o inferencia. Los módulos v2 y SecondaryBERT mantienen su código y sus huellas.

La importación de Transformers se trasladó a `load_model_and_tokenizer`. La API y los argumentos del modelo se conservan. Importar el módulo histórico para preparar una fixture o validar rutas ya no activa módulos opcionales de Transformers.

## Lector SecondaryBERT y validador histórico

Se extrajeron las operaciones ya usadas por el adaptador de lotes para resolver claves y cargar archivos comprimidos. `read_secondary_embeddings` las expone para lectura autónoma validada. Se mantiene una sola descompresión por archivo solicitado en una llamada y se reutiliza la LRU del adaptador cuando corresponde. El adaptador conserva la configuración predeterminada y la comprobación de finitud de las características concatenadas. Se distingue un shard inexistente de una clave sin vector nuevo.

El validador histórico comprueba que `chunk_id/start/end/n_rows` sean enteros no negativos antes de ordenarlos o convertirlos. La documentación dirige las lecturas autónomas al lector nuevo. Los módulos firmados y sus consumidores de generación se preservan.

## Cotejo de metadatos del concatenador

Se añadió `source_metadata_rows` para recorrer los índices por chunk y cotejar posiciones, grupos y etiquetas. En conversiones rápidas nuevas o incompletas se compara cada NPY preparado con `master_index.csv`, y el split se coteja contra `master_split.csv` cuando está disponible. Si falta el CSV de splits se conserva la validación histórica de dominio sin atribuirle una comprobación de identidad. Se detectan faltantes y sobrantes de chunks preparados en conversiones completas. Se conservan los formatos, el modo in-place, las huellas y la ruta de verificación de entregas completas. Se añade una pasada de CSV por conversión en curso, con memoria acotada por el tamaño de los chunks y bloques CSV.

Las regresiones permutan dos IDs, dos etiquetas y dos códigos válidos, y comprueban que cada caso se rechaza antes de publicar el NPY correspondiente. También se probó NaN en ProtT5 e Inf en SecondaryBERT. Las pruebas existentes conservan cobertura de grupos repetidos, grupo ausente, dimensiones, interrupciones y verificación por recibos.

## MLM

- `train_secondary_mlm.py` añade una guarda anterior al forward y desplaza la carga de Transformers a los puntos de uso. Los batches válidos conservan máscaras, arquitectura, pérdida y updates.
- `validate_secondary_mlm.py` exige objetivos enmascarados al terminar la agregación. Usa el denominador real y mantiene la semántica de los informes válidos.
- `build_secondary_mlm_dataset.py` prepara Parquet y vocabulario en staging hermano. Un fallo anterior al renombrado deja ausente el destino definitivo. Para repetir un build hay que elegir una ruta nueva. No se añadió durabilidad frente a pérdida de energía.
- `tests/test_secondary_mlm_integrity.py` usa un modelo simulado, tensores y archivos locales temporales. No se cambió ningún peso o informe publicado.

## Predicción UniRef30

`predict_uniref30_secondary_structure.py` valida IDs dentro del chunk y forma y finitud de salidas del modelo. Guarda ambos CSV en un directorio temporal hermano antes de publicar. Una excepción durante el parseo conserva el par previo. Se exige sufijo `.csv` para evitar colisión entre las rutas de predicciones y skips. Se preservan orden, columnas, recorte y tratamiento de residuos no estándar.

## Cargador y escalado histórico

La implementación histórica se mantuvo en solo lectura. Se añadieron fixtures al conjunto de tests existente para verificar medias, desviación poblacional, escala de constantes, multiplicidades y exclusión de filas VALIDATION/TEST, y para comprobar manualmente ROC-AUC, ponderación de pérdida, matriz de confusión, umbral y métricas indefinidas. C1–C3 tienen propuestas delimitadas y pendientes de revisión de compatibilidad.

## Motor LR/MLP protegido

No se modificaron el motor compartido, sus lanzadores ni el código histórico de preparación. El adaptador v2 ahora exige `uint8` para el campo split antes de validar los códigos y abrir el almacenamiento de features. Se añadieron fixtures de tipo incorrecto, muestra histórica TEST 50/50 fija y AUC global frente a promedio por chunk. Conviene separar en el futuro el plan de muestras, el lector de caché y el guardado/recuperación; se pospone mientras el motor esté en uso y hasta disponer de pruebas de compatibilidad.

## Lanzadores

El launcher LR mantiene el comando y su precedencia argparse, y resuelve el log en el directorio efectivo al usar `--output` o sus abreviaturas. La regresión usa un intérprete simulado y verifica rutas con espacios, la forma de argumento separado o con igual y el código de error del pipeline. No se tocaron los launchers MLP, el motor ni artefactos históricos.


## Orquestación D1/v2

La validación de nombres exclusivos quedó en el lector compartido de footers, aplicable a todos sus consumidores sin duplicar comprobaciones. La validación de versión reutiliza el control de enteros existente para los perfiles. Se mantuvieron las fronteras públicas entre la CLI, el adaptador y el motor activo. No se hicieron extracciones de módulos.


## Pruebas de validación D1/v2

Se reutilizó el validador de enteros en la lectura de versiones y se ubicó la comprobación de magia inicial en el lector común Parquet. Las pruebas de estado y catálogos conservan sus fixtures compartidas. Se eliminó un import local redundante y se aisló la precondición de las mutaciones del certificado SecondaryBERT. Sin reorganización del motor histórico.


## Contrato físico de etiquetas

La guarda de int8 se aplica en el punto de lectura común a base y D1, antes de NumPy. La fixture integral escribe el mismo tipo que el catálogo. Se añadió cobertura de mutaciones y propiedad de arrays sin añadir copias al lector ni cambiar el motor histórico.


## Capacidad y pruebas Zstd

Se restringió la capacidad en el constructor compartido v2 y se amplió la fixture existente para pasar opciones sin duplicar contratos. Se mantuvieron la LRU y la ruta de descodificación. El helper histórico y sus imports quedaron intactos.


## Oráculos de entrenamiento

Se ajustaron los tests existentes de paso y checkpoint MLP, aislamiento TEST de LR natural y alineación del sampler balanceado. El test MLP restaura RNG y número de hilos al terminar. No hubo cambios de implementación del motor ni nuevas abstracciones.


## Recuentos y oráculos de preparación

Se añadió una guarda de dominio al recuento antes de operar con uint8. Se amplió el oráculo de asignación por lotes y se añadió la prueba de colisión de histogramas con scores ordenados. La fórmula de asignación, los esquemas, los motores y las métricas se conservaron.


## Oráculos de concatenación

Se añadieron dos pruebas focalizadas y se agruparon imports repetidos. La primera compara cada modalidad con su fuente esperada, con distintos tamaños de lote y orden de memoria. La segunda documenta la aceptación de un intercambio exclusivo del payload primario. No se cambió código histórico ni se añadió una supuesta ruta de herencia D1.


## Dirección de destino de la auditoría

Se añadió una guarda local antes del registro de cobertura y de la indexación. La regresión usa SQLite en memoria y NPY temporal, con cierre explícito. No se reorganizaron los generadores, el motor ni el layout histórico.


## Forma de páginas IEDB

Se añadió una guarda en el límite del lector de páginas y se reemplazó el oráculo basado solo en longitud por aserciones de registros, orden y recibo de paginación. Los tests usan llamadas simuladas en memoria. Se conservaron las reglas científicas y no se modificó el motor histórico.


## Validación de etiquetas y entradas

El lector de cabecera del índice global ahora diagnostica fuentes vacías en el mismo límite de validación de esquema. Se añadieron oráculos de tokens y tipos y se reforzó la comprobación de etiquetas por fila. Se conservaron las reglas científicas y el entrenamiento.


## Esquema del resumen de proteínas

La publicación usa una lista explícita de campos para proteins.tsv en vez de deducirla de la primera fila. Las pruebas de producción se limitan a temporales y mantienen los formatos existentes. No se cambió el motor ni las claves científicas.


## Oráculos y documentación de reconstrucción

Se amplió el oráculo por fila de reconstrucción y los casos de recuperación para interrupción y sustitución con cardinalidad conservada. Se añadió a la guía de pruebas el alcance de las comprobaciones. Los cambios se limitaron a pruebas y documentación.


## Documentación histórica y v2

Cambios localizados en el inventario técnico y el README del pipeline. Se conservaron tablas, cifras históricas y enlaces de operación. Se añadió contexto para D1, D2, clasificadores y alcance de integridad, sin modificaciones de código ni artefactos.


## Alcance operativo de las guías

Se ubicaron notas de alcance histórico y enlaces a D1 junto a las instrucciones. Se explicitaron reemplazos, eliminación en archivado y alcance del chequeo de splits. No hubo cambios de implementación.


## Guarda previa a la retirada y documentación

Se reutilizó la firma existente para seguir el comprimido desde la verificación hasta la retirada y se conservó el esquema del recibo. Se añadió una regresión con sustitución después de la publicación del recibo. Se aclararon verificación, extracción y atomicidad por archivo en los dos documentos.


## Inventarios locales

Cambios localizados a documentación e informes. Se preservaron los formatos y rutas históricas y se incorporaron referencias al inventario D1, al checkpoint v2 y a los recibos. No se modificaron scripts ni artefactos.


## Documentación de reportes

Se añadieron notas localizadas en ambos índices para ubicar la evidencia de procedencia, interpretar checkpoints y evitar mezclar protocolos. Se mantuvieron tablas y archivos de resultados existentes.


## Alcance del historial experimental

Cambios localizados de redacción, referencia cruzada y cifra repetida. Los comandos históricos se conservan como registro. No hubo cambios en código ni se reconstruyeron resultados borrados.


## Oráculo de splits del ejemplo

Se reutiliza la asignación sintética en generación y comprobación y se añadió una regresión con dos posiciones de igual clase. No se modificó el motor histórico ni el workflow.


## Diagnóstico de grupos y guías

Conversión localizada de split validado para mantener índices enteros. Se añadió un caso uint64. Guías ajustadas para indicar salidas reemplazables, archivo destructivo, extracción en staging, alcance de manifiesto y diferencia de protocolo histórico/v2.


## Diagnósticos locales

El CSV se renombra después del recuento y se elimina el temporal si discrepa. El NPZ se abre con cierre explícito y valida media y escala. Se añadieron dos regresiones en el archivo de auditorías de fuentes.


## Publicación y marcadores IEDB

Se separó la escritura en staging de la publicación del destino, se validó el inventario de miembros y se adelantó el cotejo del recuento antes de persistir el marcador SQLite. Se añadieron dos regresiones offline. Los formatos y los criterios científicos se conservaron.


## Tipos de coordenadas y estado documental

Guarda localizada con una regresión por extremo booleano. Se aclaró que el flujo por fila es histórico y que el hook v2 ya selecciona con VALIDATION. La nota de claves secundarias pendientes ahora remite al cierre de fase 3C.

## Exportación de la investigación de embeddings

`investigate_embedding_cases.py` escribe CSV con cabeceras incluso sin casos y generaliza el título del informe a muestras de cualquier tamaño. Se añadió una regresión en `tests/test_source_audits.py`.

## Cierre documental

Se restauró la continuidad de la tabla del inventario de fase 3B y se identificaron las secciones históricas de reutilización y particiones. Las referencias remiten a los contratos publicados en 4C y 4D.
