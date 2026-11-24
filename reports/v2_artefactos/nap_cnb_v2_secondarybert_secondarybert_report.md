# NAP-CNB v2 · SecondaryBERT, fase 3C

**Fase 3C cerrada y validada el 20 de noviembre de 2026.** Los 1.819.032 embeddings históricos y los 1.000 embeddings del piloto se reutilizaron. La ejecución completa generó las 27.404 claves restantes. SecondaryBERT cubre las **49.123.503 ventanas originales** mediante las **1.847.436 estructuras C/H/E exactas**.

## Modelo, fuentes y compatibilidad

Las once fuentes `*_SecondaryBERT_by_group` documentan `model/secondary_bert`, un `BertForMaskedLM` de 12 capas, 12 cabezas y dimensión oculta 768. La huella histórica **7714351fc71dd4c3b929d9835d00bdb7d4869e982b9fb32054e4bf9c3846b72d** coincide con la local. Esta huella se basa en configuración y metadatos de los pesos. El SHA-256 de los pesos locales **9f116bddfad5f9232ca4d6e1f9cc183edfb9a60d46b6925ba310f245d7e30aa3** coincide con el medido en la auditoría. El SHA-256 del tokenizer local está registrado en el piloto.

El generador actual conserva la correspondencia C=5, H=6, E=7 y construye 27 tokens por entrada, con CLS=2 y SEP=3. La clave histórica `clean_ss` contiene los 25 estados realmente codificados. El flujo nuevo valida las claves del inventario tal como están. Extrae la última capa oculta del encoder, promedia las 25 posiciones biológicas con autocast FP16 en CUDA y almacena 768 valores float32 por vector. Los trabajos históricos usaron lotes de 4.096 y bloques de 102.400 filas archivados en NPY/Zstd. El piloto usó lotes de 256 en una sola GPU.

La auditoría previa comprobó integridad en 551 bloques canónicos, incluidos finitud, dimensión, IDs y coincidencia exacta entre candidatos duplicados. El piloto comprobó compatibilidad numérica con **24 claves del primer bloque de cada una de las once fuentes**, 264 comparaciones en total. Verificó el SHA-256 del NPY descomprimido contra su recibo de archivo y obtuvo **diferencia máxima 0, RMSE máximo 0 y coseno mínimo 1**. Los criterios fijados fueron diferencia absoluta máxima ≤ 0,01, RMSE máximo por fila ≤ 0,002 y coseno mínimo ≥ 0,99999. El muestreo por fuente complementa la evidencia previa de procedencia e integridad. La comparación numérica está acotada a los bloques muestreados. Los archivos legacy `chunks_pooled` quedan fuera del índice por sus diferencias documentadas.

[Auditoría previa](../../reports/audits/nap_cnb_v2_embedding_audit.md) · Fuentes históricas (`../nap_cnb_v2_embedding_audit/embedding_sources.tsv`, artefacto retirado) · [Evidencia numérica por fuente](pilot.json)

## Inventario y cobertura por clave C/H/E exacta

| Estado | Estructuras únicas | Ventanas originales |
|---|---:|---:|
| Históricas verificadas y accesibles por referencia | 1.819.032 | 49.083.724 |
| Generadas y verificadas en el piloto | 1.000 | 1.423 |
| Generadas en la ejecución completa | 27.404 | 38.356 |
| Pendientes de generación | 0 | 0 |
| Total | 1.847.436 | 49.123.503 |

Los dos inventarios contienen claves distintas entre sí de exactamente 25 caracteres C/H/E. Antes del piloto faltaban **28.404 estructuras y 39.779 ventanas**, en línea con la auditoría. Se contrastaron esas claves pendientes con los metadatos de las once fuentes canónicas, sin encontrar coincidencias. Todas las claves históricas auditadas quedaron asociadas con una fila canónica. La construcción cotejó los IDs y el orden de los metadatos con el índice de origen y guardó una referencia por clave, repartida en 549 bloques. Se conservan la longitud, el SHA-256 y la frecuencia de cada clave. Los archivos históricos, ProtT5 y la selección definitiva se consultaron en modo de lectura cuando correspondía.

