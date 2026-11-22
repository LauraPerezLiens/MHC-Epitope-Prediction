# NAP-CNB v2 · Preparación de entrenamientos

## Uso

```bash
python -B -m data_pipeline.nap_cnb_v2 train --model lr --data original --label global --dry-run
python -B -m data_pipeline.nap_cnb_v2 train --model mlp --data original --label original --json
```

El comando es un preflight incluso sin `--dry-run`. Lee referencias, dimensiones, recuentos, splits y perfil. No importa entrenadores, crea la salida ni lanza procesos. Acepta `--root` antes o después del subcomando. `--config` y `--output` admiten rutas relativas a esa raíz. La ruta de salida se muestra como propuesta. Una ruta existente se señala como impedimento. El código 1 indica un plan bloqueado y el 2 un error de argumentos o inicio. El comando de lanzamiento permanece vacío para los contratos no utilizables.

## Inventario de datos

| Conjunto | Ruta y formato | Filas / positivas / negativas operacionales | Etiquetas, embeddings y particiones | Estado |
|---|---|---|---|---|
| Selección definitiva | `results/nap_cnb_v2_final_selection/selection.json`, familias Parquet, overlay y exclusiones | 49.123.503 / 5.587.074 / 43.536.429 | Familia y ventana; split v2 recuperable por procedencia; vectores separados 1.024 + 768 | Completa y certificada. Fuente científica |
| Base v2 | `results/nap_cnb_v2_dataset_views/base_dataset.parquet` | 49.022.360 / 5.587.073 / 43.435.287 | `label_original`; split v2 por primaria; vectores separados 1.024 + 768 | Completa, validada; hook balanceado validado con fixtures; scaler completo pendiente |
| Índice global v2 | `results/nap_cnb_v2_dataset_views/global_labels.parquet` | 14.530.324 / 3.577.364 / 10.952.960 | `label_global` por primaria; catálogo de etiquetas | Completo y validado |
| D1 | `results/nap_cnb_v2_dataset_views/global_dataset.parquet` y `d1_manifest.json` | 15.100.592 / 3.844.628 / 11.255.964 | `label_global`, semilla 42 y vectores separados 1.024 + 768 | Completo, validado; hook balanceado validado con fixtures; scaler completo pendiente |
| Originales históricos | `data/global_epitope_labels/rows/*.parquet` y CSV de `data/used_data/contradiction_sources/` | 55.763.575 / 9.855.547 / 45.908.028 | Etiqueta familiar histórica y anotación global histórica; tablas de procedencia, sin un contrato directo de lotes | Catálogo histórico validado. 11.418.263 primarias con estado global sin evidencia positiva en su esquema histórico |
| Originales y derivados históricos | `data/data_input_nn/`, `data/data_input_nn_shuffled/` y `data/data_input_nn_shuffled_concatenate/` | 1.449.852.950 / 256.244.222 / 1.193.608.728 en la vista concatenada | `y` histórico por fila, heredado en derivados; split histórico por fila. Primarias archivadas por entrada; secundaria compartida por grupo; float32 concatenado de 1.792 | 14.499 chunks completos según layout, compatibles con ambos entrenadores históricos. Los 14.503 bloques corresponden a las fuentes |
| D2 v2 | Pendiente | — | Aumento v2 con etiqueta global | No disponible |

`label_original` describe evidencia verificada en el contexto familiar. `label_global` es el máximo de las etiquetas originales por primaria exacta. Se pueden enlazar por primaria y conservar ambos campos. Las vistas v2 publicadas usan etiquetas binarias y claves con cobertura validada. La prevalencia es 11,40 % en la base y 25,46 % en D1. Sustituir la etiqueta en la base sin deduplicar por par cambiaría la unidad de observación de D1. No se interpretan estados ausentes del catálogo histórico como ceros.

En base y D1, `sequence = effective_group_id` recupera la asignación de la semilla 42. ProtT5 resuelve la primaria por catálogo ordinal e índice de rangos confirmados. SecondaryBERT resuelve la C/H/E exacta por SQLite, con vectores nuevos y referencias a archivos históricos. El preflight coteja estas referencias y dimensiones mediante metadatos. El lector v2 resuelve ambas modalidades y restaura el orden de la solicitud. La conexión con el motor ya se probó con fixtures. La entrada del motor admite una fuente v2 explícita y conserva el lector físico como ruta predeterminada. El contrato histórico, en cambio, lee matrices concatenadas con `y/group_id/split_id` alineados por posición.

