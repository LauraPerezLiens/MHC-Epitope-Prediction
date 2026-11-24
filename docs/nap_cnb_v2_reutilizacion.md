# NAP-CNB v2 con reutilización de datos existentes

Este documento conserva el estudio de reutilización previo a la certificación. Los contratos publicados de embeddings, vistas, splits y D1 están en la [organización del dataset original](nap_cnb_v2_dataset_organization.md).

## Inventario

Los tamaños indican ocupación en disco redondeada, salvo las cifras de los archivos individuales. El volumen `/data/nap` tenía 21.865.994.649.600 bytes libres, unos 19,89 TiB. Los recuentos proceden de footers Parquet, manifiestos y auditorías previas. No se extrajeron archivos ni se recorrieron corpus completos.

| Ruta | Tamaño y registros | Formato, contenido y claves | Conservación para v2 |
|---|---|---|---|
| `data/used_data/data_raw.tar.zst` | 106 MiB. La auditoría registra 1.985.260 registros en 22 exportaciones MHC y T-cell. | CSV en tar comprimido. Archivo y ordinal, IRIs del ensayo y la estructura, source y parent. | Imprescindible como fuente original, con su checksum. |
| `data/used_data/data_intermediate.tar.zst` | 4,8 GiB. Los 55.763.575 originales y 1.449.852.950 registros con BLOSUM62 se contabilizaron mediante índices derivados. | CSV archivados. Eventos históricos, FASTA, ventanas, variantes y datos estructurales. Familia, referencia, inicio y grupos locales. | Conservar el archivo verificado. Extraer en flujo solo los miembros requeridos si falta el equivalente ya accesible. |
| `data/used_data/contradiction_sources/` | 1,1 GiB, 11 CSV históricos de clasificación. | Ventanas originales. Familia, URL de proteína, inicio, secuencia y grupo local. | Fuente histórica. La lectura operativa puede partir del Parquet validado. |
| `data/global_epitope_labels/` | 1,1 GiB en total. `rows/` ocupa 475 MiB y contiene 55.763.575 filas. `sequences.parquet` contiene 15.135.904 secuencias exactas. | Parquet y SQLite. Familia, proteína, inicio, `25aa_seq`, `group_id`, posición en el CSV y etiquetas históricas. | Reutilizar para el cruce de posiciones y secuencias. Las etiquetas históricas quedan como referencia de comparación. |
| `results/epitope_counterfactual_20261118/`, `results/iedb_modified_audit_20261118/`, `results/iedb_download_audit_20261118/`, `results/iedb_pending_evidence_20261118/` | 138, 467, 280 y 63 MiB. | CSV, JSON, SQLite y cachés de referencias. El remapeo se vincula por familia, epítopo, ensayo, referencias, coordenadas y hash parent. | Conservar decisiones, evidencias y cachés necesarios para reproducir la clasificación. |
| `results/source_audits_inputs_20261118/data_intermediate/` | 21 MiB. | Subconjunto extraído de CSV, con FASTA parent usado por v2. | Reutilizar los FASTA y su procedencia. |
| `data/data_input_nn/{human,mouse}/` | 3,4 TiB. La auditoría de costes registra 14.503 bloques ProtT5 y 1.102 bloques SecondaryBERT, incluidas las salidas estructurales históricas inventariadas. | NPY comprimidos e índices CSV. ProtT5 float32 × 1024 por variante. SecondaryBERT pooled float32 × 768 por grupo, más índices estructurales con `clean_ss`. Direcciones por dataset, chunk y fila de origen. | Candidatos principales para extraer por lotes o conservar como referencias. Mantener mientras tengan consumidores o sean la copia de procedencia. |
| `data/data_input_nn_shuffled/mixed/` | 3,6 TiB. El índice maestro comprimido pesa 26,08 GB y registra 1.449.852.950 direcciones. | NPY y CSV comprimidos. El índice maestro enlaza dataset, chunk, fila y grupo de origen con chunk y fila mezclados. | El índice maestro y sus verificaciones tienen valor independiente. Evaluar las matrices redundantes por separado. |
| `data/data_input_nn_shuffled_concatenate/` | 9,5 TiB. 1.449.852.950 filas en 14.499 chunks. | NPY float32 × 1792, manifiesto de reordenación, etiquetas, grupos y splits por chunk. Acceso mmap por chunk y fila. | MLP y LR activos lo usan. El acceso directo puede servir de referencia si se conserva el mapa de procedencia y se confirma el rendimiento. |
| `model/unet_c_ensemble/` y `model/secondary_bert/` | 65 MiB y 327 MiB. | Pesos y configuración de predicción C/H/E, pesos y tokenizer de SecondaryBERT. | Conservar y fijar sus huellas. Para ProtT5 queda pendiente comprobar la revisión exacta de pesos y tokenizer de cada lote histórico. |
| `data/used_data/data_uniref50.tar.zst` y `results/group_split_check/` | 25 GiB y 781 MiB. | Fuente de preentrenamiento histórico y auditoría de grupos/splits de 1.449.852.950 filas. | Conservar como procedencia. La auditoría sirve para diseñar un split nuevo, ya que detectó 55.595.967 grupos en más de un split. |

