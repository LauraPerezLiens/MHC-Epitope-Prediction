# Recuperación de coordenadas de epítopos

Se reprodujeron los **102,654** eventos del grupo original. La búsqueda mantuvo la URL completa y la versión del FASTA archivado de cada proteína.

| Ocurrencias exactas en la proteína FASTA | Eventos |
|---|---:|
| Una | 102,420 |
| Varias | 234 |
| Ninguna dentro del grupo de 102.654 | 0 |
| Ninguna, categoría separada de la auditoría original | 5,149 |

## Coordenadas fuente

- `both_absent`: 0 eventos del grupo original.
- `partially_absent`: 0 eventos del grupo original.
- `contradictory_or_invalid`: 102,654 eventos del grupo original.
- `correct_length_wrong_residues`: 100,550 eventos.
- `outside_fasta_or_invalid_order`: 2,104 eventos.

Desplazamientos más frecuentes entre el intervalo fuente y el inferido: (+1, +1) en 4,482, (-1, -1) en 1,680, (+25, +25) en 1,548, (+2, +2) en 1,242, (+3, +3) en 1,179. Los desplazamientos no son uniformes.

Las coordenadas contradictorias o inválidas requieren revisión aunque la secuencia tenga una única ocurrencia. Las coincidencias múltiples no se resolvieron por proximidad.

## Ventanas candidatas que contienen la ocurrencia única

- 583,806 de 596,063 filas.
- 167,902 ventanas por proteína y posición.
- 167,502 secuencias de ventana distintas.
- 583,806 filas tienen al menos un evento con coordenadas fuente contradictorias o inválidas.

| Familia de la ventana | Filas |
|---|---:|
| HLA-A | 130,517 |
| HLA-B | 128,438 |
| HLA-C | 105,473 |
| HLA-DP | 60,264 |
| HLA-DQ | 28,521 |
| HLA-DR | 83,093 |
| H2-D | 15,105 |
| H2-K | 24,023 |
| H2-L | 32 |
| H2-IA | 7,971 |
| H2-IE | 369 |

Las posiciones son 1-based e inclusivas e inferidas por una coincidencia única en FASTA. El resultado se conserva por separado de los epítopos con coordenadas originales verificadas.

## Ejemplos

- `www.uniprot.org/uniprot/A0A087WZ13`, HLA-A, ventana en 503, epítopo `HSLLPASNL` inferido en 513–521.
- `www.uniprot.org/uniprot/A0A096LP25`, HLA-A, ventana en 1070, epítopo `GPMAGKPFRPQSL` inferido en 1082–1094.
- `www.uniprot.org/uniprot/A0A0A0MQW0`, HLA-A, ventana en 417, epítopo `FGDSFGRLGGGM` inferido en 428–439.
- `www.uniprot.org/uniprot/A0A0A0MS15`, HLA-A, ventana en 18, epítopo `LVQPGRSL` inferido en 30–37.
