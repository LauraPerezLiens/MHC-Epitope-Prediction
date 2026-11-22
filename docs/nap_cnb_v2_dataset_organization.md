# NAP-CNB v2 · Organización del dataset original

## Fuente de verdad y dependencias

El dataset maestro propuesto es una vista de solo lectura de la [selección definitiva](../results/nap_cnb_v2_final_selection/final_selection_report.md). A partir de `selection.json`, la vista lee los once Parquet familiares de fase 1, incorpora el suplemento estructural por `window_id` y excluye las claves de `pending_windows.parquet`. El manifiesto y los suplementos fijan la versión que debe consumir cada experimento. Se cotejaron las 61 firmas de tamaño y mtime y los dos SHA-256 de suplementos del manifiesto. Todas coincidieron. El resultado certificado contiene 49.123.503 ventanas, con 5.587.074 positivas y 43.536.429 negativas operacionales.

| Componente | Dependencia |
|---|---|
| Ventanas, etiquetas y coordenadas | `nap_cnb_v2_phase1/families/*.parquet` y reglas de la selección definitiva |
| Proteínas y trazabilidad | `proteins/`, `references/`, `provenance/` y `evidence_verified/` de fase 1 |
| ProtT5 original | Inventario de primarias exactas, manifiesto, `progress.sqlite` y 146 shards NPY del almacén final |
| SecondaryBERT original | `nap_cnb_v2_secondarybert/index.sqlite` y archivos NPY/Zstd canónicos apuntados por el índice |
| Etiqueta agregada por secuencia | `nap_cnb_v2_phase1/global_index.parquet`, que pertenece al conjunto binario anterior al filtro estructural |

[Manifiesto de selección](../results/nap_cnb_v2_final_selection/selection.json) · [ProtT5](nap_cnb_v2_prott5.md) · [SecondaryBERT](nap_cnb_v2_secondarybert.md)

## Contrato de la vista maestra

| Campo lógico | Fuente |
|---|---|
| `window_id` | Identificador existente, compuesto por familia, URL de origen e inicio. Coordenadas de proteína con base 1 y extremos inclusivos, 25 posiciones por ventana |
| `protein_id` | Referencia a la identidad de origen con URL, accesión y versión. Conservar también `parent_sha256` para identidad de secuencia completa |
| `protein_group_id`, `group_id` históricos | Disponibles en tablas antiguas con alcance local de archivo. En la vista v2 quedan ausentes salvo correspondencia demostrada. El futuro grupo de partición tendrá un campo propio |
| Familia, clase y especie | `family`, `mhc_class`, `organism`. La especie de la clasificación y la proteína de origen conservan campos separados |
| Primaria y Secundaria | `sequence` exacta de fase 1 y C/H/E exacta de la vista. `structure_prediction_id` y `structure_source` documentan procedencia |
| Referencias de embeddings | Primaria exacta para ProtT5 y C/H/E exacta para SecondaryBERT. Los ordinales y offsets son direcciones físicas ligadas al manifiesto |
| Etiqueta | `contains_epitope` de la familia, con `pending_candidate` como dato de procedencia |
| Evidencia y posición | Relación por `window_id` con todos los `verified_event_ids` y sus coordenadas. Los campos históricos `selected_epitope` y `epitope_pos_score` carecen de equivalente escalar en v2 |
| Procedencia y tipo | Versión de selección y archivo familiar. Tipo `original`. La vista original carece de padre o ID de variante |

La primaria puede repetirse en varias filas. El identificador de ventana mantiene las observaciones separadas y el catálogo de embeddings permite compartir su vector. Mantener toda la evidencia como relación aparte evita multiplicar filas cuando una ventana tenga varios eventos. La vista de DuckDB en el informe de selección es el punto de partida. Parquet permite proyectar columnas y filtrar por familia. Reservar SQLite para catálogos y manifiestos pequeños respecto al conjunto de ventanas. Materializar únicamente índices de acceso o listas de IDs cuando un patrón de lectura lo justifique.

## Etiquetas y relaciones entre proteínas

Fase 1 etiqueta positivamente una ventana cuando contiene al menos un intervalo completo con evidencia verificada en su contexto familiar. Un candidato pendiente queda señalado y no aporta positividad. Las ventanas sin evidencia verificada pueden ser negativas operacionales. Los casos retenidos quedan fuera del conjunto binario. El filtro estructural conserva las etiquetas de fase 1 y deja fuera 81.601 ventanas, incluidas 7.455 positivas. La agregación global aplica positividad si alguna observación de la secuencia es positiva. Hay 3.364.405 secuencias con observaciones positivas y negativas operacionales en ese índice anterior al filtro. Para experimentos por ventana se usa la etiqueta familiar y se mantienen las coordenadas y el contexto de origen.

