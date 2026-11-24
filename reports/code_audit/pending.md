# Trabajo pendiente

**Inventario original completo.** Las rutas y tareas de revisión general que aparecen en los hitos anteriores son históricas. Los riesgos que siguen abiertos están en la sección final.

1. Completar la lectura semántica por archivo. [Cobertura](coverage.md) delimita las rutas que ya se leyeron en detalle. La clasificación del inventario es preliminar.
2. Completar el mapa de dependencias con invocaciones externas, imports dinámicos y consumidores de datos declarados en manifiestos. Las dependencias estáticas son un punto de partida.
3. Ampliar fixtures del scaler, índices, splits inválidos y reanudación de extremo a extremo. Fijar primero el comportamiento exigido por cada contrato. Preservar las pruebas y checkpoints de formatos anteriores.
4. Medir, en una ventana autorizada, picos de memoria y fallos de caché de la lectura v2. Terminar ese piloto antes de dimensionar el ajuste completo del scaler de D1.
5. Revisar documentación y tests de todos los componentes restantes. Extraer código compartido solo después de verificar equivalencia. Conservar informes que forman parte de evidencia publicada.
6. Revisar el alcance de generalización de D1 con una auditoría de similitud aprobada y separada de la entrega certificada. D2 permanece pendiente. El almacenamiento histórico dispone de un lector por rangos y una comparación piloto de catálogos. [Informe previo](../../docs/PIPELINE.md)
7. Definir la integración de PR-AUC y average precision con ejemplos de clases ausentes y un contrato de salida versionado. Probar por separado la selección de checkpoint y el momento de evaluación TEST.

## Punto de continuación del bloque A

Empezar por `data_pipeline/scripts/rebuild_iedb/rebuild.py`, líneas 1–599. Continuar con el resto del archivo y los tres módulos de selección, vistas y recuperación indicados en [cobertura](coverage.md). Añadir fixtures que interrumpan un constructor y modifiquen una fuente sin cambiar el tamaño ni la fecha. Determinar qué fases rechazan el cambio y cuáles ya publicaron resultados intermedios. Mantener la compatibilidad con manifiestos existentes y estimar el coste antes de proponer hashes completos. Los bloques B–F siguen pendientes según el orden solicitado.

## Punto de continuación tras el constructor

La lectura de `rebuild.py`, selección, vistas y recuperación está registrada. Sigue `data_pipeline/scripts/data_splitting/split_nap_cnb_v2.py` desde la línea 1. Mantener abiertas las pruebas de cambio de insumo con firma aparente conservada (A11), recuperación sin gaps (A16) y medición de RAM y rutas de vistas (A17).

## Siguiente punto tras particionado

Leer `data_pipeline/scripts/data_classification/fetch_parent_proteins_fastas.py` desde la línea 1 y luego `epitope_classification.py`. Continúan abiertos A11 (barrera de reanudación reproducida, falta estrategia compatible), A16 (fixture de recuperación sin gaps), A17/A23 (RSS de vistas y splits) y A22/A24 (interrupciones de publicación).

## Siguiente etapa

Retomar el bloque B en `data_pipeline/scripts/embeddings/primary_structure/generate_prott5_embeddings.py`, línea 1. Quedan pendientes la compatibilidad de firmas de contenido en cachés auxiliares y en otros constructores, las fixtures de logs desordenados o duplicados, la recuperación estructural sin gaps y el perfil acotado de RAM de las vistas. Las firmas opcionales nuevas protegen el reinicio del constructor, sin elevar las garantías de los validadores históricos que leen sus metadatos.

## Siguiente etapa de embeddings

Retomar `data_pipeline/scripts/embeddings/secondary_structure/check_secondary_embeddings.py`, línea 1. Después revisar predicción de estructura, concatenación y entrenamiento del encoder. Quedan B2–B5, B7 y la medición de relecturas en un patrón real de consumo aprobado. Aumentar la caché aumenta memoria retenida y no se cambió el valor predeterminado. Continúan abiertos los riesgos del bloque A de recuperación sin gaps, logs duplicados o desordenados, pico RSS de las vistas y publicación interrumpida.

## Siguiente etapa de concatenación