## Qué reutilizar y qué calcular

- **Ventanas.** Hacer el cruce por familia, identidad de parent, hash de su secuencia, inicio y 25 aa exactos. El histórico aporta varias filas por posición cuando hay distintos epítopos. El índice nuevo conserva una posición y todos los vínculos de evidencia. Clasificar en conservada con igual etiqueta, conservada con etiqueta recalculada, excluida y nueva. Una corrección de coordenadas cambia los límites positivos dentro de un parent ya recorrido. Si habilita un parent antes omitido, genera posiciones nuevas. Un cambio en la secuencia de referencia requiere comprobar de nuevo la posición y la entrada estructural. La igualdad de secuencia se valida incluso para una posición aparentemente intacta.
- **ProtT5.** El código toma los 25 aa, aplica la limpieza histórica, tokeniza con espacios y promedia tokens de la ventana. La entrada carece de flancos proteicos. La reutilización exige 25 aa exactos, igual limpieza, pesos/tokenizer, pooling y política numérica. Registrar la revisión del modelo o marcar la compatibilidad sin verificar cuando falte evidencia. La muestra previa encontró igualdad exacta de ProtT5 en las 1.203 secuencias repetidas examinadas.
- **SecondaryBERT.** El código toma la cadena C/H/E de la ventana, obtenida de la predicción sobre la proteína completa. Para reutilizarla, comprobar parent completo y versión/hash, intervalo, 25 aa y recorte estructural. También se puede compartir un vector entre ventanas con la misma cadena C/H/E verificada y la misma huella de modelo, tokenizer y pooling, una vez comprobada cada correspondencia con su propia proteína. La auditoría detectó seis secuencias con dos entradas estructurales distintas y 41 observaciones barajadas coincidentes en ambos vectores con su origen. Esto confirma rutas de reutilización y excluye un join universal por 25 aa para SecondaryBERT.
- **Porcentajes.** Para cada modalidad informar, por ventana y por clave de entrada única, cuántas tienen una fuente compatible confirmada, cuántas requieren cálculo y cuántas tienen compatibilidad pendiente. Denominador: ventanas originales elegibles v2 o claves únicas v2, según la métrica. Incluir la intersección que permite reutilizar ambas modalidades. El porcentaje del corpus sigue indeterminado hasta cruzar todos los metadatos pertinentes. Las 11.030 observaciones de la auditoría eran una muestra dirigida. No hace falta una auditoría de igualdad de todos los vectores para contar coincidencias exactas de entradas y procedencia.
- **BLOSUM62.** Técnicamente se pueden recuperar los 26 registros de cada grupo histórico con `dataset + group_id`, comprobar el original en el primer registro y vincular las variantes por su secuencia y dirección explícita. `protein_group_id` identifica la proteína local y por sí solo no identifica un grupo de variantes. Excluir BLOSUM62 del dataset experimental principal. Si se aprueba una tarea de aumento posterior, registrar cada variante como sintética, restringirla a TRAIN y conservar por separado su progenitor y su estructura heredada. Los vectores secundarios heredados describen el progenitor. Revisar también variantes idénticas a secuencias de evaluación antes de reutilizarlas.
- **Splits y scaler.** Conservar los históricos como reproducibilidad. Para una nueva evaluación, dividir el índice definitivo por unidades que mantengan juntas las secuencias/representaciones idénticas y los grupos proteicos definidos por el protocolo, incluyendo futuros derivados sintéticos. Verificar el solapamiento y ajustar el scaler usando únicamente TRAIN v2. Los splits se pueden representar con un ID por ejemplo, sin copias de features.

## Revisión del constructor actual

Las 23 pruebas seleccionadas pasan. `verify_event` permite únicamente evidencia simple de ensayos elegibles y utiliza anotación explícita en versión exacta, remapeo previo vinculado a entidad/ensayo/hash o una proyección inequívoca con verificación de residuos. `build_family` exige al menos un evento verificado por familia–parent. La extensión positiva es el intervalo de inicios `max(1, epitope_end - 24)..min(epitope_start, protein_length - 24)`. El mismo intervalo se aplica a las ocurrencias ambiguas que se reservan. Un positivo simple en el mismo intervalo tiene precedencia. Otra proteína o familia aporta su propia evidencia. El OR de `global_counts` agrega una secuencia exacta entre las familias incluidas, que son once con `--full`. `reconcile_family` coteja etiquetas, residuos, intervalos y procedencia desde parquet.