Como comprobación acotada durante la preparación, se recuperó un vector original ProtT5 por ordinal y un vector nuevo SecondaryBERT por clave C/H/E en modo lectura. Ambos tenían la dimensión esperada y valores finitos, y el checksum del vector SecondaryBERT coincidió. La comprobación de los históricos SecondaryBERT usa las referencias ya certificadas y evita descomprimir sus bloques.

Los derivados históricos preservan grupo y origen. Sus secuencias primarias modificadas tienen sus propias entradas ProtT5 archivadas y reutilizan secundaria por grupo. La coincidencia con una secuencia original se determina por clave exacta. Los grupos históricos cruzaban splits y sus vectores ProtT5 no fueron certificados como intercambiables con los de v2. La vista aumentada histórica sirve para reproducir sus experimentos, mientras que la comparación con D1 requiere un dataset de aumento de evaluación compatible, actualmente ausente.

[Recuentos históricos por chunk](../reports/reorder_chunk_label_counts_20261110.csv) · [Índice histórico](../data_pipeline/scripts/global_epitope_labels/README.md) · [Auditoría de embeddings](../results/nap_cnb_v2_embedding_audit/embedding_audit_report.md) · [Organización actual](nap_cnb_v2_dataset_organization.md)

## Entrenadores y procesos auditados

| Perfil | Script y dependencias | Modelo, pérdida y optimización | Lectura, evaluación y checkpoints |
|---|---|---|---|
| `lr_balanced` | `neural_network/logistic_regression/train.py`; importa motor MLP y `check_preparation.py` | PyTorch, logit lineal 1.792 → 1, BCEWithLogitsLoss, AdamW, lr 0,001, decay 0,0001. Batch 8.192 con 50/50 exacto, 10 épocas objetivo, sin early stopping | Chunks mmap. Evalúa por chunk con muestras STAGE/ALL fijas. Loss, ROC-AUC, precisión, recall, F1 y otras métricas del motor. Recuperación y último checkpoint LR con comprobación de configuración |
| `lr_natural` | `neural_network/logistic_regression/train_natural.py`; lector y validación de preparación históricos | PyTorch, logit lineal, BCE más L2 explícito sobre pesos, Adam, lr 0,001, L2 0,0001. Batch 8.192, 10 épocas objetivo. Prevalencia natural y sin early stopping en el flujo registrado | Lee TRAIN en bloques con localidad de disco y permuta el batch en memoria. Métricas acumuladas, ROC-AUC y AP por histograma. Checkpoint de modelo, optimizador y cursor. Sustituido por el run balanceado |
| `mlp_historical` | `neural_network/MLP/mlp_layernorm_shuffled_ladder100_dualeval.py`; usa `dataset.py` y metadatos históricos | PyTorch, 1.792 → 512 → 128 → 1, LayerNorm, ReLU, dropout 0,30. BCEWithLogitsLoss, AdamW, lr 0,001 y decay 0,0001, batch 8.192 con 50/50. Coseno T0=20, Tmult=1, mínimo 0,00001. Sin early stopping | mmap, lotes y caché acotada. Evalúa STAGE/ALL y selecciona por TEST STAGE en el protocolo histórico. Loss, ROC-AUC, F1, precisión, recall y contadores. Best, last y recovery con optimizador, scheduler y RNG |

**Ejecuciones observadas.** MLP PID 3348177 usa el script de la tabla con `--model-type mlp --features primary_secondary --epochs 10 --seed 42 --eval-every epoch --max-chunks 14499 --checkpoint-every 10 --report-every-chunks 10 --secondary-cache-size 1 --eval-batch-size 1024 --eval-target-per-class 29006`. Reanuda `recovery_mlp_primary_secondary.pt` en `chunks_14499`. LR PID 3348404 usa `train.py` con `--epochs 10 --batch-size 8192 --lr 0.001 --l2 0.0001 --device auto --gpus 1 --log-every 10 --checkpoint-every 10 --resume`. Ambos apuntan a la misma raíz de chunks concatenados y al scaler histórico. La cadencia de evaluación activa es diferente. Los flags omitidos en la línea del proceso se reconstruyen con los defaults del código y la documentación, no se presentan como argumentos explícitos observados.

**Escalado.** `neural_network/MLP/standardizer_all_train_chunks.npz` guarda medias y escalas por modalidad y el inventario de chunks. El ajuste usa solo TRAIN de la representación histórica aumentada. La reutilización exige la misma representación y población de ajuste. Para v2 se indica `REQUIRES_TRAIN_FIT`. El ajuste futuro debe fijar vista, hash de asignaciones, referencias de embeddings, número de filas TRAIN, dimensiones y procedimiento. Preflight no carga ni recalcula estadísticas.