El código histórico asigna `protein_group_id` por URL dentro de cada archivo de clasificación y `group_id` por fila original. Los metadatos de proteínas de fase 1 contienen 32.131 SHA-256 distintos. 22.026 aparecen en más de una familia y 256 aparecen bajo más de una URL. Son recuentos de los catálogos de fase 1, previos al filtro de ventanas. Una misma proteína aporta ventanas solapadas y un identificador histórico local no garantiza independencia. El [chequeo histórico](../results/group_split_check/summary.json) encontró 55.595.967 de 55.763.575 grupos locales repartidos entre varios splits. Sus asignaciones son evidencia histórica y quedan fuera de las futuras particiones v2.

[Informe de fase 1](../results/nap_cnb_v2_phase1/phase1_report.md) · [Construcción de etiquetas](../data_pipeline/scripts/rebuild_iedb/rebuild.py) · [Identificadores históricos](../data_pipeline/scripts/data_classification/epitope_classification.py)

## Estructura secundaria original

El nombre local es **UNet-C Ensemble**, según la documentación y el directorio `model/unet_c_ensemble`. El predictor carga un TensorFlow/Keras SavedModel. El SHA-256 local de `saved_model.pb` es `d3eb4dc8a79f6306841e3d16b078fd172c9e3b7eda1a03ef0da6ed7892fa2b36`. Las variables forman parte del checkpoint. Este hash identifica el archivo disponible, sin acreditar por sí solo el checkpoint de cada predicción archivada.

El predictor usa la secuencia de la proteína codificada one-hot, rellena a 1.024 posiciones y devuelve tres probabilidades por residuo en orden C/H/E. En proteínas largas usa segmentos de 1.024 con solapamiento de 200, recorta márgenes internos y promedia las contribuciones conservadas. Si quedan posiciones descubiertas, recurre a los segmentos completos. La asignación final usa argmax. La estructura de 25 estados se extrae tras verificar coordenadas y coincidencia exacta con la ventana primaria de referencia. Las recuperaciones archivadas se identifican en el suplemento. Si un registro derivado solo reutiliza una anotación del padre, `secondary_structure_origin = inherited_from_parent` debe describir esa procedencia y la estructura debe seguir vinculada a la observación original.

[Predictor y mapeo](../data_pipeline/scripts/secondary_structure_prediction/README.md)

## Lectura, particiones y experimentos

1. Proponer grupos globales como componentes conectados por identidad de proteína de origen y por hash de secuencia proteica completa. Resolver versiones y alias con las referencias verificadas. Medir adicionalmente cuántas claves de primaria exacta aparecen en varios componentes, y evaluar aristas de identidad de ventana y agrupamiento de homólogos antes de fijar el criterio. Inspeccionar el tamaño del mayor componente antes de decidir cómo equilibrar los conjuntos.
2. Asignar componentes enteros, con objetivo 80/10/10, semilla, algoritmo versionado y balance aproximado por filas, familia y clase. Mantener juntas las ventanas solapadas. Todo registro derivado deberá heredar la asignación de su padre. Reservar el test principal a originales y usar las mismas observaciones para todas las comparaciones. Verificar disjunción de grupos, proteínas y claves conforme al criterio elegido. Ningún split quedó construido en esta fase.
3. Filtrar lógicamente por especie, MHC, proteína, grupo o etiqueta antes de muestrear. Barajar IDs de filas mediante permutación reproducible de bloques y de los IDs dentro de cada bloque con semilla y época. Guardar versión, semilla, bloque y cursor para reanudar. Resolver referencias por lotes, agrupar internamente las lecturas por shard o archivo y restaurar el orden del lote con la posición de cada solicitud. Leer ProtT5 por mmap y evaluar agrupación, lectura por lotes y caché de SecondaryBERT durante la preparación del consumo. El piloto midió 4,73 s por bloque comprimido de SecondaryBERT de mediana. La representación conjunta de 1.792 dimensiones se puede formar en memoria al cargar el lote.
4. D1 selecciona todos los originales y D3 aplica un manifiesto versionado de proteínas a los mismos originales. D2/D4 quedan registrados como configuraciones propuestas. Si se evaluaran conjuntos derivados admisibles, sus filas vivirían en una tabla independiente, vinculadas a la observación original y con procedencia, versión y partición heredada. Una identidad lógica de registro puede derivarse del ID del padre, la versión y una clave de contenido, independientemente del orden físico.
5. Para comparar LR, MLP u otros modelos, fijar versión de selección, inventarios de embeddings, manifiesto de particiones y filtros de proteína. Registrar semilla y estrategia de balanceo. Aplicar el balanceo al entrenamiento y reportar ROC-AUC, PR-AUC, precisión, recall, F1 y matriz de confusión sobre un test común, con resultados por familia y especie.

