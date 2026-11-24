# Auditoría de redundancia exacta de embeddings

Alcance: prefix_plus_addressed_shuffle_sample. Corpus: 15,135,904 secuencias distintas.

| Medida | Total |
|---|---:|
| Observaciones originales comparadas | 11,030 |
| Secuencias distintas en la auditoría | 8,703 |
| Secuencias repetidas | 1,203 |
| Repetidas con todos los ProtT5 iguales | 1,203 |
| Repetidas con todos los SecondaryBERT iguales | 1,197 |
| Repetidas con ambas modalidades iguales en todas sus observaciones | 1,197 |
| Repetidas con algún par ProtT5 igual | 1,203 |
| Repetidas con algún par SecondaryBERT igual | 1,198 |
| Repetidas con algún par igual en ambas modalidades | 1,198 |
| Secuencias con más de una representación conjunta | 6 |
| Filas que podrían retirarse en el alcance auditado | 2,321 |
| Filas que quedarían en el alcance auditado | 8,709 |
| Pares de embeddings idénticos con etiquetas globales diferentes | 0 |
| Secuencias exactas con etiquetas globales contradictorias | 0 |

## Comparación tras barajar

Se cotejaron 41 originales con direcciones de origen explícitas. Diferencias ProtT5: 0. Diferencias SecondaryBERT: 0.

## Procedencia y límites

El primer registro de cada grupo de 26 corresponde a la secuencia original. Las direcciones y los metadatos del grupo, proteína y etiqueta original se verifican frente a los archivos. La deduplicación propuesta usa secuencia, ambas modalidades y etiqueta global.
SHA-256 solo selecciona candidatos. Cada igualdad declarada se verifica valor por valor en float32, sin tolerancia. Los ceros con signo se consideran numéricamente iguales. Los no finitos se rechazan.
La muestra combina prefijos por familia y originales del primer bloque local rastreados en los primeros chunks barajados. Sus proporciones no se extrapolan al corpus.
La tabla propuesta conserva una fila por observación y su representante. Revisar conflictos y decidir cómo preservar la procedencia y los futuros splits antes de aplicar una limpieza.

## Ejemplos

- Secuencia `AACLCFRSEQEDEVLLVSSSRYPDQ`, origen 1:360 → representante 0:20.
- Secuencia `AACLCFRSEQEDEVLLVSSSRYPDQ`, origen 2:20 → representante 0:20.
- Secuencia `AACLCFRSEQEDEVLLVSSSRYPDQ`, origen 5:20 → representante 0:20.
- Secuencia `AAFISRLSISKDNSKSQVFFKMNSL`, origen 7:187 → representante 6:248.
- Secuencia `AAFISRLSISKDNSKSQVFFKMNSL`, origen 9:329 → representante 6:248.
- Origen 9:0:91676 → barajado 0:23817, ProtT5 exacto True, SecondaryBERT exacto True.
- Origen 9:0:46046 → barajado 0:35152, ProtT5 exacto True, SecondaryBERT exacto True.
- Origen 1:0:47866 → barajado 0:51106, ProtT5 exacto True, SecondaryBERT exacto True.