[Experimentos MLP](mlp_experiment_history.md) · [LR balanceada](../results/logistic_regression_balanced/config.json) · [LR natural](../results/logistic_regression_all/config.json) · [Lector](../neural_network/MLP/dataset.py) · [Ajuste de escala](../neural_network/MLP/fit_shuffled_scaler.py)

## Matriz de compatibilidad

| Modelo | Datos | Etiqueta | Estado para v2 | Motivo |
|---|---|---|---|---|
| LR | Original | Original | `INCOMPLETE` | Base validada 49.022.360. Splits v2 y 1.792 dimensiones separadas. Hook balanceado probado; scaler TRAIN pendiente |
| LR | Original | Global | `INCOMPLETE` | D1 validado 15.100.592. Splits v2 y 1.792 dimensiones separadas. Hook balanceado probado; scaler TRAIN pendiente |
| LR | BLOSUM62 | Original | `INCOMPATIBLE` | Histórico disponible para replay con 1.449.852.950 filas, splits y scaler históricos |
| LR | BLOSUM62 | Global | No disponible | D2 ausente. La etiqueta histórica no es la global v2 |
| MLP | Original | Original | `INCOMPLETE` | Base validada 49.022.360. Splits v2 y 1.792 dimensiones separadas. Hook balanceado probado; scaler TRAIN pendiente |
| MLP | Original | Global | `INCOMPLETE` | D1 validado 15.100.592. Splits v2 y 1.792 dimensiones separadas. Hook balanceado probado; scaler TRAIN pendiente |
| MLP | BLOSUM62 | Original | `INCOMPATIBLE` | Histórico disponible para replay con 1.449.852.950 filas, splits y scaler históricos |
| MLP | BLOSUM62 | Global | No disponible | D2 ausente. La etiqueta histórica no es la global v2 |

D1 tiene 12.083.630 / 1.507.558 / 1.509.404 filas train/validation/test. La base tiene 39.228.827 / 4.891.517 / 4.902.016. Los splits v2 separan primarias exactas y comparten proteínas. Los splits históricos tienen otro contrato. El CLI marca D2 como `INCOMPATIBLE` con un mensaje explícito de ausencia.

## Configuración y siguiente etapa

Los [perfiles versionables](../data_pipeline/nap_cnb_v2_training_profiles.json) admiten LR balanceada y MLP histórico balanceado. LR natural se conserva como antecedente científico. Su perfil se retiró del selector v2 y una solicitud explícita se rechaza. El default de LR es `lr_balanced` y el de MLP es `mlp_historical`. Ejemplo de contenido de un JSON para pasar a `--config`.

```json
{"schema_version": 1, "profile": "lr_balanced", "parameters": {"epochs": 10}}
```

Se admiten overrides de hiperparámetros presentes en el perfil. Ambos perfiles operativos usan el muestreo histórico **50/50 exacto en TRAIN**. El muestreador recorre cada clase y vuelve a tomar filas donde hace falta, con un donante de TRAIN para grupos sin una clase. La pérdida BCE no introduce pesos de clase ni `pos_weight`. No se estiman pesos ni prevalencias a partir de VALIDATION o TEST. La semilla de entrenamiento del perfil es independiente de la semilla del split. El preflight deriva datos, etiquetas, escalado y particiones del contrato en vez de aceptar reemplazos opacos. Las configuraciones describen los protocolos históricos y no constituyen configuraciones v2 ya ejecutadas.

## Adaptador de datos originales

[OriginalBatches y LegacyRowAdapter](../data_pipeline/nap_cnb_v2_batches.py) comparten una sola implementación para LR y MLP. La base conserva `base_id` y usa `label_original`; D1 usa el par exacto como identidad y `label_global`. El adaptador coteja las claves del índice de asignaciones con la primaria del inventario ProtT5. Retiene en memoria claves de 25 bytes, ordinales de 32 bits y códigos de split, con un lector por proceso. Proyecta un grupo de filas Parquet a la vez y solo resuelve vectores para las posiciones pedidas. Una columna ausente, clave ausente, etiqueta nula o no binaria, código de split inválido, offset incorrecto, archivo corrupto o vector no finito detiene la lectura.

Los lotes tienen `X` float32 de forma `(N, 1792)`, con las 1.024 columnas ProtT5 primero y las 768 SecondaryBERT después, y `y` float32 de forma `(N,)`. Se conservan identificadores, primarias, secundarias, split y orden de la solicitud. Los lotes de lectura secuencial retienen el último lote corto. El muestreador histórico balanceado aplica sus propias reglas de repetición y orden y usa los hooks de filas, sin entremezclar VALIDATION y TEST. El iterador independiente puede barajar los grupos y las filas de un split con una semilla explícita. Este barajado no se usa como sustituto del sampler histórico.