La mejora necesaria se encuentra en la salida. Hoy se repiten secuencias y claves en familias, procedencia e índice global. El modo completo cuenta filas históricas sin reconciliar posiciones individuales. Separar verificación de evidencias y emisión de ventanas, conservar el recorrido en memoria por proteína y emitir un índice compacto tras el cruce exacto. Representar las evidencias por intervalos y almacenar asociaciones explícitas cuando aporten información, por ejemplo en exclusiones y remapeos. Si la estructura original del parent se reutiliza, fijar también la versión del predictor y el hash de la secuencia completa. Mantener el verificador como control de integridad de las salidas compactas.

## Estrategias y coste

Cifras en GB decimales salvo donde se indica GiB o TiB. Sean **N** las observaciones originales v2, **P** y **S** las entradas únicas de cada modalidad que todavía requieren cálculo y **K** las entradas reutilizadas que un benchmark aconseje materializar. Un par float32 ocupa 7.168 bytes. La representación de nuevas entradas cuesta **4.096 × P + 3.072 × S bytes**. Usar 55,76 M filas como escala de comparación, manteniendo pendiente el recuento v2.

| Estrategia | Lecturas, escrituras y tiempo | Espacio adicional | Reutilización, complejidad y riesgos |
|---|---|---|---|
| A. Reconstrucción tradicional | Verifica evidencias, vuelve a generar estructura y embeddings, escribe variantes si se incluyesen y concatena. Tiempo dependiente del rendimiento GPU por entrada única y del throughput local. Las escrituras con la huella del concatenado histórico son de 10,39 TB de payload por copia. | Para originales, 400 GB por copia de dos modalidades por fila a escala histórica, cerca de 800 GB si coexisten modalidades y concatenado. Con 26 filas por grupo, 10,39 TB solo el concatenado, más temporales. | 0% reutilización por diseño. Complejidad menor en joins y coste mayor. Regenerar BLOSUM62 solo reproduciría un artefacto ajeno al núcleo experimental. |
| B. Incremental materializada | Cruza metadatos, lee vectores candidatos agrupados por bloque y copia los aceptados a un almacén nuevo. Calcula los faltantes. Si la lectura toca todos los bloques originales comprimidos, la estimación previa es 3,72 TB comprimidos y 6,11 TB descomprimidos. A 50–200 MB/s efectivos sobre bytes descomprimidos son 8,5–34 h de lectura/decodificación, antes de cálculo y joins. | Como máximo de referencia, 400 GB de features si se vuelve a guardar un par por cada original histórico, o menos al compartir entradas. Añadir índices y búferes acotados. Una copia por secuencia exacta histórica daría 108,5 GB si hubiera un solo par por secuencia; SecondaryBERT puede tener más de una entrada. | P y S se miden con el cruce. Complejidad intermedia. Lectura de entrenamiento más localizada. Riesgo de asociar un vector a otra entrada o versión. |
| C. Índices, referencias y faltantes | Lee evidencias, footers e índices, genera las posiciones en memoria y persiste solo claves, etiquetas, direcciones y features faltantes. El Parquet histórico de ventanas ocupa 475 MiB. Si se requiere recorrer el maestro barajado completo, son otros 26,08 GB comprimidos; se puede evitar para resolver direcciones por bloques originales. El tiempo depende del cruce, verificación de referencias y ritmo de los joins, aún sin benchmark representativo. | Los registros de 24–48 bytes por observación serían 1,34–2,68 GB de payload a escala histórica. Presupuesto inicial de diseño de **5–10 GB permanentes** para índices y procedencia, **10–30 GB pico** con ordenaciones por particiones. A los dos se suma el almacén de faltantes y, si procede, la caché de K entradas frecuentes. Son presupuestos para dimensionar el piloto, no mediciones del pipeline final. | Misma oportunidad de reutilizar que B. Complejidad mayor en el cargador y dependencia de los archivos referenciados. Evitar acceso aleatorio a Zstd por fila. Puede combinarse con B por bloque si es más rápido al entrenar. |

