# NAP-CNB v2 · auditoría de embeddings históricos

Se auditó la selección definitiva de **49.123.503 ventanas**. La auditoría separa la coincidencia exacta de entrada de la reutilización certificada. Los conflictos numéricos quedan pendientes de resolución.

| Métrica | ProtT5 | SecondaryBERT |
|---|---:|---:|
| Entradas únicas NAP-CNB v2 | 14.530.324 | 1.847.436 |
| Entradas con embedding histórico localizado | 14.260.167 | 1.819.032 |
| Entradas sin coincidencia localizada | 270.157 | 28.404 |
| Entradas con embedding reutilizable verificado | 0 | 1.819.032 |
| Entradas con procedencia insuficiente | 14.260.167 | 0 |
| Entradas incompatibles por valores no finitos | Sin cotejo exhaustivo | 0 |
| Entradas con candidatos numéricamente contradictorios | Sin cotejo exhaustivo | 0 |
| Entradas sin embedding reutilizable | 14.530.324 | 28.404 |
| Ventanas cubiertas | 0 | 49.083.724 |
| Ventanas pendientes | 49.123.503 | 39.779 |
| Dimensiones | 1.024 | 768 |

## Cobertura conjunta verificada

| Estado | Ventanas | Porcentaje |
|---|---:|---:|
| Ambos | 0 | 0,000 % |
| Solo ProtT5 | 0 | 0,000 % |
| Solo SecondaryBERT | 49.083.724 | 99,919 % |
| Ninguno | 39.779 | 0,081 % |
| Total | 49.123.503 | 100 % |

Por coincidencia de entrada, antes de verificar los vectores, **48.727.283** ventanas tenían candidatos para ambas modalidades. ProtT5 tenía candidatos para **48.735.569** ventanas y SecondaryBERT para **49.083.724**. Entre las **468.559** ventanas con estructura recuperada, **465.155** tienen un SecondaryBERT verificado.

## Frecuencias y contexto de proteína

| Medida | Primaria | C/H/E |
|---|---:|---:|
| Ventanas | 49.123.503 | 49.123.503 |
| Entradas únicas | 14.530.324 | 1.847.436 |
| Claves con más de una aparición | 11.440.938 | 1.558.957 |
| Apariciones adicionales sobre la primera | 34.593.179 | 47.276.067 |

Hay **15.100.592 pares únicos**. **547.627** primarias se asocian a más de una estructura y **601.847** estructuras se comparten entre primarias distintas. El cruce se hizo por la cadena C/H/E de cada observación tras resolver la recuperación por `window_id`.

## Procedencia y controles

### ProtT5

El generador documenta `Rostlab/prot_t5_xl_half_uniref50-enc` con T5Tokenizer sin minúsculas automáticas, separación por espacios y sustitución de U/Z/O/B y símbolos fuera del alfabeto por X. El límite del tokenizador es 30 tokens, con tokens especiales y padding. La media usa la máscara de atención del último estado oculto, por lo que incluye los tokens especiales activos. El código usa pesos FP16 en CUDA y exporta float32 sin normalización L2. La revisión de los pesos, el tokenizador y el entorno no están fijados por lote. [Generador](../../data_pipeline/scripts/embeddings/primary_structure/generate_prott5_embeddings.py)

Se leyeron **1.449.852.950** filas de entrada en **14.503** CSV de bloques Zstandard sin leer sus vectores. Cada bloque tenía una matriz archivada con recibo. Descontando la cabecera NPY de 128 bytes observada en las muestras, los 14.503 tamaños son múltiplos de 4.096 bytes y suman el mismo número de filas. Es una comprobación de tamaño compatible con 1.024 float32, además de las dimensiones comprobadas en la muestra. Entre las coincidencias, **14.249.139** estaban también en el índice de originales y **11.028** solo en otros registros históricos. **11.978.645** claves de v2 tenían más de un candidato histórico. **0** claves de v2 presentes en el índice histórico de originales carecen de una entrada en los CSV ProtT5. Se comparó la secuencia cruda exacta. El mapeo a X del generador no se utilizó para declarar equivalencia entre primarias crudas distintas.

La auditoría previa de 11.030 originales verificó dimensiones y finitud dentro de su muestra, y cotejó 41 direcciones contra los concatenados. Eso demuestra integridad muestral, mientras que la revisión de modelo sigue sin fijar. El cotejo exhaustivo de todos los bloques primarios implicaría cerca de 3,59 TB comprimidos. Las coincidencias ProtT5 quedan pendientes de procedencia y validación numérica, incluidas las muestras. [Auditoría anterior](exact_embeddings_sample.md) · [Presupuesto de lectura](exact_embeddings_cost.md)

### SecondaryBERT