Los ordinales ProtT5 identifican shard y offset. El lector abre mmap de solo lectura, con caché predeterminada de dos shards. SecondaryBERT usa SQLite de solo lectura para resolver las claves. Comprueba el digest de los blobs nuevos. En las peticiones históricas agrupa por archivo, abre solo los bloques Zstd requeridos, coteja el recibo SHA-256 y valida el offset. El número de bloques en caché es configurable de uno a cuatro, con uno por defecto. Cada bloque tiene un límite de 320 MiB descomprimidos. El modo actual es de un solo lector y el motor histórico conserva su transferencia CPU/GPU. La caché es local y su tamaño no cambia los splits ni el contenido de los lotes.

### Scaler TRAIN

El fit reutiliza `_RunningMoments` y `ModalityStandardizer` históricos. Acumula por modalidad en float64, estima la varianza poblacional M2/N y guarda medias y escalas float32. Una escala menor de 1e-12 se sustituye por 1. El adaptador rechaza NaN/Inf antes del ajuste. El scaler aplica `(x - media) / escala`, incluidos VALIDATION y TEST con las estadísticas de TRAIN. Base y D1 tienen 39.228.827 y 12.083.630 filas TRAIN, respectivamente. La multiplicidad distinta impide presuponer un scaler común. El NPZ histórico aumentado permanece separado.

El ajuste completo queda pendiente de autorización. Después de medir el rendimiento y cuando se autorice la lectura, crear el directorio aislado `results/nap_cnb_v2_training/scalers/` y usar una ruta nueva para cada vista. La opción explícita confirma que se leerá todo TRAIN.

```bash
python -B -m data_pipeline.nap_cnb_v2_batches fit-scaler \
  --label original --batch-size 8192 --confirm-full-train \
  --output results/nap_cnb_v2_training/scalers/base.npz

python -B -m data_pipeline.nap_cnb_v2_batches fit-scaler \
  --label global --batch-size 8192 --confirm-full-train \
  --output results/nap_cnb_v2_training/scalers/d1.npz
```

El NPZ conserva los arrays del scaler histórico y añade `provenance.json` con versión, vista, etiqueta, split TRAIN, filas, dimensiones, método, precisiones, tamaño de lote, ruta de salida y firmas. Los SHA-256 de D1 y del informe de partición se calculan sobre JSON pequeños; las firmas de archivos grandes se registran como declaradas, sin rehashear payloads. El fit coteja los manifiestos al inicio y al final. La publicación es atómica y preserva cualquier NPZ existente. El preflight examina el contrato sin cargar estadísticas. Si la procedencia coincide muestra `METADATA_MATCH`. Antes de usarlo, el lector `load_train_scaler` comprueba además formas, float32, finitud y escalas positivas. En fixtures se comprobó reproducibilidad para el mismo orden y tamaño de lote, equivalencia tras guardar y reabrir, uso en VALIDATION y TEST, y rechazo de un NPZ de otra vista o de un intento de sobrescritura.

A 8.192 filas, el buffer de features ocupa 58,7 MB. El cálculo añade temporales float64 por modalidad. Los índices compactos ocupan unos 436 MB retenidos, con un pico superior al construir el orden y cotejar claves. Una descompresión histórica puede requerir el bloque en caché y copias temporales durante la carga. Mantener un solo lector mientras se mide RSS. El NPZ esperado ocupa decenas de kB. El volumen lógico recorrido en TRAIN es de unos 86,6 GB para D1 y 281,2 GB para la base. Las lecturas físicas dependen del patrón de caché y pueden ser mayores. El 4,73 s por bloque histórico de mediana del piloto implicaría unos 43 minutos si se leyera una vez cada uno de los 549 bloques referenciados. Es una referencia de coste, no una ETA. Con una caché pequeña, revisitar bloques puede dominar el tiempo y la carga de CPU de Zstd. Medir una muestra de orden y tasa de fallos de caché antes de autorizar el fit.

### Integración y política de evaluación

`BalancedTrainingSource` enlaza el lector por claves con el motor de [MLP y LR balanceada](../neural_network/MLP/mlp_layernorm_shuffled_ladder100_dualeval.py). Carga el scaler persistido mediante su contrato TRAIN y expone un grupo de filas por job. El único punto de entrada nuevo es el argumento programático `data_source` de `main()`. Los dos hooks de acceso se llaman a través de la fuente explícita, sin sustituir funciones del módulo. La rama v2 usa un lector sin prefetch en otro hilo porque SQLite es afín al hilo de apertura. La ruta predeterminada de los scripts históricos conserva el descubrimiento de chunks, los argumentos de CLI y la evaluación histórica.