La prueba ligera leyó un lote proyectado de 65.536 filas históricas en unos 0,28 s. Un mmap de un chunk concatenado leyó 1.024 filas contiguas y 1.024 dispersas ordenadas, 7,34 MB útiles por ensayo. Los tiempos fueron aproximadamente 0,21 y 0,01 s respectivamente, con orden fijo y caché no controlada. Esos tiempos solo verifican los dos modos de acceso. Medir lotes en varios bloques y repetir con datos fríos y calientes, contando bytes de disco, RSS, filas/s y tiempo hasta entregar el lote. Agrupar por archivo, reutilizar un número acotado de bloques descomprimidos y barajar bloques y minibatches con semilla fija. Medir también el throughput real de GPU en un piloto autorizado posterior para presupuestar P y S.

## Diseño recomendado

Empezar con **C para las ventanas originales**, con opción de materializar solo las representaciones consultadas repetidamente si el cargador por referencias resulta lento. Usar Parquet particionado para ventanas, evidencias, holdouts y cambios. Mantener un diccionario de secuencias exactas y referencias de proteína con checksums. Usar arrays compactos o tablas para `window_id → sequence_id, parent_id, start, etiquetas, split_id, primary_ref, secondary_ref`. Guardar rutas relativas a raíces declaradas en el manifiesto, tamaños, checksums y schema; una raíz movida se resuelve mediante configuración. Una referencia de embedding incluye el bloque y la fila, dimensión, dtype y la identidad de entrada/modelo. Un almacén binario aparte contiene solo vectores faltantes o materializados por rendimiento.

Salidas permanentes propuestas: manifiesto reproducible, diccionarios de secuencia y referencia, evidencias y decisiones, índice de ventanas y etiquetas, holdouts, direcciones por modalidad, splits como IDs y resumen de validación. Los temporales serían particiones de cruce, índices de trabajo y bloques de descompresión acotados. Confirmar recuentos, claves, etiquetas, direcciones y checksums, publicar la partición de forma atómica y retirar únicamente sus temporales registrados. Un fallo conserva los checkpoints y las particiones necesarias para reanudar.

### Archivos cuya retirada podría evaluarse después

- **9,5 TiB del concatenado histórico.** Es la principal oportunidad de espacio. Es dependencia activa de MLP/LR y posible origen mmap para C. Solo evaluar la retirada tras migrar consumidores, resultados reproducibles y referencias v2.
- **Hasta 3,6 TiB del árbol barajado comprimido.** Revisar la redundancia de matrices por chunk tras garantizar la reconstrucción desde los originales. Separar y conservar el máster de direcciones, los manifiestos y checksums. El total del árbol incluye estos metadatos.
- **Hasta 1,1 GiB de CSV de clasificación extraídos.** Evaluar cuando se haya comprobado recuperación desde el tar verificado y los consumidores usen el Parquet o puedan extraer miembros en flujo.
- **Dos cachés de evaluación de unos 799 MiB cada una** en los resultados históricos MLP/LR. Validar claves, contenido y regenerabilidad antes de evaluar su retirada. Conservar las métricas, los checkpoints y sus configuraciones.

## Orden de ejecución

Comprobaciones ya ejecutadas o de lectura local, desde la raíz:

```bash
df -B1 .
du -h --max-depth=2 data results
conda activate nap_env
python -m unittest tests.test_rebuild_iedb tests.test_iedb_modified_audit \
  tests.test_iedb_download_audit tests.test_source_audits
```

Cuando se autorice un piloto del constructor actual, este comando materializa únicamente su selección acotada. Usar una salida nueva.

```bash
python -m data_pipeline.scripts.rebuild_iedb.rebuild \
  --pilot data_pipeline/scripts/rebuild_iedb/pilot_selection.json \
  --output results/iedb_rebuild_v2_reuse_reference_pilot
```

Para C, el orden es implementar la salida compacta, contrastarla con el piloto de referencia, medir cobertura y lectura por bloques, decidir la caché de entrenamiento y ejecutar el cruce de las once familias tras autorización. Después se calculan únicamente faltantes aprobados y se generan splits y scaler cuando proceda. La CLI compacta aún no existe. El `--full` existente materializa las tablas actuales y queda fuera de la ruta recomendada.

## Fuentes locales

- [Proveniencia, formatos y manifiestos](../data_pipeline/docs/data_and_models.md)
- [Resumen histórico de ventanas](../data/global_epitope_labels/report.md)
- [Auditoría de redundancia y muestra barajada](../reports/audits/exact_embeddings_sample.md)
- [Los seis casos de contexto estructural distinto](../reports/audits/embedding_representation_cases.md)
- [Presupuesto previo de lecturas de embeddings](../reports/audits/exact_embeddings_cost.md)
- [Constructor v2](../data_pipeline/scripts/rebuild_iedb/rebuild.py)