## Artefactos históricos y capacidad

Conservar `scripts/data_augmentation/generate_blosum62_variants.py` y los índices y volúmenes históricos `*_blosum_ProtT5_chunks` como artefactos de procedencia. La auditoría anterior identifica su checkpoint sin vincular una revisión exacta a los lotes. Los datasets `data_input_nn_shuffled` y `data_input_nn_shuffled_concatenate`, sus scripts de reordenamiento y los resultados LR/MLP describen experimentos anteriores. Las copias derivadas y las salidas legacy `chunks_pooled/` son candidatas a revisión de redundancia cuando se conozcan sus consumidores.

El techo solicitado de 1.228.087.575 registros adicionales representa capacidad teórica. Si cada registro tuviera un vector distinto de 1.024 valores float32, el payload llegaría a **5.030.246.707.200 bytes** o 5,03 TB decimales, más metadatos. Esta cifra es un límite aritmético. El tamaño real depende de la cardinalidad y compresión. Para medir costes de cualquier ampliación admisible, separar conteo de registros, cardinalidad de claves, coincidencias con el catálogo certificado, bytes por fila medida y ritmo de inferencia y escritura medido. Las fases originales ya ofrecen almacenes certificados independientes y no requieren nuevas inferencias para D1/D3.

Quedan por cerrar el criterio global de grupos, el tratamiento de secuencias compartidas entre contextos, la tolerancia del reparto por familia y la política de manifiestos de subconjuntos. El alcance documentado de esta entrega es la vista original, su procedencia y el diseño de evaluación reproducible.

[Inventario de scripts](nap_cnb_v2_organizacion.md) · [Auditoría de fuentes de embeddings](../results/nap_cnb_v2_embedding_audit/embedding_audit_report.md)

## Fase 4B · Base deduplicada e índice global

El módulo [dataset_views.py](../data_pipeline/scripts/rebuild_iedb/dataset_views.py) aplica el manifiesto de selección definitiva y genera catálogos de metadatos Parquet con PyArrow. Se eligió PyArrow porque ya está instalado en Pascal. Los catálogos pueden consultarse también con DuckDB. El comando reproducible, desde la raíz y con el entorno `nap_env`, es `python -m data_pipeline.scripts.rebuild_iedb.dataset_views`. La publicación se hace al terminar las validaciones. En caso de interrupción antes de publicar se ejecuta de nuevo el mismo comando. Para una reconstrucción posterior se puede indicar otro destino con `--output`.

La clave de la base es `(parent_url, parent_accession, parent_version, parent_sha256, family, sequence, secondary_structure, label_original)`. Conserva URLs distintas incluso si coinciden sus hashes, y conserva referencias con versiones o hashes distintos. Esta política evita fusionar identidades ambiguas. Una coincidencia del hash de la proteína completa se puede estudiar como relación, independientemente de la identidad conservadora que se usa en la base. Como ProtT5 y SecondaryBERT están certificados por clave exacta, las dos secuencias fijan los vectores sin leer sus valores. El representante `base_id` es el menor `window_id` lexicográfico. La relación de procedencia incluye a todos los miembros, incluido el representante.

| Catálogo | Clave y contenido |
|---|---|
| `base_dataset.parquet` | `base_id`, clave de la base, especie, clase MHC y número de observaciones. Las vistas específicas filtran esta tabla y consumen `label_original` |
| `window_provenance.parquet` | Una fila por `window_id`, con su `base_id`. Las coordenadas, la fuente familiar y los IDs de evidencia se recuperan desde la selección y la procedencia de fase 1 |
| `legacy_group_links.parquet` | Enlaces por `window_id` a archivo, fila, `group_id` y etiqueta histórica. Varios candidatos para una ventana pueden coexistir |
| `global_labels.parquet` | Una fila por primaria exacta, con `MAX(label_original)` y recuentos de procedencia |
| `global_dataset.parquet` | Una fila por primaria y secundaria exactas, con etiqueta global por primaria. Las filas de la base se recuperan por ese par exacto |
| `metrics.json` | Firma de la selección, métricas por familia y globales, tamaños y tiempo de ejecución |

La etiqueta global es una agregación de evidencia. Una primaria positiva en el índice global puede seguir siendo negativa operacional en una observación familiar. Se conservan las distintas estructuras secundarias asociadas a una misma primaria. Para evaluar en el futuro una vista de una sola fila por primaria, se puede definir y versionar por adelantado un criterio de procedencia estructural, seguido por número de proteínas distintas que aportan la estructura y desempate lexicográfico. La elección, si se realiza, se valida contra la vista que conserva todas las estructuras. Las proteínas y familias de cada representación se consultan en el catálogo base.

### Grupos históricos y futuras particiones