El motor utiliza las mismas clases, BCE, AdamW, sampler TRAIN, scheduler y guardado de checkpoint. Bajo v2 evalúa **todas las filas de VALIDATION** al terminar cada época, con su prevalencia original, y elige el checkpoint de menor pérdida. Tras completar las épocas vuelve a cargar el mejor checkpoint y evalúa **TEST una vez**, conservando su prevalencia. Los perfiles balanceados conservan sus épocas fijas sin early stopping. Las métricas siguen siendo las del motor, incluida ROC-AUC cuando hay ambas clases. El campo `selection_metric` es `validation_loss` y el checkpoint añade `selection_split` y el contrato v2 con vista, etiqueta, perfil, balanceo, semilla y escalado. Se mantienen modelo, optimizador, scheduler y estado histórico de checkpoint. La recuperación final del modelo se probó. La reanudación e inicialización desde un checkpoint se rechazan por ahora en v2; las CLI históricas conservan su comportamiento.

El test de extremo a extremo usa dos épocas y ocho observaciones sintéticas, un único grupo de filas y un NPZ de TRAIN de fixture por vista. Los cuatro cruces balanceados pasan por `main(data_source=...)` sin monkey-patching. Cada época optimiza con 50/50 y valida sobre las tres observaciones reales de VALIDATION del fixture. Una traza en el lector prueba que las tres filas de TEST se recuperan solo al final. La prueba también comprueba la pérdida de selección, el estado del optimizador y el checkpoint guardado.

### Lanzamiento y resultados aislados

El preflight resuelve el perfil, hook, vista, embeddings, scaler esperado, política y salida. BASE y D1 siguen `INCOMPLETE` mientras falten sus scalers de producción. Incluso si el scaler coincide en procedencia, el preflight sigue siendo de solo lectura y la ejecución CLI se mantiene deshabilitada. Los resultados de fixtures se crean en directorios temporales. El almacenamiento real propuesto sigue bajo `results/nap_cnb_v2_training/`, con un directorio nuevo por experimento, separados scaler y métricas por split. Antes de habilitar un lanzamiento real quedan la medición de E/S por archivo, ambos ajustes completos, comprobación de estadísticas al cargar y autorización de ejecución. BLOSUM62/D2 siguen pendientes.

## Comprobación operativa de D1 del 22 de noviembre de 2026

En `nap_env`, `validate-datasets`, `validate-splits`, `validate-d1`,
`validate-prott5` y `validate-secondarybert` devolvieron PASS. El alcance
fue metadatos, footers, cabeceras y comprobaciones acotadas de catálogos según
el validador. La correspondencia por clave y la integridad numérica de todo
el corpus siguen cubiertas por la evidencia publicada y las pruebas acotadas,
sin una nueva pasada exhaustiva.

El preflight de LR original/global devolvió `INCOMPLETE`, código 1.
`results/nap_cnb_v2_training/scalers/d1.npz` sigue ausente y la salida
propuesta es `results/nap_cnb_v2_training/lr-original-global`. El planificador
mantiene la ejecución desactivada y el comando de lanzamiento vacío. El
perfil previsto conserva una capa lineal con un logit, AdamW, BCEWithLogitsLoss,
batch 8.192, tasa 0,001, weight decay 0,0001, semilla 42 y 10 épocas.

La suite CPU verificó el motor y el hook v2 sobre fixtures, incluyendo
escalado con TRAIN, actualizaciones del optimizador, selección por pérdida
en VALIDATION, lectura del checkpoint y una evaluación final en TEST. La
restauración de estado se comprobó en fixtures por separado. Queda por
verificar la reanudación de una corrida v2 interrumpida de extremo a extremo.
El motor registra los cuatro recuentos de confusión y ROC-AUC. PR-AUC no
figura en la salida actual y sigue pendiente para el informe del experimento.

En la comprobación de recursos, la MLP seguía activa y la LR histórica estaba
detenida. Había 171 GiB de RAM disponible, unos 20 TiB en el filesystem del
repositorio y aproximadamente 23–24 GiB de memoria libre por GPU en la
captura puntual. La E/S de lectura osciló aproximadamente entre 101 y
209 MiB/s en dos intervalos de un segundo. La captura no dimensiona el
entrenamiento ni establece una ETA. El fit de D1 y la corrida completa
quedaron pendientes.
