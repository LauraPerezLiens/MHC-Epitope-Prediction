# Auditoría de epítopos positivos potencialmente omitidos

Primeras 10,000 filas de cada familia. La evidencia se leyó completa de las once familias.

- Proteínas revisadas: 197
- Epítopos positivos distintos: 681,805
- Pares proteína–epítopo: 706,158
- Ocurrencias positivas con coordenadas verificadas y longitud ≤25: 655,192
- Filas revisadas: 104,448 (69,091 sin anotación global positiva)

| Evidencia | Filas | Ventanas distintas | Secuencias distintas |
|---|---:|---:|---:|
| coordinate_verified | 0 | 0 | 0 |
| sequence_only | 463 | 395 | 395 |
| Cualquier candidato | 463 | 395 | 395 |

Filas con coincidencias exclusivamente de secuencia: 463. Una fila puede aparecer en las dos categorías.

| Familia | Filas revisadas | Coordenadas verificadas | Coincidencia de secuencia |
|---|---:|---:|---:|
| HLA-A | 10,000 | 0 | 0 |
| HLA-B | 10,000 | 0 | 0 |
| HLA-C | 10,000 | 0 | 0 |
| HLA-DP | 10,000 | 0 | 105 |
| HLA-DQ | 10,000 | 0 | 56 |
| HLA-DR | 10,000 | 0 | 167 |
| H2-D | 10,000 | 0 | 15 |
| H2-K | 10,000 | 0 | 0 |
| H2-L | 4,448 | 0 | 32 |
| H2-IA | 10,000 | 0 | 13 |
| H2-IE | 10,000 | 0 | 75 |

## Ambigüedades y revisión

- Ventanas sin coordenadas verificadas contra FASTA: 0.
- Ventanas con versiones FASTA incompatibles: 0.
- Eventos de evidencia con `missing_or_conflicting_epitope_coordinates`: 102,654.
- Eventos de evidencia con `epitope_absent_from_archived_fasta`: 5,149.
- Eventos de evidencia con `missing_protein_or_epitope`: 4,007.
- Eventos de evidencia con `missing_fasta`: 1,299.
- Eventos de evidencia con `positive_longer_than_window`: 5,502.

Los identificadores de proteína se compararon por URL completa y secuencia FASTA cuando estaba disponible. Las versiones conflictivas dentro de un mismo origen se excluyeron de los hallazgos. Los aciertos por secuencia no confirman el locus. La muestra por prefijo no permite extrapolar tasas.
Revisar los aciertos por coordenadas y resolver identidad y locus de los ambiguos antes de decidir cambios de etiqueta.

## Ejemplos

- sequence_only en `www.uniprot.org/uniprot/A0A096LP25`, HLA-DP, ventana `NKGPQLQKEAVSGPMAGKPFRPQSL` en 1070, epítopo `GPMAGKPFRPQSL` (?–?), etiqueta global 0.
- sequence_only en `www.uniprot.org/uniprot/A0A0A0MS15`, HLA-DP, ventana `QCEVQLVESGGGLVQPGRSLRLSCT` en 18, epítopo `LVQPGRSL` (?–?), etiqueta global 0.
- sequence_only en `www.uniprot.org/uniprot/A0A0B4J1Z2`, HLA-DP, ventana `FIYYASSLQSGVPSRFSGSGSGTDY` en 69, epítopo `SRFSGSGSGTDY` (?–?), etiqueta global 0.
- sequence_only en `www.uniprot.org/uniprot/A0A0B4J1Z2`, HLA-DP, ventana `YYASSLQSGVPSRFSGSGSGTDYTL` en 71, epítopo `SRFSGSGSGTDYTL` (?–?), etiqueta global 0.