`group_id` se asignaba por fila de ventana original dentro de cada archivo de clasificación, y las filas derivadas conservaban ese valor. La clave histórica que evita colisiones es `(legacy_source_file, group_id)`. La reconstrucción enlaza por familia, URL normalizada con la misma semántica de fase 1, coordenada y secuencia exacta. Las coincidencias múltiples quedan registradas como candidatas. La etiqueta histórica es un dato de trazabilidad y la etiqueta canónica se toma siempre de la selección. Una ventana sin enlace histórico conserva su `window_id` como clave v2. Así se preserva la correspondencia cuando una base deduplicada reúne varios grupos.

Para esta fase, el criterio de partición solicitado sustituye el criterio por proteínas propuesto en 4A. Las asignaciones futuras partirán de `group_id` con ámbito de archivo y de la clave v2 para ventanas sin correspondencia única. Conectar grupos que aporten al mismo registro deduplicado o a la misma representación global. Para comparar de forma estricta con la etiqueta global que se agrega por primaria, conectar también representaciones de la misma primaria aunque tengan secundarias distintas. Los enlaces actuales exigen identidad de primaria y los grupos históricos se asignan a una ventana original, de modo que los componentes bajo ese criterio se pueden identificar por primaria exacta en estos catálogos. Las particiones se asignarán una sola vez a esos componentes y se heredarán en la base, las vistas globales y los filtros familiares. El solapamiento de proteína completa se medirá como diagnóstico. El test común se restringirá a originales. El reparto 80/10/10 sigue pendiente.

### Consulta de procedencia

Desde la raíz, estas vistas de DuckDB vinculan las representaciones con la base y las observaciones. La selección y los Parquet de fase 1 siguen siendo necesarios para recuperar coordenadas y evidencias por `window_id`.

```sql
CREATE VIEW base_v2 AS
SELECT * FROM read_parquet('results/nap_cnb_v2_dataset_views/base_dataset.parquet');

CREATE VIEW global_v2 AS
SELECT * FROM read_parquet('results/nap_cnb_v2_dataset_views/global_dataset.parquet');

CREATE VIEW window_links_v2 AS
SELECT * FROM read_parquet('results/nap_cnb_v2_dataset_views/window_provenance.parquet');

CREATE VIEW legacy_groups_v2 AS
SELECT * FROM read_parquet('results/nap_cnb_v2_dataset_views/legacy_group_links.parquet');

-- Filas y etiquetas familiares originales de una representación global.
SELECT g.label_global, b.label_original, b.family, b.parent_url, w.window_id,
       l.legacy_source_file, l.group_id
FROM global_v2 g
JOIN base_v2 b USING (sequence, secondary_structure)
JOIN window_links_v2 w USING (base_id)
LEFT JOIN legacy_groups_v2 l USING (window_id)
WHERE g.sequence = $primary AND g.secondary_structure = $secondary;
```

La consulta devuelve un registro por candidato histórico cuando hay varios. Para contar observaciones originales, usar `window_links_v2` directamente o contar `DISTINCT window_id` después de incorporar candidatos.

### Resultados de la fase 4B

| Familia | Originales | Base | Duplicados consolidados | Positivas en base | Negativas operacionales en base |
|---|---:|---:|---:|---:|---:|
| HLA-A | 9.485.082 | 9.464.157 | 20.925 | 1.519.552 | 7.944.605 |
| HLA-B | 9.515.496 | 9.499.649 | 15.847 | 1.998.856 | 7.500.793 |
| HLA-C | 7.507.884 | 7.491.944 | 15.940 | 781.222 | 6.710.722 |
| HLA-DP | 4.288.102 | 4.274.625 | 13.477 | 238.245 | 4.036.380 |
| HLA-DQ | 2.112.668 | 2.103.834 | 8.834 | 108.664 | 1.995.170 |
| HLA-DR | 5.884.747 | 5.870.191 | 14.556 | 419.921 | 5.450.270 |
| H2-D | 3.058.819 | 3.056.053 | 2.766 | 126.192 | 2.929.861 |
| H2-K | 5.485.543 | 5.480.480 | 5.063 | 345.337 | 5.135.143 |
| H2-L | 4.421 | 4.421 | 0 | 99 | 4.322 |
| H2-IA | 1.709.929 | 1.706.236 | 3.693 | 47.400 | 1.658.836 |
| H2-IE | 70.812 | 70.770 | 42 | 1.585 | 69.185 |
| **Total** | **49.123.503** | **49.022.360** | **101.143** | **5.587.073** | **43.435.287** |

La base reduce el número de registros un **0,21 %**. Se consolidaron 1 observación positiva y 101.142 negativas operacionales. En total, 150.878 ventanas pertenecen a claves base con más de una observación. Las 49.123.503 ventanas siguen recuperables mediante la relación de procedencia. Los 3.378.126 pares primaria/secundaria con etiquetas originales distintas se conservan como observaciones separadas en la base.

