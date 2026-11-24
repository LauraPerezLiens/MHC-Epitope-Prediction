# NAP-CNB · Partición por componentes de proteína sobre D1

Mide cuánto del rendimiento de E1 y E2 depende de que ventanas de la misma
proteína aparezcan en varias particiones. **Resultado: prácticamente nada.**

## Unidad de partición

Una misma ventana de 25 aa aparece en varias proteínas, de modo que repartir por
`parent_accession` seguiría colocando la misma primaria en dos particiones. Se
construyeron las componentes conexas del grafo bipartito (primaria, proteína), que
son la unidad indivisible del reparto.

| Medida | Valor |
|---|---:|
| Ventanas de las once familias | 49.205.104 |
| Primarias distintas | 14.554.919 |
| Proteínas distintas (`parent_accession`) | 28.872 |
| Fusiones por primaria compartida | 12.523 |
| **Componentes independientes** | **16.349** |
| Componentes con una sola proteína | 8.265 (50,6 %) |
| Proteínas en componentes multiproteína | 20.607 (71,4 %) |
| Componente mayor | 73 proteínas |

Los 16.349 componentes son el número de unidades independientes del estudio, no
los 49,1 millones de ventanas. Reparto con semilla 42 y objetivo 80/10/10 por
filas, colocando cada componente en la partición con mayor déficit relativo:

| Partición | Componentes | Filas | Positivos | Prevalencia |
|---|---:|---:|---:|---:|
| TRAIN | 13.105 | 12.079.478 | 3.111.466 | 25,7583 % |
| VALIDATION | 1.504 | 1.510.799 | 364.872 | 24,1509 % |
| TEST | 1.701 | 1.510.315 | 368.290 | 24,3850 % |

Las 15.100.592 filas de D1 se asignaron sin ninguna sin componente. Los tamaños
son casi idénticos a los de D1 (12.083.630 / 1.507.558 / 1.509.404), de modo que la
diferencia de métricas no se debe al volumen de entrenamiento. El componente es
indivisible, así que la prevalencia no puede igualarse exactamente.

## Protocolo

Idéntico a E1 y E2 salvo la partición: 1.792 características en orden
ProtT5 (1.024) + SecondaryBERT (768), 3 épocas, AdamW 1e-3 / 1e-4, lotes de 8.192,
prevalencia natural, semilla 42, selección de época por mínima log loss de
VALIDATION, umbral por F1 máximo en VALIDATION y TEST puntuado una sola vez.

El scaler **se reajustó sobre el nuevo TRAIN**, con momentos poblacionales en
float64 sobre las 12.079.478 filas y SHA-256
`2470f082007368ca00de8d8b5d799b3984558747f5d60a735b50b1684060e7d7`. Reutilizar el
de E1 habría filtrado las proteínas de TEST a través de la normalización.

Lectura secuencial de los 61 bloques materializados de D1, con VALIDATION y TEST
en caché local. El acceso disperso a ese volumen rinde 2 MiB/s, frente a
155–514 MiB/s en secuencial, de ahí la lectura por bloques completos.

## Resultados en TEST

| Modelo | Partición | ROC-AUC | AP | Prevalencia | AP / prevalencia | Log loss |
|---|---|---:|---:|---:|---:|---:|
| LR | primaria exacta | 0,654641 | 0,375738 | 0,25451 | 1,4763 | 0,539791 |
| **LR** | **componentes** | **0,662294** | 0,379399 | 0,24385 | **1,5559** | **0,523927** |
| MLP | primaria exacta | 0,680107 | 0,412129 | 0,25451 | 1,6193 | 0,527197 |
| **MLP** | **componentes** | **0,674668** | 0,395093 | 0,24385 | **1,6202** | **0,522958** |

- Δ MLP (componentes − primaria): ROC-AUC **−0,005438**, AP −0,017036.
- Δ LR (componentes − primaria): ROC-AUC **+0,007653**, AP +0,003661.

La caída de AP de la MLP se explica por la prevalencia, no por el modelo: la AP
normalizada por la prevalencia es **1,6193 frente a 1,6202**, es decir, igual. La
capacidad de ordenación no cambia al eliminar la fuga.

Matrices de confusión en TEST, filas de clase real y columnas de predicha:

- LR componentes `[[581295, 560730], [103729, 264561]]`
- MLP componentes `[[617510, 524515], [108312, 259978]]`

## Conclusión: la fuga por proteína no inflaba las métricas

Eliminar por completo el solapamiento de proteínas entre particiones cuesta
0,0054 de ROC-AUC en la MLP y **mejora** 0,0077 en la LR. **El nivel de 0,66–0,68
es generalización real a proteínas no vistas**, no un artefacto.

Esto refuta la hipótesis de que el 0,680 de E2 estuviera inflado por los vecinos
inmediatos en TRAIN. La explicación del 0,7955 histórico sigue siendo su
partición **por fila**, que es una fuga mucho más severa: con 26 variantes
BLOSUM62 de la misma ventana repartidas por fila, TEST contenía casi duplicados
exactos de filas de TRAIN. La partición por primaria exacta ya eliminaba eso.

Por tanto el techo de rendimiento no se explica por fuga, ni por ruido de etiqueta
—D1 no tiene ni un grupo mixto por primaria—, ni por corrupción de embeddings.
Queda atribuido a la **representación y la formulación de la tarea**: la media
sobre 25 posiciones para una etiqueta que depende de un 8–11mero, y la ausencia
del alelo en la entrada.

## Las dos ejecuciones no habían convergido

| Época | LR componentes | MLP componentes | MLP primaria exacta (E2) |
|---:|---:|---:|---:|
| 1 | 0,534774 | 0,551828 | 0,536629 |
| 2 | 0,533056 | 0,541125 | **0,527658** |
| 3 | **0,520353** | **0,517833** | 0,542042 |

Log loss de VALIDATION. E2 toca su mínimo en la época 2 y empeora en la 3: se
sobreajusta. **Los dos modelos con partición por componentes descienden de forma
monótona y seguían mejorando al terminar la época 3.** Es coherente con que la
partición por componentes sea más difícil de sobreajustar, al no haber vecinos
casi idénticos que memorizar.

En consecuencia, 0,674668 es una **cota inferior** del rendimiento alcanzable con
este protocolo, y tres épocas son insuficientes. Repetir con 10 épocas es el
siguiente experimento de mayor valor por coste: unas tres horas por modelo.

## Artefactos

`results/nap_cnb_v2_protein_split/` contiene `build_components.py`,
`assign_splits.py`, `experiment.py`, el mapa `primary_components.npz`, las
asignaciones `row_splits.npz` y `component_assignment.npz`, los tamaños en
`component_sizes.json`, el resumen `split_summary.json`, el recibo `prepare.json`
y los subdirectorios `lr/` y `mlp/` con configuración, checkpoints, selección y
métricas.