Retomar en `data_pipeline/scripts/embedding_concatenation/concatenate_primary_secondary.py`, línea 1. Quedan las pruebas de intercambio de vectores, el protocolo seguro de recibos de caché, la auditoría de marcadores históricos y la revisión del encoder. Conservar la llamada interna del piloto firmado y utilizar la ruta documentada validada para lectura autónoma.

## Siguiente etapa del encoder

Retomar `data_pipeline/scripts/secondaryBERT/train_secondary_mlm.py`, línea 1. Quedan la correspondencia criptográfica de los NPY históricos a nivel fuente y la reanudación ante cambios con metadatos conservados, las pruebas de publicación MLM interrumpida, y la caracterización de la evaluación sin tokens enmascarados. Los riesgos anteriores de cachés auxiliares, logs, recuperación estructural, memoria de vistas y localidad de SecondaryBERT comprimido siguen abiertos.

## Continuación UniRef30

Retomar `data_pipeline/scripts/secondaryBERT/predict_uniref30_secondary_structure.py`, línea 1. Revisar luego preparación y clustering FASTA. Quedan B18–B20, la publicación de pesos finales, una comprobación DDP real acotada, y la identidad por fila histórica (B12). Conservar las tareas anteriores de cachés auxiliares, logs, recuperación estructural, memoria y localidad.

## Continuación del bloque C

Retomar `neural_network/MLP/dataset.py`, línea 1, en solo lectura mientras la MLP esté activa. Quedan la firma por chunk y publicación conjunta de UniRef, aislamiento de restos tras repartir FASTA, recibos del clustering, prueba DDP de pasos de optimizador/scheduler, y diseño de reanudación exacta MLM. Se conservan los pendientes previos de cachés auxiliares, logs, recuperación estructural sin gaps, memoria de vistas, compatibilidad, localidad y trazabilidad histórica.

## Motor compartido LR/MLP

Retomar `neural_network/MLP/mlp_layernorm_shuffled_ladder100_dualeval.py`, línea 1, en modo lectura mientras siga activo. Completar auditoría de checkpoint, LR, evaluación, orden de batches, pesos y guardas. Mantener pendientes C1–C3 en los módulos históricos, cuantificación de homología y una auditoría separada de la procedencia del scaler sin recalcularlo. Las tareas de cachés, logs, recuperación estructural, UniRef, memoria, AMP/DDP, reanudación y trazabilidad previa permanecen abiertas.

## Continuación de lanzadores

Retomar `neural_network/MLP/run_shuffled_pipeline.sh`, línea 1, sin modificar archivos que use la MLP activa. Revisar después `run_chunk_ladder100_dualeval.sh` y `neural_network/logistic_regression/run.sh`. Mantener C1–C3 y C8–C9, exactitud de reanudación, pruebas de homología y los riesgos previos. La interpretación de BEST histórico conserva la advertencia de selección por TEST. Los riesgos de UniRef, AMP/DDP, cachés auxiliares, logs, recuperación estructural, memoria y trazabilidad previa siguen abiertos.

## Continuación de orquestación

Retomar `data_pipeline/nap_cnb_v2.py`, línea 1. Mantener C8–C9 (caché y préstamo de búfer), C11–C13 (certificación de etapa, verificación al reanudar y bloqueo de logs), validación CUDA de equivalencia y los pendientes de splits, índices, escalado, UniRef, AMP/DDP, cachés auxiliares, recuperación y trazabilidad. El protocolo BEST histórico y sus limitaciones se preservan.


## Continuación de pruebas de contratos D1/v2

Retomar `tests/test_nap_cnb_v2_validation.py`, línea 1. Continuar con las pruebas especializadas y de estado aún pendientes. Investigar metadatos que cambian entre lecturas, referencias a archivos grandes con estadísticas conservadas y discrepancias entre el estado de metadatos y la lectura del adaptador mediante fixtures. El preflight permanece deshabilitado para ejecutar entrenamientos y el motor v2 rechaza reanudaciones. Quedan pendientes la homología, la identidad de cachés, la equivalencia CUDA y los riesgos históricos, de publicación y de recuperación ya inventariados.


## Continuación del lector de batches D1/v2