Para una misma combinación de primaria, secundaria y etiqueta original, 1.832.713 claves aparecen en varias identidades de proteína (9.743.564 ventanas), y 12.461.779 en varias familias (43.077.182 ventanas). Las categorías pueden solaparse. En los catálogos de proteína de fase 1 no se observó una URL con varios hashes conocidos. Los 256 hashes con varias URLs documentados en 4A se mantienen separados por URL en la base.

| Catálogo | Filas | Positivas | Negativas operacionales |
|---|---:|---:|---:|
| Índice por primaria | 14.530.324 | 3.577.364 | 10.952.960 |
| Vista de representaciones | 15.100.592 | 3.844.628 | 11.255.964 |

Hay 3.360.793 primarias con ambos valores de etiqueta original y 3.354.655 con máximos distintos entre las familias observadas. La etiqueta global es positiva para 11.856.457 observaciones de la base cuya etiqueta original es negativa operacional. Hay 547.627 primarias con varias secundarias. La vista global reduce el número de registros un **69,20 %** respecto a la base.

### Recuentos de grupos y validación

| Medida | Resultado |
|---|---:|
| Grupos en el catálogo histórico, con ámbito de archivo | 55.763.575 |
| Grupos históricos enlazados a la selección v2 | 51.593.373 |
| Valores numéricos de `group_id` reutilizados entre archivos | 10.214.658 |
| Ventanas con al menos un candidato histórico | 47.560.441 |
| Ventanas con varios candidatos históricos | 1.675.495 |
| Ventanas sin candidato histórico | 1.563.062 |
| Grupos históricos enlazados por una clave base con duplicados | 145.606 |
| Grupos históricos enlazados a un par primaria/secundaria compartido | 48.462.521 |
| Grupos históricos enlazados a una primaria compartida | 48.732.432 |
| Ventanas canónicas que comparten el par exacto | 45.736.290 |
| Ventanas que comparten el par exacto entre familias | 45.698.401 |
| Mayor componente por primaria exacta, en ventanas originales | 351 |

Cada ID histórico con ámbito de archivo pertenece a una sola familia. El número bruto se reutiliza ampliamente y no identifica relaciones biológicas. El catálogo original tiene una fila y una etiqueta por grupo con ese ámbito. De los enlaces recuperados, 319.672 tienen una etiqueta histórica diferente de la corregida. La discrepancia se conserva en el enlace y la base usa siempre la corregida. La comprobación se hizo sobre las ventanas originales históricas. El código conserva el identificador del padre en filas derivadas.

Los cinco Parquet ocupan **861.738.282 bytes**. La construcción y sus comprobaciones internas duraron **931,59 s**. La reapertura y el recuento adicional de grupos duraron **129,68 s**. Se verificaron los totales de etiquetas por familia contra el manifiesto, una relación por ventana original, la cobertura de procedencia en la vista global, la regla MAX mediante una agregación independiente por familia y la coincidencia de claves con los dos catálogos certificados de embeddings. La primera comprobación del enlace histórico detectó coincidencias múltiples. Se resolvió con una relación separada que conserva todos los candidatos. Los Parquet se reabrieron y se comprobaron sus referencias y recuentos.

[Catálogo base](../results/nap_cnb_v2_dataset_views/base_dataset.parquet) · [Índice de etiquetas](../results/nap_cnb_v2_dataset_views/global_labels.parquet) · [Vista global](../results/nap_cnb_v2_dataset_views/global_dataset.parquet) · [Métricas y tamaños](../results/nap_cnb_v2_dataset_views/metrics.json)

## Fase 4C · Manifiesto común de particiones

La unidad indivisible es la primaria exacta de 25 residuos. Su valor sirve directamente como `effective_group_id`. Las ventanas sin enlace histórico mantienen este criterio. Para una ventana con varios candidatos a `group_id` se conservan los enlaces como candidatos y se comprueba el ámbito de archivo y la cardinalidad de cada grupo. El código se detiene si un grupo histórico con ámbito de archivo enlaza a más de una ventana o si un archivo histórico aparece en más de una familia. Esto permite revisar cualquier futuro enlace que pueda conectar primarias distintas antes de publicar un nuevo manifiesto.

El algoritmo `primary-blake2b-mod10-v1` usa BLAKE2b con digest de 8 bytes y semilla codificada como entero sin signo de 64 bits little-endian. Interpreta el digest como entero little-endian y usa el residuo módulo 10. Los valores 0 a 7 son train, 8 es validation y 9 es test. El manifiesto se guarda ordenado por clave exacta. Cada grupo recibe una sola asignación y aporta todas sus observaciones al cómputo del reparto. Este esquema da un 80/10/10 esperado por observaciones y por cualquier subconjunto fijado de antemano. El reparto medido y la prevalencia por familia se verifican tras asignar. El algoritmo carece de cuotas de estratificación duras y de restricciones por proteína completa.