Los once manifiestos registran el mismo BERT de `model/secondary_bert` y la huella `7714351fc71dd4c3b929d9835d00bdb7d4869e982b9fb32054e4bf9c3846b72d`, que coincide con la del modelo local. Esta huella combina contenido de configuración y metadatos de pesos. El SHA-256 actual de los pesos locales es `9f116bddfad5f9232ca4d6e1f9cc183edfb9a60d46b6925ba310f245d7e30aa3`. La clave es la cadena `clean_ss` exacta, que registra los estados efectivamente codificados. Los manifiestos indican lote 4.096 y bloques de 102.400 filas. El generador usa C=5, H=6, E=7, una secuencia de 25 estados rodeada de CLS/SEP y media del último estado oculto sobre los 25 tokens biológicos. El código aplica autocast FP16 en CUDA y escribe float32 sin normalización L2. [Generador](../../data_pipeline/scripts/embeddings/secondary_structure/generate_secondary_bert_embeddings.py)

Se leyeron **551** bloques canónicos, **55.763.575** vectores y **131,317 GB** comprimidos. Se comprobó cada checksum de archivo archivado, dimensión 768, dtype float32, finitud y correspondencia de los IDs del bloque con el CSV que contiene `clean_ss`. La salida anterior `chunks_pooled/` tiene **551** recibos de contenido distintos de los bloques vigentes. En H2-L, ambas matrices float32 tienen forma 4.448 × 768. El bloque antiguo contiene un único vector distinto frente a 2.328 en el vigente. Al comparar las matrices posición por posición, la diferencia máxima fue aproximadamente 7,44. El manifiesto vigente dirige a `chunks/`; la salida anterior carece de un manifiesto separado que fije su configuración y se mantuvo fuera de los candidatos compatibles. Se verificaron duplicados mediante SHA-256 de los valores float32 en orden, con ceros de ambos signos canonicalizados. El criterio de aceptación fue igualdad exacta, sin margen numérico. Una huella diferente o un candidato no finito mantiene la clave fuera de reutilización. **1.595.976** claves de v2 tuvieron candidatos históricos repetidos.

Los concatenados son derivados float32, con segmentos 1.024 y 768, y `normalized=false` en el manifiesto. La auditoría usa las fuentes originales para decidir identidad y compatibilidad. Los concatenados son direccionables por posición con los índices de origen. Sus comprobaciones muestrales se reutilizaron como evidencia auxiliar.

## Coste pendiente y almacenamiento

| Escenario | ProtT5 | SecondaryBERT |
|---|---:|---:|
| Entradas sin candidato exacto | 270.157 | 28.404 |
| Ventanas sin candidato exacto | 387.934 | 39.779 |
| Espacio float32 para cubrir solo ausentes | 1,107 GB | 0,087 GB |
| Entradas pendientes con los criterios de esta auditoría | 14.530.324 | 28.404 |
| Espacio float32 si se calculan todas las pendientes | 59,516 GB | 0,087 GB |

Las entradas con candidatos pendientes pueden reducir ese coste si se fija su procedencia o se resuelven los conflictos. El tiempo de inferencia se estima como entradas únicas divididas por entradas/s. A **100 entradas/s** de ProtT5 y **1.000 entradas/s** de SecondaryBERT, los escenarios completos pendientes serían **40.36 h** y **0.01 h** respectivamente. Son tasas ilustrativas, sin inferencias de benchmark.

Un índice por entrada con una dirección de 16 bytes costaría aproximadamente **0,262 GB** de direcciones en el límite superior de todas las claves. Los diccionarios de claves y sus metadatos se sumarían a esa cifra. Los vectores históricos referenciados ocupan **0 GB adicionales**. Concatenar físicamente las 49.123.503 filas en 1.792 float32 requeriría **352,117 GB** antes de metadatos y compresión.

Para la etapa posterior, usar diccionarios por entrada exacta y configuración, guardar los vectores nuevos una vez y agrupar lecturas históricas por bloque. Los NPY comprimidos requieren descomprimir el bloque para leer una fila. Las direcciones deben vincular el grupo histórico con archivo y desplazamiento verificados. El índice auxiliar de direcciones por clave queda fuera de esta auditoría.

## Integridad y archivos

Se verificaron las firmas del manifiesto definitivo y los SHA-256 de los suplementos, la unión estructural por `window_id`, la exclusión de las 81.601 ventanas, los recuentos de las once familias y la cobertura de las 49.123.503 ventanas. Los 281.555 holdouts permanecen fuera porque se leen únicamente los Parquet binarios. Las frecuencias se derivaron de las fuentes, sin alterar secuencias, etiquetas, coordenadas ni estructuras.

- `embedding_sources.tsv` inventaría las fuentes y su grado de verificación.
- `embedding_coverage_summary.tsv` registra la cobertura global y por familia.
- `missing_prott5_sequences.parquet` contiene las frecuencias, candidatos y causa por primaria pendiente.
- `missing_secondarybert_structures.parquet` contiene las frecuencias y causa por estructura pendiente.
- `verified_secondarybert_frequencies.parquet` completa las frecuencias de la modalidad con las claves verificadas.

Los inventarios y TSV ocupan **63.439.877 bytes**, sin incluir este informe.