Retomar `tests/test_nap_cnb_v2_batches.py`, línea 1. Completar la matriz de mutaciones sobre el lector real de la fixture: tipo físico de etiquetas, nulos, duplicados, sustituciones de código por otro válido, orden, ID y vectores. Separar la detección de contenido al abrir un lector de cualquier cambio observado tras poblar una caché. Conservar los riesgos previos de identidad histórica, reanudación y recuperación, CUDA, AMP/DDP, publicación, homología e integridad exhaustiva D1. Los ensayos acotados aquí no fijan el coste de rehashear grandes payloads.


## Continuación de fixtures de preparación

Retomar `tests/helpers.py`, línea 1. Pendientes en v2: regresión permanente para sustitución de un código uint8 válido, nulos, corruptelas y evicción Zstd, pruebas de tipos de row group y evaluación de coste de recibos por shard. Mantener trazabilidad histórica, homología, validación exhaustiva del contenido, equivalencia CUDA, propiedad de buffers históricos, reanudación histórica, AMP/DDP, publicación y recuperación. Investigar por separado el ResourceWarning de CSV de preparación.


## Continuación de pruebas de dataset y motor

Retomar `tests/test_dataset_and_mlp.py`, línea 1. La regresión base de corrupción y evicción Zstd queda cubierta. Quedan evicción LRU con capacidad mayor a uno, dimensiones maliciosas declaradas en cabecera, medición RSS, política explícita de snapshots, recibos de identidad por clave histórica, nulos y validación exhaustiva, más los riesgos históricos ya inventariados.


## Continuación de pruebas de preparación

Retomar `tests/test_data_preparation.py`, línea 1. Quedan cobertura AP agregada entre chunks, reproducibilidad CUDA, comprobaciones históricas de identidad y reanudación, trazabilidad de embeddings, memoria de caché, homología y demás pendientes previos.


## Continuación de pruebas de concatenación

Retomar `tests/test_embedding_concatenation.py`, línea 1. Quedan procedencia de históricos, homología, pruebas de herencia en rutas que conserven vínculo original-variante, identidad y memoria de cachés, equivalencia CUDA y los pendientes de entrenamiento, recuperación e integridad ya inventariados. Se caracterizó AP agregada en un caso sintético; queda medir la aproximación en distribuciones reales.


## Continuación de pruebas de auditoría de fuentes

Retomar `tests/test_source_audits.py`, línea 1. Mantener la trazabilidad independiente de embeddings históricos, picos de RAM, homología, identidad y memoria de cachés, validación exhaustiva, reanudación y equivalencia CUDA. La fixture de herencia padre–variante queda ligada a una futura ruta D2 real. Mantener abierta la evaluación de la AP aproximada sobre distribuciones reales.


## Continuación de auditorías de descarga

Retomar `tests/test_iedb_download_audit.py`, línea 1. Continúan pendientes direcciones destino duplicadas, identidad histórica independiente, validación exhaustiva D1, vínculo D2, homología, memoria y coherencia de cachés y los riesgos previos de entrenamiento y recuperación.


## Continuación de pruebas de etiquetas globales

Retomar `tests/test_global_epitope_labels.py`, línea 1. Quedan cobertura de fallos de transporte, archivos incompletos y publicación, unicidad por identificador, destinos repetidos y nulos, trazabilidad histórica, integridad exhaustiva D1, D2 y riesgos de entrenamiento, homología y recuperación ya inventariados.


## Continuación de pruebas de recuperación estructural

Retomar `tests/test_recover_structures.py`, línea 1. Mantener pendientes cobertura de nulos e IDs de procedencia, vínculos históricos de vectores, integridad exhaustiva D1, homología, D2, publicación y riesgos de entrenamiento registrados.


## Continuación de pruebas de reconstrucción

Retomar `tests/test_rebuild_iedb.py`, línea 1. Quedan interrupción completa de la publicación, sustitución de posiciones con cardinalidad conservada, procedencia de embeddings, integridad exhaustiva D1, homología, equivalencia CUDA, reanudación histórica y demás riesgos registrados.


## Continuación de contratos de datos

Retomar `data_pipeline/docs/data_and_models.md`, línea 1. Queda la verificación independiente de conjuntos de posiciones y claves en entradas históricas, semántica ante caída fuera de excepciones controladas, integridad exhaustiva D1, identidad de vectores, homología, D2 y riesgos de entrenamiento y publicación previos.