Para reproducir la construcción desde la raíz con `nap_env`, ejecutar `python -m data_pipeline.scripts.data_splitting.split_nap_cnb_v2 --seed 42`. El código lee un Parquet familiar de metadatos cada vez además de los catálogos globales compactos. Usa el manifiesto de selección ya validado, comprueba firmas del contenido Parquet antes y después del procesamiento y verifica la asignación al reabrir el resultado. El destino predeterminado es `results/nap_cnb_v2_dataset_views/splits/`. Para reconstruir con los mismos parámetros se puede indicar un destino nuevo con `--output`.

La base y la vista global se unen con el manifiesto mediante `sequence = effective_group_id`. La base conserva `label_original` y la vista global conserva `label_global`. Las vistas por familia, especie o subconjunto de proteínas filtran después de recuperar la asignación. Para cualquier registro derivado, recuperar `parent_window_id` en `window_provenance.parquet`, seguir `base_id` a la base y usar la primaria de esa ventana. Este recorrido conserva la asignación aunque la deduplicación haya reunido varios padres canónicos en una fila base. Los conjuntos se representan mediante el catálogo y el filtro de `split_id`, sin duplicar metadatos ni embeddings.

El diagnóstico de solapamiento agrupa por SHA-256 de la secuencia proteica completa, incluyendo alias de la misma proteína. Para ventanas originales de 25 residuos de ese mismo grupo, compara intervalos de coordenadas con extremos inclusivos. El recuento de ventanas afectadas cuenta cada ventana una vez por split. Los pares se cuentan una vez por combinación de splits. La identidad de primaria garantiza disjunción exacta. Los grupos históricos enlazan ventanas originales individuales y por sí solos no garantizan separación por homología. Las ventanas solapadas de secuencias distintas y las proteínas compartidas entre splits pueden hacer que la evaluación sobreestime la generalización a proteínas no vistas. Una evaluación posterior específicamente por proteína u homología requeriría definir el criterio y medir los componentes y el coste antes de crear una partición adicional.

### Resultados y validación de la fase 4C

| Medida | Train | Validation | Test |
|---|---:|---:|---:|
| Grupos efectivos / primarias | 11.627.152 | 1.450.379 | 1.452.793 |
| Ventanas originales | 39.311.036 | 4.900.434 | 4.912.033 |
| Base, filas | 39.228.827 | 4.891.517 | 4.902.016 |
| Base, porcentaje de filas | 80,022 % | 9,978 % | 10,000 % |
| Base, positivas | 4.470.747 | 557.339 | 558.987 |
| Base, negativas operacionales | 34.758.080 | 4.334.178 | 4.343.029 |
| Base, prevalencia positiva | 11,397 % | 11,394 % | 11,403 % |
| Global, filas | 12.083.630 | 1.507.558 | 1.509.404 |
| Global, porcentaje de filas | 80,021 % | 9,983 % | 9,996 % |
| Global, positivas | 3.076.633 | 383.839 | 384.156 |
| Global, negativas operacionales | 9.006.997 | 1.123.719 | 1.125.248 |
| Global, prevalencia positiva | 25,461 % | 25,461 % | 25,451 % |

El siguiente desglose usa la etiqueta original de la base. Cada celda indica filas, positivas, negativas operacionales y porcentaje de filas de su grupo.

