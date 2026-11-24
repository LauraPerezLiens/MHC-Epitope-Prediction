# Índice de originales D1

`original_index.parquet` conserva las etiquetas y los identificadores certificados.
`group_id` identifica la secuencia primaria y `observation_id` identifica la
observación primaria–C/H/E. Cada fila incluye el bloque D1 y el índice de fila
dentro del bloque, ambos de base cero. El vector SecondaryBERT está en las
columnas 1024 a 1791 de esa fila de la matriz D1. El manifiesto registra la
revisión de origen y el estado del directorio.

## Piloto histórico H2-L

`historical_h2_l/variants.parquet` y `historical_h2_l/features.npy` se alinean por fila.
Contienen **89.179 variantes archivadas** de **3.569 observaciones TRAIN**.
Las primeras 1.024 columnas son ProtT5 de los dos bloques históricos verificados.
Las 768 restantes son el vector SecondaryBERT de la fila padre en D1, comprobado bit a bit.

Se cotejaron los índices maestros, los metadatos por bloque y las claves de ventana históricas.
De 89.775 filas con padre TRAIN se retiraron
46 con primaria exacta en VALIDATION o TEST y
550 copias equivalentes del mismo par padre–variante.
VALIDATION y TEST siguen siendo los originales certificados de D1.

La etiqueta de entrenamiento de cada variante se heredó de D1. La etiqueta de la
fuente histórica se conserva por separado y difiere de la heredada en
51.717 filas. Heredar la etiqueta supone
que la sustitución preserva la clase para fines de entrenamiento. Es una
hipótesis metodológica que se evalúa sobre originales reservados. Tanto la
etiqueta heredada como la estructura reutilizada son aproximaciones de la aumentación.

Se cotejaron los embeddings primarios de **3.569 padres** con los
embeddings históricos de sus mismos originales. Coincidieron bit a bit
**0**. Distancia L2 mediana
**0,00178512** y rango **0,00110911–0,0537279**.
La procedencia del encoder histórico y su equivalencia con el certificado
quedan pendientes. El piloto cubre una familia y su comparación con E1/E2
mezclaría el efecto de la aumentación con la representación histórica. Para
aislar el efecto en este subconjunto, ambos brazos deben compartir la misma
representación de los originales y evaluarse sobre los mismos originales reservados.
E3 y E4 siguen pendientes.

Los scripts `recover_historical_h2_l.py` y `check_historical_primary.py` reproducen
la recuperación y el control pareado desde la raíz del repositorio con Python de
`nap_env`. El primero publica el piloto en un subdirectorio nuevo.