## Continuación de la guía de etapas

Retomar `data_pipeline/scripts/README.md`, línea 1. Mantener abiertos la correspondencia independiente de vectores, integridad exhaustiva y homología D1, D2, caída abrupta y posiciones con recuento conservado, cachés, recuperación y riesgos históricos de entrenamiento enumerados en los informes.


## Continuación de documentación de archivado

Retomar `data_pipeline/scripts/data_archiving/README.md`, línea 1. Mantener pendientes integridad exhaustiva y homología D1, identidad histórica y cachés, recuperación y caída abrupta, D2, métricas aproximadas y validaciones operativas ya inventariadas.


## Continuación del inventario de datos

Retomar `data/README.md`, línea 1. Permanecen pendientes la verificación ante caída abrupta, coordinación frente a escritores externos, destino parcial en extracción, correspondencia histórica de vectores, integridad exhaustiva y homología D1, D2 y riesgos operativos y de entrenamiento previos.


## Continuación de los informes de datos

Retomar `reports/README.md`, línea 1. Continúan pendientes procedencia independiente de vectores, versiones de fuentes históricas no registradas, integridad exhaustiva D1, D2, homología, caída abrupta, recuperación, cachés y riesgos operativos previos.


## Continuación del historial experimental

Retomar `docs/HISTORIAL.md`, línea 1. Queda cotejar trazabilidad de cada ejecución histórica y conservar los pendientes de identidad de datos y vectores, independencia, integridad D1, cachés, reanudación, D2 y publicación enumerados previamente.


## Continuación del ejemplo CPU

Retomar `examples/synthetic_mlp.py`, línea 1. Quedan procedencia por ejecución eliminada, reproducibilidad CUDA e histórica, trazabilidad de vectores, integridad exhaustiva D1, homología, D2, cachés y recuperación previamente inventariadas.


## Continuación del entorno CPU

Retomar `env/README.md`, línea 1. Quedan ejecución alojada de CI, equivalencia CUDA, integridad exhaustiva D1, correspondencia histórica, homología, D2, cachés, recuperación y los riesgos de entrenamiento previos.


## Continuación de diagnósticos


Retomar `data_pipeline/scripts/iedb_download_audit/audit.py`, línea 1. Quedan **27 archivos**. Añadir fixtures para exportación por recuento, extracción interrumpida y media no finita en diagnósticos antes de cambiar su contrato.


## Continuación del bloque IEDB

Retomar `data_pipeline/scripts/iedb_modified_audit/audit.py`, línea 1. Quedan **22 archivos**. Mantener los riesgos de extracción interrumpida, publicación conjunta, miembros ausentes y validación de informes IEDB, junto con los riesgos científicos y operativos anteriores.


## Continuación de auditorías de evidencia pendiente

Retomar `data_pipeline/scripts/iedb_pending_audit/audit.py`, línea 1. Quedan **18 archivos**. Pendientes técnicos: validación exhaustiva de esquemas CSV, integridad y concurrencia durante publicación, identidad de entradas y marcadores históricos, además de los riesgos científicos previos.


## Continuación de auditoría de fuentes

Retomar `data_pipeline/scripts/source_audits/exact_embeddings.py`, línea 1. Quedan **11 archivos** del inventario. Los riesgos previos de caché, publicación, trazabilidad y garantías científicas siguen abiertos.

## Continuación documental

Retomar `docs/HISTORIAL.md`, línea 1. Quedan siete archivos documentales. En las auditorías de fuentes quedan por validar con fixtures la publicación parcial, la dependencia del orden en el recuento de candidatos recuperados y las métricas para pares cuyo coseno no está definido.

## Inventario original completo

Cobertura 144/144. Las rutas de continuación anteriores registran hitos históricos. El análisis de riesgos sigue abierto para publicación conjunta e interrupciones, identidad fuerte de entradas en reanudación, discontinuidades, escalabilidad a corpus completo, equivalencia CUDA y generalización a proteínas u homólogos no vistos. D2 y la validación exhaustiva de todos los vectores quedan fuera de este cierre.