| Familia, clase o especie | Train | Validation | Test |
|---|---|---|---|
| HLA-A | 7.573.165 · 1.215.405 · 6.357.760 · 80,019 % | 943.953 · 151.741 · 792.212 · 9,974 % | 947.039 · 152.406 · 794.633 · 10,007 % |
| HLA-B | 7.601.802 · 1.599.322 · 6.002.480 · 80,022 % | 947.973 · 199.603 · 748.370 · 9,979 % | 949.874 · 199.931 · 749.943 · 9,999 % |
| HLA-C | 5.995.631 · 625.431 · 5.370.200 · 80,028 % | 747.190 · 77.641 · 669.549 · 9,973 % | 749.123 · 78.150 · 670.973 · 9,999 % |
| HLA-DP | 3.421.195 · 190.494 · 3.230.701 · 80,035 % | 425.713 · 23.804 · 401.909 · 9,959 % | 427.717 · 23.947 · 403.770 · 10,006 % |
| HLA-DQ | 1.683.064 · 86.841 · 1.596.223 · 80,000 % | 210.202 · 10.975 · 199.227 · 9,991 % | 210.568 · 10.848 · 199.720 · 10,009 % |
| HLA-DR | 4.697.788 · 336.518 · 4.361.270 · 80,028 % | 585.194 · 41.839 · 543.355 · 9,969 % | 587.209 · 41.564 · 545.645 · 10,003 % |
| H2-D | 2.444.988 · 101.024 · 2.343.964 · 80,005 % | 305.525 · 12.516 · 293.009 · 9,997 % | 305.540 · 12.652 · 292.888 · 9,998 % |
| H2-K | 4.385.488 · 276.447 · 4.109.041 · 80,020 % | 547.645 · 34.356 · 513.289 · 9,993 % | 547.347 · 34.534 · 512.813 · 9,987 % |
| H2-L | 3.569 · 87 · 3.482 · 80,728 % | 451 · 4 · 447 · 10,201 % | 401 · 8 · 393 · 9,070 % |
| H2-IA | 1.365.443 · 37.910 · 1.327.533 · 80,027 % | 170.596 · 4.688 · 165.908 · 9,998 % | 170.197 · 4.802 · 165.395 · 9,975 % |
| H2-IE | 56.694 · 1.268 · 55.426 · 80,110 % | 7.075 · 172 · 6.903 · 9,997 % | 7.001 · 145 · 6.856 · 9,893 % |
| mhc-I | 28.004.643 · 3.817.716 · 24.186.927 · 80,021 % | 3.492.737 · 475.861 · 3.016.876 · 9,980 % | 3.499.324 · 477.681 · 3.021.643 · 9,999 % |
| mhc-II | 11.224.184 · 653.031 · 10.571.153 · 80,026 % | 1.398.780 · 81.478 · 1.317.302 · 9,973 % | 1.402.692 · 81.306 · 1.321.386 · 10,001 % |
| human | 30.972.645 · 4.054.011 · 26.918.634 · 80,024 % | 3.860.225 · 505.603 · 3.354.622 · 9,974 % | 3.871.530 · 506.846 · 3.364.684 · 10,003 % |
| mouse | 8.256.182 · 416.736 · 7.839.446 · 80,018 % | 1.031.292 · 51.736 · 979.556 · 9,995 % | 1.030.486 · 52.141 · 978.345 · 9,987 % |

Se verificaron **14.530.324 componentes**, uno por primaria exacta. Los tamaños máximos por componente son 351 ventanas originales, 139 filas base y 10 representaciones globales. Se comprobaron **51.593.373** IDs históricos con ámbito de archivo. Cada uno apunta a una sola ventana de la selección y ningún enlace histórico conecta primarias distintas. Hay **1.675.495** ventanas ambiguas con **5.708.427** enlaces candidatos y **1.563.062** ventanas sin enlace. Como cada candidato con ámbito de archivo apunta únicamente a una ventana, conservar los candidatos ambiguos no induce conexiones entre primarias ni asignaciones contradictorias.

Hay **2.186.218** primarias compartidas por proteínas de hash distinto y **28.475 de 28.485** hashes de proteína presentes en varios splits. **49.118.918** ventanas originales solapan alguna ventana de otro split. Por conjunto son 39.306.452, 4.900.433 y 4.912.033. Todos los pares entre splits tienen inicios distintos. Los recuentos de pares son 695.443.761 train–validation, 697.914.950 train–test y 86.994.451 validation–test. La evaluación de estos splits mide generalización a primarias exactas no vistas. La extensión a proteínas no vistas requiere otra evaluación. H2-L conserva 4 positivos en validation y 8 en test, por lo que sus métricas aisladas serán sensibles a pocas observaciones.

Se validaron la cobertura de las **49.022.360 filas base**, **15.100.592 representaciones globales**, **14.530.324 primarias** y **49.123.503 ventanas originales**, la correspondencia de etiqueta original en cada enlace de procedencia y la coincidencia de la etiqueta global del catálogo. Un único `split_id` por primaria garantiza también un único split por par primaria/secundaria. Se verificó el contenido de los cinco Parquet de entrada antes y después. La reapertura reprodujo todas las asignaciones con la semilla registrada. El manifiesto ocupa **164.425.896 bytes** y la construcción con validación tardó **386,32 s**.

[Asignaciones](../results/nap_cnb_v2_dataset_views/splits/assignments.parquet) · [Informe de validación y firmas](../results/nap_cnb_v2_dataset_views/splits/validation.json) · [Código](../data_pipeline/scripts/data_splitting/split_nap_cnb_v2.py)

## Fase 4D · D1 global y contrato de evaluación

D1 selecciona las representaciones originales de `global_dataset.parquet`, con `label_global`. Las claves primarias y C/H/E exactas resuelven ProtT5 y SecondaryBERT, respectivamente. La primaria se une a `effective_group_id` en el manifiesto de splits de 4C. La unión conserva las distintas secundarias de una misma primaria. El archivo de configuración fija rutas relativas a la raíz del repositorio, claves, dimensiones, hashes y recuentos. Los catálogos se siguen consultando desde sus rutas originales.