La reapertura confirmó **1.847.436 / 1.847.436 estructuras** y **49.123.503 / 49.123.503 ventanas**. Cada clave exacta, su SHA-256 y su frecuencia coincidieron con los inventarios de la selección definitiva. No quedaron claves pendientes ni asociaciones dobles.

## Piloto, rendimiento y almacenamiento

Tras comprobar que la GPU física 2 estaba libre, se utilizó esa RTX 3090 con lote 256, PyTorch 2.14.0+cu130 y Transformers 5.17.0. La muestra con semilla 20261120 incluyó 370 claves con predominio de C, 305 de H y 325 de E. En los empates se siguió el orden C/H/E. Hubo 690 claves con los tres estados y entre 2 y 12 transiciones. Las dos inferencias coincidieron bit a bit. La relectura recuperó una matriz de **1.000 × 768**, float32 y finita, verificando el digest asociado a cada clave. Se probó también una consulta que combina un vector histórico con los del piloto.

| Medida | Resultado |
|---|---:|
| Inferencia de dos pasadas de 1.000 claves y escritura de una | 0,663 s |
| Carga del modelo | 0,905 s |
| Pico de VRAM asignada durante el piloto | 487 MiB |
| Construcción del índice | 181,37 s |
| Base SQLite con el piloto | 288.477.184 bytes |
| Carga, descompresión y comprobación de un bloque histórico muestreado | 0,33–6,82 s, mediana 4,73 s |

## Ejecución completa y validación final

El comando documentado `python -m data_pipeline.scripts.embeddings.secondary_structure.secondarybert_v2 generate` se ejecutó en la RTX 3090 física 2 con el checkpoint, tokenizador, software y lote 256 del piloto. La comprobación previa confirmó el índice SQLite, los 1.000 embeddings del piloto, las 27.404 claves pendientes, el espacio disponible y la accesibilidad de los 551 archivos comprimidos canónicos y sus recibos. Se usó la evidencia de compatibilidad existente.

| Medida | Resultado |
|---|---:|
| Inferencia y escritura de los 27.404 vectores | 13,99 s |
| Tiempo de pared del comando, con arranque y comprobación interna | 88,81 s |
| SQLite final | 416.288.768 bytes |
| Crecimiento de SQLite desde el piloto | 127.811.584 bytes |
| Datos float32 de los 28.404 vectores generados entre piloto y ejecución | 87.257.088 bytes |

Cada lote se confirmó en una transacción. Tras cerrar y reabrir la base en modo lectura, `quick_check` devolvió `ok` y `foreign_key_check` no encontró errores. Se verificaron las 28.404 filas generadas entre piloto y ejecución, con 768 valores float32 finitos y digest válido de clave más vector en cada fila. Los 1.000 digests del piloto coincidieron con sus valores previos y el SHA-256 de `pilot.json` se mantuvo. Se recuperaron juntos un vector histórico, uno del piloto y uno nuevo. La reapertura no ejecutó inferencia.

Los históricos siguen referenciados en SQLite por archivo y posición. Se reutilizó su auditoría de integridad y se comprobó la lectura del archivo histórico recuperado contra su recibo SHA-256. La mediana observada en el piloto, 4,73 s por bloque comprimido, sigue siendo una limitación para las futuras lecturas aleatorias. Durante la preparación del entrenamiento se evaluarán la agrupación por archivo, la caché, la lectura por lotes y, si es necesaria, la consolidación. Los vectores históricos siguen en sus archivos originales.

No hubo incidencias durante la generación ni durante su validación. El generador y el procedimiento del piloto se conservaron. ProtT5 mantiene su cobertura verificada de 49.123.503 ventanas con 1.024 dimensiones. Ambas representaciones quedan disponibles por separado para una futura carga de 1.792 dimensiones.

[Procedimiento y recuperación](../../docs/PIPELINE.md) · [Índice SQLite](index.sqlite) · [Evidencia del piloto](pilot.json)