| Split | Filas D1 | Positivas globales | Negativas operacionales |
|---|---:|---:|---:|
| Train | 12.083.630 | 3.076.633 | 9.006.997 |
| Validation | 1.507.558 | 383.839 | 1.123.719 |
| Test | 1.509.404 | 384.156 | 1.125.248 |
| **Total** | **15.100.592** | **3.844.628** | **11.255.964** |

La validación reabrió el manifiesto, comprobó la unicidad de los 15.100.592 pares, reprodujo las asignaciones de la semilla 42 y cotejó todas las etiquetas con el índice global. Las 14.530.324 primarias y 1.847.436 secundarias coinciden con sus catálogos certificados. Se verificaron las cabeceras NPY y rangos confirmados de los 146 shards ProtT5, y se comprobó el acceso a los 549 bloques históricos referenciados por SecondaryBERT. Los hashes de los insumos coincidieron antes y después. El manifiesto ocupa 3.356 bytes.

La consulta de metadatos es una unión por primaria. Desde la raíz del repositorio, la selección D1 se expresa en DuckDB así.

```sql
SELECT g.sequence, g.secondary_structure, g.label_global, a.split_id
FROM read_parquet('results/nap_cnb_v2_dataset_views/global_dataset.parquet') AS g
JOIN read_parquet('results/nap_cnb_v2_dataset_views/splits/assignments.parquet') AS a
  ON g.sequence = a.effective_group_id;
```

Los códigos 0, 1 y 2 corresponden a train, validation y test. Para experimentos por familia MHC, usar `base_dataset.parquet` y `label_original`, con la misma unión de particiones. El riesgo de solapamiento entre ventanas de una misma proteína es el medido en 4C. D1 evalúa primarias exactas no vistas.

[D1](../results/nap_cnb_v2_dataset_views/d1_manifest.json) · [Manifiesto de particiones](../results/nap_cnb_v2_dataset_views/splits/assignments.parquet) · [Validación de particiones](../results/nap_cnb_v2_dataset_views/splits/validation.json)

### Procedencia histórica y capacidad

El generador histórico leía CSV de clasificación con `protein_group_id`, `group_id` y etiqueta familiar. Escribía `original_seq` y `blosum_seq` junto al identificador local de grupo y a los campos de etiqueta, epítopo seleccionado y posición de la observación de origen. Esos campos son trazabilidad histórica. Una etiqueta copiada de una observación original describe un supuesto de aumento, sin evidencia experimental nueva. La ruta histórica de concatenación reutilizaba el vector de secundaria por identificador de grupo, con offsets documentados al combinar fuentes.

La auditoría registró **1.449.852.950 filas** de entradas históricas ProtT5 en **14.503 bloques** de las fuentes archivadas `*_blosum_ProtT5_chunks`. Es el tamaño de ese corpus histórico, con originales y registros derivados. La coincidencia de entrada exacta localizó **14.260.167** candidatos históricos para el conjunto original v2. La procedencia disponible de Rostlab ProtT5 carece de una revisión exacta y un tokenizador fijados por lote, por lo que la auditoría certificó **cero** de esos candidatos para reutilización. Los dos resolutores de embeddings de D1 apuntan a los almacenes certificados de 3B y 3C.

Los **12.083.630 originales de train**, multiplicados por el supuesto de 25 registros adicionales por representación, dan un techo de **302.090.750 registros**. A 4.096 bytes por vector ProtT5, el techo aritmético en el caso de un vector distinto por registro es **1.237.363.712.000 bytes**, sin contar metadatos. La cifra no mide unicidad, coincidencias, espacio temporal ni tiempo de ejecución. Como referencia medida, la fase 3B verificó 14.530.324 entradas originales en unas 7,12 horas con una RTX 3090.

[Código histórico y campos de salida](../data_pipeline/scripts/data_augmentation/generate_blosum62_variants.py) · [Auditoría de procedencia](../results/nap_cnb_v2_embedding_audit/embedding_audit_report.md) · [Medición de ProtT5](../results/nap_cnb_v2_prott5/final_report.md)

### Condiciones compartidas de evaluación

D2 queda pendiente. Para cualquier conjunto derivado admisible, validation y test deben apuntar a las mismas claves y firmas de D1. El único conjunto extensible es train. Las comprobaciones de coincidencia exacta con evaluación dependen de claves de entrada, con independencia de las etiquetas de evaluación. Cualquier fila derivada debe conservar la referencia a su observación de origen y distinguir la procedencia de la etiqueta y de la estructura, incluida `inherited_from_parent` cuando se reutilice una anotación del padre. Los catálogos originales y el índice de etiquetas globales permanecen como referencias de solo lectura para esos experimentos.
