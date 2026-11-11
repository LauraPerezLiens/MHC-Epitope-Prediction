# Registro de pruebas del MLP: desde BatchNorm hasta la mezcla global de muestras

Recopilación histórica: 26 de octubre de 2026. Actualización histórica: 28 de octubre de 2026. Retirada de archivos: 10 de noviembre de 2026.
Las secciones 1–13 conservan la instantánea histórica; la sección 14 recoge
el estado posterior y la preparación de datos en curso. Este documento es una instantánea,
no un informe de 100 épocas completadas en todos los experimentos.
Los valores históricos se han reconstruido de historiales JSONL archivados;
BatchNorm procede del registro técnico conservado antes de borrar sus salidas.

## 1. Configuración de referencia y cómo interpretar las cifras

Se ha trabajado con clasificación binaria sobre embeddings precomputados:
ProtT5, 1.024 dimensiones, y SecondaryBERT, 768 dimensiones: 1.792 en total.
La arquitectura de referencia es 1792 → 512 → 128 → 1, con normalización,
ReLU y dropout 0,30. Se usa BCEWithLogitsLoss, AdamW, learning rate inicial
0,001, weight decay 0,0001 y batches de 8.192 filas, 4.096 por clase.
El scheduler de las escaleras es cosine con warm restarts: T0=20 épocas,
Tmult=1 y learning rate mínimo 0,00001. Semilla 42; 100 épocas por etapa,
sin early stopping, sobre una GPU por entrenamiento.

Los datos están preparados en 11 datasets y 14.503 chunks físicos. TRAIN,
VALIDATION y TEST se distinguen por split_id. La política acordada es dividir
por filas: se permite compartir grupos/proteínas entre splits. No se ha
redefinido esta política como un split por grupos. Los resultados no prueban
generalización a proteínas o grupos totalmente nuevos.

En las escaleras se reutilizan los pesos del best de la etapa anterior y se
reinician optimizador y scheduler. Por tanto, son entrenamientos acumulativos,
no modelos independientes entrenados desde cero para cada tamaño.

Salvo que se indique lo contrario, las tablas muestran el checkpoint con menor
TEST loss de la etapa, no necesariamente la última época ni la máxima accuracy.
TEST participa en la selección: estos resultados son exploratorios. VALIDATION
no ha sustituido a TEST como criterio de selección en las pruebas realizadas.

## 2. BatchNorm: baseline y diagnóstico de estadísticas de inferencia

Se completaron un baseline y una ejecución diagnóstica de 10 chunks y 100 épocas.
El síntoma fue una discrepancia entre el comportamiento en entrenamiento y en
modo evaluación. Se evaluaron los mismos pesos y muestras con las estadísticas
acumuladas de BatchNorm y, como diagnóstico, con estadísticas del batch,
desactivando dropout y evitando modificar el modelo original.

Resultados de TEST en época 100 conservados en la documentación:

| Normalización / evaluación | Loss | Accuracy | Recall | ROC-AUC |
|---|---:|---:|---:|---:|
| BatchNorm, estadísticas acumuladas | 1,880200 | 76,9167 % | 53,8600 % | 0,986282 |
| BatchNorm, estadísticas del batch — diagnóstico | 0,050603 | 98,5450 % | 98,3391 % | 0,998883 |
| LayerNorm, evaluación normal | 0,003121 | 99,9170 % | 99,8538 % | 0,999991 |

Interpretación: el modo de normalizar en inferencia afectaba fuertemente al
resultado de BatchNorm. Una AUC alta con accuracy/recall y loss peores también
indica que ordenar ejemplos y clasificarlos con el umbral fijo no es lo mismo.
La evaluación con estadísticas del batch fue un diagnóstico, no una validación
de un modelo independiente de la composición del batch en inferencia.

También se inició una escalera BatchNorm, que se detuvo durante la etapa de
20 chunks. Sus salidas y scripts se eliminaron por decisión del usuario; no
queda una tabla numérica fiable de esa etapa. Se decidió continuar con LayerNorm.

## 3. Sustitución de BatchNorm por LayerNorm

Se sustituyeron las dos capas de normalización por LayerNorm. Esta normaliza
las activaciones de cada muestra, sin running mean/variance dependientes de
los batches. El primer entrenamiento de 10 chunks completó 100 épocas.

- Mejor checkpoint: época 98, TEST loss 0,002926; accuracy 99,9269 %;
  recall 99,8738 %; AUC 0,999990; 3 falsos positivos y 19 falsos negativos.
- Último checkpoint: época 100, loss 0,003121; accuracy 99,9170 %;
  3 falsos positivos y 22 falsos negativos.
- TEST evaluado: 30.104 filas, 15.052 por clase.

Conclusión operativa: LayerNorm resolvió en esta prueba la fuerte diferencia
asociada a las estadísticas de BatchNorm y se adoptó para los siguientes ensayos.
La comparación fue con una semilla; no demuestra universalmente que una
normalización sea superior en cualquier población.

## 4. Escalera de 10 en 10, LayerNorm y cosine, sin shuffled entre épocas

Etapas 10, 20, 30…; scaler ajustado con TRAIN de 2 chunks; orden de chunks fijo
entre épocas. Las muestras se barajaban dentro del entrenamiento, pero no el
orden de visita de los chunks. TRAIN EVAL y TEST EVAL balanceaban globalmente
con todas las positivas del split de la etapa y otras tantas negativas fijas.

| Chunks | Épocas completadas | Época best | TEST loss | Accuracy | Recall | ROC-AUC |
|---:|---:|---:|---:|---:|---:|---:|
| 10 | 100 | 98 | 0.002926 | 99.9269 % | 99.8738 % | 0.999990 |
| 20 | 100 | 100 | 0.003898 | 99.8859 % | 99.7902 % | 0.999991 |
| 30 | 100 | 100 | 0.005635 | 99.8248 % | 99.7578 % | 0.999966 |
| 40 | 100 | 100 | 0.010749 | 99.6793 % | 99.5837 % | 0.999907 |
| 50 | 100 | 100 | 0.015396 | 99.5222 % | 99.2825 % | 0.999882 |
| 60 | 100 | 100 | 0.041782 | 98.5328 % | 97.7107 % | 0.999421 |
| 70 | 100 | 100 | 0.048620 | 98.2409 % | 97.1894 % | 0.999216 |
| 80 | 100 | 100 | 0.048334 | 98.2566 % | 97.2959 % | 0.999075 |
| 90 | 71 | 60 | 0.055978 | 97.9806 % | 96.9819 % | 0.998624 |

La etapa de 90 chunks se detuvo durante la época 72, dejando 71 completas.
Al ampliar la escalera empeoraron loss y recall; la accuracy de best pasó de
99,93 % en 10 chunks a 97,98 % en la etapa parcial de 90.
Esto no permite concluir que añadir datos sea perjudicial: cambian la población
de evaluación, su heterogeneidad y el historial acumulado de entrenamiento.

Se revisó además la composición de los chunks con un análisis auxiliar. Se
plantearon diferencias entre datasets y efectos del orden como explicaciones;
no se realizó una intervención controlada que aislase una única causa.

## 5. Barajar el orden de los chunks en cada época: shuffled

Se creó una variante que cambia únicamente el orden de visita TRAIN de los
chunks por época, de forma determinista con semilla y época. Se mantuvieron
el subconjunto de chunks de cada etapa y las muestras de evaluación fijas.
La primera etapa comenzó desde cero; las siguientes heredaron su propio best.

| Chunks | Épocas completadas | Época best | TEST loss | Accuracy | Recall | ROC-AUC |
|---:|---:|---:|---:|---:|---:|---:|
| 10 | 100 | 93 | 0.002078 | 99.9502 % | 99.9269 % | 0.999995 |
| 20 | 100 | 95 | 0.002680 | 99.9121 % | 99.8550 % | 0.999994 |
| 30 | 100 | 95 | 0.003949 | 99.8973 % | 99.8422 % | 0.999974 |
| 40 | 100 | 96 | 0.006852 | 99.8031 % | 99.7665 % | 0.999947 |
| 50 | 100 | 77 | 0.009908 | 99.6910 % | 99.6000 % | 0.999930 |
| 60 | 8 | 8 | 0.039510 | 98.5424 % | 98.0706 % | 0.999097 |

La etapa de 60 se detuvo durante la época 9; sus valores proceden de solo
8 épocas completas y no equivalen a un entrenamiento de 100 épocas.

Comparación de loss best con y sin shuffled, ambas etapas completas:

| Chunks | Sin shuffled | Con shuffled | Reducción relativa de loss |
|---:|---:|---:|---:|
| 10 | 0.002926 | 0.002078 | 29.0 % |
| 20 | 0.003898 | 0.002680 | 31.3 % |
| 30 | 0.005635 | 0.003949 | 29.9 % |
| 40 | 0.010749 | 0.006852 | 36.3 % |
| 50 | 0.015396 | 0.009908 | 35.6 % |

La mejora fue consistente en 10–50 chunks. En 40 chunks los errores pasaron de
456 a 280; en 50, de 903 a 584. El efecto incluye los pesos acumulados desde
etapas anteriores; no son cinco experimentos independientes desde cero.

Se observó que muchos best aparecían cerca de la época 100. Se planteó prolongar
hasta 200 épocas, pero no se ejecutó esa comparación. Los mínimos tienden a
coincidir con el final de los ciclos cosine de 20 épocas.

## 6. StandardScaler: 2 chunks, prueba de 10 y cálculo de todos los chunks

El scaler original se ajustaba con todas las filas TRAIN de 2 chunks físicos,
independientes de los chunks seleccionados para cada etapa del MLP.
Se preparó una comparación con 10 chunks; se terminó retirando su carpeta al
optar por calcular el scaler completo. No se conservan aquí cifras verificables
de esa comparación 2 frente a 10 y no se inventa una conclusión cuantitativa.

El scaler completo terminó con 14.503 chunks y **1.159.882.361 filas TRAIN**.
No utilizó filas de TEST ni VALIDATION para estimar medias y escalas.

| Diferencia frente al scaler de 2 chunks | Primary, 1.024 variables | Secondary, 768 variables |
|---|---:|---:|
| Desplazamiento mediano de medias, en sigma del scaler completo | 0,110 | 0,215 |
| Diferencia mediana relativa de escala | 5,11 % | 4,70 % |
| Diferencia máxima relativa de escala | 28,87 % | 18,65 % |
| Variables con diferencia de escala mayor del 10 % | 169 —16,5 %— | 76 —9,9 %— |
| Diferencia RMS entre valores normalizados sobre todo TRAIN | 0,179 | 0,236 |

Cambian las medias y escalas de las 1.792 características. La diferencia
justificaba probar el entrenamiento, pero no demostraba de antemano una mejora.
El scaler completo es el que usa la ejecución actual.

## 7. Escalera shuffled con el scaler completo

Se creó una copia del entrenamiento shuffled que carga el scaler completo sin
calcularlo y usa una carpeta independiente. La etapa de 10 comenzó desde cero.

| Chunks | Épocas completadas | Época best | TEST loss | Accuracy | Recall | ROC-AUC |
|---:|---:|---:|---:|---:|---:|---:|
| 10 | 100 | 96 | 0.003006 | 99.9336 % | 99.9070 % | 0.999988 |
| 20 | 100 | 95 | 0.002944 | 99.9167 % | 99.8581 % | 0.999996 |
| 30 | 20 | 20 | 0.010867 | 99.6532 % | 99.4496 % | 0.999915 |

Las etapas de 10 y 20 completaron 100 épocas. La de 30 se detuvo durante la
época 21, con 20 completas. Frente al shuffled con scaler de 2 chunks:

- 10 chunks: loss 0,002078 → 0,003005; accuracy 99,9502 % → 99,9336 %.
- 20 chunks: loss 0,002680 → 0,002944; accuracy 99,9121 % → 99,9167 %.

Por tanto, **no se observó una mejora uniforme al usar el scaler completo**:
la loss fue mayor en las dos etapas comparables; la accuracy mejoró ligeramente
en 20. Una semilla y diferencias pequeñas no establecen superioridad general.
No se compara la etapa parcial de 30 como si estuviese terminada.

## 8. Entrenamiento directo con los 14.503 chunks

Se lanzó un entrenamiento desde cero con LayerNorm, shuffled, scaler completo,
100 épocas objetivo y todos los chunks desde la primera época. TRAIN ONLINE
seguía siendo 50/50. Se añadieron TRAIN EVAL y TEST EVAL tras cada chunk sobre
muestras globales fijas de 58.012 filas: 29.006 positivas y 29.006 negativas.
Se eligió este monitor para seguir la misma población mientras pasaban más datos.

La primera versión conservaba índices y muestras en RAM: se observaron unos
10 GiB durante preparación. Se detuvo y se cambió a lectura por lotes y cachés
en disco. Más adelante se eliminó la acumulación global de logits/predicciones,
manteniendo contadores de la época y AUC exacto en los monitores. Se observaron
aproximadamente 1–1,7 GiB de RAM y unos 563 MiB de VRAM en entrenamiento;
son mediciones puntuales, no un límite garantizado.

Inicialmente se conservó una evaluación de todas las filas balanceadas al final
de época. Tras terminar los 14.503 chunks de la época 1, esa fase seguía ocupando
aproximadamente un día sin mensajes de progreso. Se detuvo, se recuperó desde
el chunk 14.500, se repitieron los últimos 3 y se sustituyó por los monitores
fijos ya calculados. Así se guardaron best/last y pudo arrancar la época 2.

| Momento | TEST loss | Accuracy | Recall | Especificidad | ROC-AUC |
|---|---:|---:|---:|---:|---:|
| Cierre de época 1, checkpoint guardado | 0,649533 | 61,47 % | 56,53 % | 66,42 % | 0,665027 |
| Último monitor antes de detener, época 2/chunk 601 | 0,645867 | 62,06 % | 70,67 % | 53,45 % | 0,670063 |

Se detuvo con 1 época completa y un checkpoint recuperable hasta el chunk 600
de la época 2. El best guardado corresponde a la época 1: no se guardaba best
por cada chunk. No se completaron 100 épocas en esta prueba.

Interpretación: aprendió respecto al inicio, pero el rendimiento global se
estabilizó aproximadamente en AUC 0,67, con recall/especificidad oscilantes.
No se alcanzaron los ~99 % de las pruebas pequeñas; esas evaluaciones no tienen
la misma población ni el mismo número de épocas, por lo que no son comparables
directamente. Se descartó continuar por coste y rendimiento insuficiente para
justificar ese experimento, no por un fallo de ejecución demostrado.

## 9. Rendimiento, concurrencia y cambios operativos

Se inspeccionaron GPU, CPU, disco y RAM. Los tres entrenamientos simultáneos
usaban GPU distintas. No se observó saturación global de CPU; había bastante
trabajo de sistema/gestión de datos y baja actividad instantánea de GPU.

Se detuvieron las otras dos escaleras para comprobar interferencia. En la
muestra corta posterior hubo chunks de 7–9 segundos, pero también un pico de
69 segundos; no se obtuvo una comparación controlada suficiente para atribuir
una aceleración sostenida a eliminar la concurrencia.

Las estimaciones por época variaron según el tramo: alrededor de 40–79 horas,
más la evaluación global final cuando existía. No eran tiempos medidos de
100 épocas completas. El campo de 23 segundos en el cierre recuperado de la
época 1 mide únicamente el segmento repetido, no la época entera.

Se añadieron checkpoints atómicos, estado aleatorio PyTorch/CUDA, recuperación
intraépoca, separación de best/last/recovery y limpieza de historiales duplicados
tras reanudar. Las comprobaciones automáticas validaron balanceo, muestras fijas,
reproducibilidad de la evaluación y selección correcta del best. Son pruebas
del software, no experimentos adicionales de calidad predictiva.

## 10. Experimento actual: escalera de 100 en 100 y evaluación doble

Etapas previstas: 100, 200, 300… 14.500 y 14.503; 100 épocas por etapa.
Se mantienen LayerNorm, shuffled, scaler completo, cosine y el resto de la
configuración. La primera etapa empieza desde cero; la siguiente recibe el
best de TEST STAGE de la anterior, reiniciando optimizador/scheduler.

Se evalúan cuatro conjuntos fijos 50/50 después de cada chunk:

| Evaluación, etapa actual de 100 chunks | Positivas | Negativas | Total |
|---|---:|---:|---:|
| TRAIN EVAL STAGE —100 chunks— | 29.006 | 29.006 | 58.012 |
| TEST EVAL STAGE —100 chunks— | 28.873 | 28.873 | 57.746 |
| TRAIN EVAL ALL —14.503 chunks— | 29.006 | 29.006 | 58.012 |
| TEST EVAL ALL —14.503 chunks— | 29.006 | 29.006 | 58.012 |

Las muestras ALL se reutilizan entre etapas. Las STAGE permanecen fijas dentro
de cada etapa y cambian al ampliar los chunks. Se seleccionan filas sin repetición
con cuotas por chunk; no se recorren todas las filas ni se pondera necesariamente
cada chunk según su tamaño. TEST STAGE selecciona best; ALL solo diagnostica.
TRAIN ALL incluye chunks todavía no entrenados en esa etapa, no es solo error
sobre los ejemplos ya usados para ajustar pesos.

Instantánea al recopilar datos: 22 épocas completas; época 23/chunk 38 en curso.
El mejor cierre de época por TEST STAGE loss es el 20:

| Evaluación, época 20 | Loss | Accuracy | Recall | Especificidad | ROC-AUC |
|---|---:|---:|---:|---:|---:|
| TRAIN STAGE | 0.317686 | 85.44 % | 80.49 % | 90.39 % | 0.936854 |
| TEST STAGE | 0.333323 | 84.83 % | 79.38 % | 90.29 % | 0.930583 |
| TRAIN ALL | 1.079969 | 54.03 % | 22.47 % | 85.60 % | 0.590878 |
| TEST ALL | 1.072312 | 54.28 % | 22.78 % | 85.77 % | 0.593038 |

El TEST local pasó de loss 0,672914, accuracy 58,26 % y AUC 0,634662 en época 1
a loss 0,333323, accuracy 84,83 % y AUC 0,930583 en época 20. Sin embargo,
el TEST ALL pasó de loss 0,686453 y AUC 0,611053 a loss 1,072312 y AUC 0,593038.

Este es un resultado relevante: **mejorar dentro de los 100 chunks no está
implicando mejorar sobre todos los chunks**. En esa época el recall global fue
22,78 %, con especificidad 85,77 %: hay una tendencia a clasificar como negativos
muchos positivos del conjunto global. No se explica solamente por diferencia
TRAIN frente a TEST local; puede reflejar especialización al subconjunto o
cambios de distribución entre chunks. No se ha aislado causalmente el mecanismo.

Tras el reinicio cosine en época 21 empeoró temporalmente TEST STAGE: loss
0,426520 y AUC 0,882531; en época 22 volvió a mejorar a 0,388790 y 0,907267.
No se ha completado la primera etapa ni comenzado la de 200 en esta instantánea.

## 11. Propuestas que todavía no equivalen a experimentos realizados

- Comparar una y dos GPU con el mismo batch global: propuesto, no ejecutado como
  comparación de calidad. Usar GPU distintas para ejecuciones independientes no
  es entrenar un modelo con dos GPU.
- Evaluar o entrenar con prevalencia natural, sin balancear: discutido; finalmente
  se pidió mantener 50/50. No hay resultados de una comparación balanceado/natural.
- Extender una etapa a 200 épocas: propuesto al ver best tardíos; no realizado.
- Reducir el learning rate o actualizar cosine por minibatch/chunk: hipótesis,
  no una prueba independiente con resultados disponibles.
- Mezclar/intercalar minibatches de varios chunks con un búfer pequeño: propuesto
  para investigar adaptación al chunk reciente; no implementado como experimento.
- Seleccionar checkpoints con VALIDATION: recomendado para una evaluación final
  independiente; se mantuvo TEST STAGE por decisión del usuario.

## 12. Conclusiones acumuladas y límites

1. El diagnóstico de BatchNorm mostró un problema fuerte al cambiar las
   estadísticas de inferencia; LayerNorm mejoró claramente el ensayo de 10 chunks.
2. Shuffled mejoró la loss en las etapas completas comparables de 10–50 chunks.
3. El scaler completo cambió apreciablemente la normalización, pero no mejoró
   uniformemente las métricas de las primeras etapas frente al scaler de 2 chunks.
4. Los resultados casi perfectos de subconjuntos pequeños no se trasladaron al
   entrenamiento directo ni a la evaluación sobre todos los chunks.
5. La evaluación doble actual distingue aprendizaje local de rendimiento global:
   de momento hay una mejora local notable y una transferencia global limitada.
6. Se ha reducido considerablemente el uso de RAM y el coste del cierre de época;
   esto mejora viabilidad, pero no corrige por sí solo la calidad predictiva.
7. No hay comparación multisemilla, experimento controlado de LR/mezcla de chunks,
   prueba de calidad con DDP ni evaluación independiente por grupos nuevos.

## 13. Fuentes utilizadas para reconstruir los resultados

- `archive/legacy_experiments_2026-10-26.tar.gz` (eliminado el 10/11/2026): EXPERIMENTS.md, escaleras antiguas,
  historiales por época y archivo del experimento con todos los chunks.
- `archive/auxiliary_tools_and_scaler_analysis.tar.gz` (eliminado el 10/11/2026): comparación de scalers,
  conteos/procedencia y herramientas de comprobación.
- Carpeta histórica `chunk_ladder100_layernorm_cosine_shuffled_allscaler_dualeval_100epochs_1GPU/` (eliminada el 10/11/2026; resultados finales en sección 16):
  historial por época, monitor por chunk, logs y checkpoints activos.

Los historiales contienen más decimales que el log. Los números se presentan
redondeados. Las etapas interrumpidas están identificadas y no se extrapolan
sus resultados a 100 épocas. Que un archivo auxiliar se haya archivado o
eliminado no implica por sí mismo que el experimento fracasara científicamente.


## 14. Actualización del 28 de octubre: mezcla global antes del split

### Estado del entrenamiento anterior

En la revisión del 28 de octubre no había un entrenamiento MLP activo y las
cuatro RTX 3090 estaban sin procesos de cómputo. El log de la escalera de 100
en 100 había avanzado más allá de la instantánea de la sección 10: su última
entrada era época 30/100, chunk 93/200, dentro de la etapa de 200 chunks.
La última modificación de ese log fue el 27 de octubre a las 16:06, hora de
Madrid. No se observó un mensaje final que permita atribuir una causa al paro.
Esta entrada por chunk no certifica un cierre de época ni un checkpoint guardado.

Últimas métricas TEST visibles en ese monitor:

| Población | Loss | Accuracy | Recall | ROC-AUC |
|---|---:|---:|---:|---:|
| STAGE, 200 chunks | 0,168707 | 93,49 % | 90,89 % | 0,9842 |
| ALL, 14.503 chunks | 1,441980 | 53,19 % | 16,23 % | 0,5836 |

Son valores del último monitor, no una selección de best ni resultados finales.
Persiste la diferencia entre rendimiento local y global. La nueva preparación
busca repartir las distintas procedencias entre los chunks; todavía no demuestra
que esa intervención vaya a mejorar las métricas del modelo.

### Qué se está ejecutando

Se está ejecutando `reorder_chunks.py` desde la raíz del proyecto, en `nap_env`:

```bash
python -u reorder_chunks.py --root data_input_nn \
  --output data_input_nn_shuffled --chunk-rows 100000 --buckets 1024 --seed 42
```

La salida del proceso se recoge en `reorder_chunks.log`. En las consultas de
esta sesión su PID es 2314483; es un identificador de esta ejecución, no fijo.

El shuffled de los experimentos anteriores cambiaba el orden de visita de
chunks durante cada época, conservando su composición. Este script mezcla
físicamente las filas y sus embeddings primarios entre los 11 datasets antes
de crear un nuevo split. No realiza entrenamiento ni balanceo 50/50.

### Algoritmo, integridad y archivos

1. Localiza los `master_index.csv` originales en orden de ruta. Comprueba
   columnas, etiquetas binarias, índices consecutivos, correspondencia con los
   embeddings primarios y compatibilidad de dimensiones y tipos entre fuentes.
2. Conserva la procedencia en `source_dataset_id`, `source_chunk_id`,
   `source_row_idx_in_chunk` y `source_group_id`. Desplaza `group_id` por fuente
   para evitar colisiones al consultar SecondaryBERT. Conserva `protein_group_id`;
   este último debe interpretarse junto al dataset de origen.
3. Fase `PARTITION`: asigna cada muestra al azar a uno de 1.024 buckets, con
   semilla 42. En `_shuffle_work/000000.csv` guarda metadatos y en
   `_shuffle_work/000000.bin` los embeddings primarios correspondientes, en el
   mismo orden. El BIN es binario sin cabecera; su lectura requiere tipo y
   dimensiones. El número del archivo identifica un bucket temporal.
4. Tras repartir todas las entradas, permuta las filas de cada bucket y escribe
   chunks definitivos de 100.000 muestras, salvo el último si hay un resto.
   Aparecen mensajes `WRITE chunk=...`. Los embeddings se guardan en
   `mixed/classification_mixed_ProtT5_chunks/chunk_XXXXXX_X.npy` y los metadatos
   en su `master_index.csv`, con nuevos índices de chunk y de fila.
5. Elimina cada pareja CSV/BIN después de consumirla. Comprueba que el total
   emitido coincida con el de entrada, escribe `reorder_manifest.json` y elimina
   `_shuffle_work` e `INCOMPLETE` al finalizar correctamente.

Cada fila se emite una vez, sin muestreo con reemplazo. La asignación aleatoria
no garantiza proporciones exactas por clase, especie o MHC en cada chunk.
La reproducibilidad requiere las mismas entradas, semilla y número de buckets.

Los embeddings secundarios no se copian: el índice combinado en
`mixed/classification_mixed_SecondaryBERT_by_group` referencia por rutas absolutas
los archivos originales. Es necesario mantenerlos disponibles. El script no
sobrescribe la entrada y exige una carpeta de salida nueva, separada de ella.
No implementa reanudación automática de ejecuciones parciales.

### Recursos y seguimiento de esta ejecución

El trabajo usa CPU y disco, no GPU. Se observó alrededor de un 30 % de un núcleo
como promedio acumulado, con valores instantáneos mayores. El tiempo `TIME+`
de `top` es CPU acumulada; `ELAPSED` de `ps` es la duración real e incluye las
esperas de disco. La RAM no contiene todos los embeddings: se procesa un chunk
original y, en la segunda fase, los metadatos/permutación de un bucket y los
bloques necesarios para formar el chunk de salida.

Los buckets llegaron a ocupar aproximadamente 2,8 TB durante las primeras
consultas; ese tamaño cambia durante la ejecución. Debe contemplarse espacio
para los temporales y la salida definitiva, además de los originales. El código
elimina los temporales progresivamente durante la segunda fase.

| Consulta del 28 de octubre, hora de Madrid | Filas repartidas | Observación |
|---|---:|---|
| 13:01 | 745.020.080 | Inicio de source=3 |
| 13:49 | 778.520.080 | Sigue PARTITION |
| 13:54 | 782.120.080 | Ritmo similar con otras tareas activas |
| 15:40 | 856.520.080 | Aproximadamente 59 % de PARTITION |
| 16:13 | 879.130.530 | source=4, chunk=36; proceso activo |

La última consulta corresponde a unas 22 h 41 min de ejecución. El total de
entrada se estima en unos 1.450 millones de filas; el valor definitivo lo dará
el manifiesto al finalizar. Con ese total, el último progreso es aproximadamente
el 61 % del reparto, no el 61 % del tiempo total del trabajo.

El ritmo observado fue aproximadamente 690.000–703.000 filas por minuto. Las
nuevas tareas de STAR/Scipion no mostraron una ralentización apreciable entre
las consultas comparadas; esto no garantiza ausencia de interferencia futura.
En esa revisión había 146 GiB de RAM disponibles, sin presión de memoria, y
esperas de disco cuya causa no se aisló. A las 15:40 quedaban 28 TB libres.

A las 16:13, extrapolar ese ritmo da unas 13,5–14 horas para acabar PARTITION.
La duración de la segunda fase aún no se ha medido. La estimación conversada de
15–35 horas adicionales para ella es orientativa, no un tiempo validado. No debe
interpretarse una fecha estimada como garantía ni sumar los porcentajes de ambas
fases como si costasen lo mismo.

Para consultar el estado sin modificar los datos:

```bash
tail -n 10 reorder_chunks.log
ps -p 2314483 -o pid,etime,time,%cpu,%mem,stat,args
```

### Pasos pendientes después de completar el shuffle

Mientras exista `data_input_nn_shuffled/INCOMPLETE`, la salida no está lista
para dividir ni entrenar. La secuencia prevista, aún pendiente en esta
actualización, es:

```bash
python split_data.py --root data_input_nn_shuffled --seed 42
python check_master_split.py --root data_input_nn_shuffled --skip-metadata
python prepare_chunk_metadata.py --root data_input_nn_shuffled
python check_master_split.py --root data_input_nn_shuffled
```

Se mantiene la política acordada de split aleatorio por filas, estratificado por
etiqueta dentro de cada chunk, aproximadamente 80/10/10. Se permite compartir
grupos y proteínas entre splits. La mezcla no convierte la evaluación en una
prueba de generalización a grupos o proteínas nuevos.

El futuro entrenamiento deberá usar la nueva raíz, pesos iniciales nuevos y un
scaler ajustado exclusivamente con las nuevas filas TRAIN. No se debe reutilizar
el scaler histórico como si correspondiera al nuevo split. A fecha de esta
actualización no se han generado resultados predictivos del dataset mezclado.

Fuentes de esta actualización: `reorder_chunks.py`, `reorder_chunks.log`, el
`run.log` de `chunks_200`, el flujo documentado en el README raíz y consultas
puntuales de procesos, memoria, disco y GPU. Existe `test_reorder_chunks.py`
como prueba sintética de integración; esta actualización documental no afirma
una validación completa de los datos reales ni una nueva ejecución de tests.


## 15. Retirada del archivo histórico el 10 de noviembre de 2026

Por decisión del usuario se elimina la carpeta `archive/` completa. Los resultados,
configuraciones y límites de las pruebas permanecen documentados en las secciones
1–14. Las expresiones «actual», «activo» y «en curso» de esas secciones describen
sus respectivas instantáneas históricas; no certifican procesos activos hoy.

Se retiran dos archivos comprimidos y `cleanup_manifest.json`. No se elimina
ninguna carpeta de resultados fuera de `archive/`, ningún embedding ni el scaler
histórico conservado como `standardizer_legacy_all_train_chunks.npz`.
Los checkpoints, logs completos y scripts contenidos únicamente en los comprimidos
ya no están disponibles para restaurar o reproducir exactamente esas ejecuciones.
Este resumen conserva sus conclusiones y métricas, no sustituye sus pesos ni datos
por época. No se presentan resultados nuevos por esta limpieza.

Inventario de los comprimidos retirados, leído antes de eliminarlos:

| Archivo | Archivos internos | Bytes comprimidos | Contenido |
|---|---:|---:|---|
| `legacy_experiments_2026-10-26.tar.gz` | 146 | 674,853,830 | Escaleras LayerNorm sin/con barajado, scaler completo, ensayo de todos los chunks, checkpoints best/last/recovery, métricas, logs, gráficas, documentación y scripts históricos (incluido dataset.py). |
| `auxiliary_tools_and_scaler_analysis.tar.gz` | 12 | 221,126 | Tests antiguos de muestreo y evaluación dual, compare_scaler_all_chunks.py, documentación y análisis del scaler de 2 chunks frente al completo. |

Detalle de familias del archivo principal (número de archivos):

- `EXPERIMENTS.md`: 1.
- `README_allchunks_lowmemory.md`: 1.
- `allchunks_layernorm_cosine_shuffled_allscaler_100epochs_1GPU`: 14.
- `analysis_chunk_ladder_seed42`: 4.
- `analyze_chunk_ladder.py`: 1.
- `chunk_ladder_layernorm_cosine_100epochs_1GPU`: 59.
- `chunk_ladder_layernorm_cosine_shuffled_100epochs_1GPU`: 37.
- `chunk_ladder_layernorm_cosine_shuffled_allscaler_100epochs_1GPU`: 18.
- `chunk_ladder_layernorm_cosine_shuffled_allscaler_launcher.log`: 1.
- `chunk_ladder_layernorm_cosine_shuffled_launcher.log`: 1.
- `mlp_baseline_layernorm.py`: 1.
- `mlp_baseline_layernorm_shuffled.py`: 1.
- `mlp_baseline_layernorm_shuffled_allscaler.py`: 1.
- `mlp_layernorm_shuffled_allchunks_monitor.py`: 1.
- `run_allchunks_shuffled_allscaler_monitor.sh`: 1.
- `run_chunk_ladder_layernorm.sh`: 1.
- `run_chunk_ladder_layernorm_shuffled.sh`: 1.
- `run_chunk_ladder_layernorm_shuffled_allscaler.sh`: 1.
- `dataset.py`: 1.

Contenido del archivo auxiliar:

- `tests/test_ladder100_dualeval.py`.
- `tests/test_ladder100_sampling.py`.
- `compare_scaler_all_chunks.py`.
- `README_ladder100_dualeval.md`.
- `archive/README.md`.
- `analysis_scaler_2_vs_all/progress.npz`.
- `analysis_scaler_2_vs_all/status.json`.
- `analysis_scaler_2_vs_all/standardizer_reference_2chunks.npz`.
- `analysis_scaler_2_vs_all/comparison.json`.
- `analysis_scaler_2_vs_all/chunks.json`.
- `analysis_scaler_2_vs_all/analysis.lock`.
- `analysis_scaler_2_vs_all/run.log`.

Registro del manifiesto de limpieza original:

- Inventariaba 145 entradas archivadas. La lista real del comprimido principal contiene 146 archivos; para esta retirada se utiliza su contenido real.
- Registraba como eliminados previamente: `compare_scalers_2_vs_10.py`, `test_allchunks_lowmemory.py`, `test_epoch_finish_resume.py`, `__pycache__`.
- Su campo `kept_active` identificaba históricamente `chunk_ladder100_layernorm_cosine_shuffled_allscaler_dualeval_100epochs_1GPU`; esa carpeta externa a archive no se toca.

SHA-256 de los comprimidos antes de su retirada (identifican los archivos eliminados; no constituyen una copia de seguridad):

- `legacy_experiments_2026-10-26.tar.gz`: `6e6b1dbe259eaf0d1d0f775651583529bbf66134e69b339fab49d1fe2d8ee7df`.
- `auxiliary_tools_and_scaler_analysis.tar.gz`: `2f4bd348806c9d43a03aadefcd030fa2d621619890249d9361bbeb9877e4bd20`.

El checksum del archivo principal coincidió con el registrado en el manifiesto original.


## 16. Cierre documental y eliminación del último experimento anterior (10/11/2026)

Se revisó y eliminó por decisión del usuario `chunk_ladder100_layernorm_cosine_shuffled_allscaler_dualeval_100epochs_1GPU/`, aproximadamente 2,4 GiB.
No había un entrenamiento activo usando esta carpeta. Se retiraron checkpoints,
logs, historiales JSONL, muestras y cachés de evaluación STAGE/ALL. Los resultados
se conservan aquí; los pesos y las evaluaciones exactas por muestra ya no podrán
restaurarse desde esta carpeta. No se tocan los embeddings ni el nuevo scaler
en cálculo dentro de `chunk_ladder100_mixed_shuffled_20261110/`.

Esta sección actualiza las instantáneas parciales de las secciones 10 y 14.
El experimento utilizó los 11 datasets originales (14.503 chunks), antes de la
mezcla física global: Primary+Secondary, LayerNorm, batches TRAIN 50/50 de 8.192,
una GPU, orden de chunks barajado por época y selección de best por TEST STAGE
loss. STAGE y ALL son muestras fijas balanceadas; ALL no representa una evaluación
de todas las filas. La etapa de 200 hereda el best de la de 100, reiniciando
optimizador y scheduler según la política de escalera documentada anteriormente.
No son dos entrenamientos independientes. TEST participa en selección de modelos.

### chunks_100: estado, mejor cierre y último cierre

- Épocas completas: **100**. Registros de monitor por chunk: 10,000.
- Mejor cierre por TEST STAGE loss: época **100**, loss **0.038097077**.
- Último cierre: época 100. Último monitor: época 100, chunk 100.
- Marca `completed_100_epochs.ok`: presente.

| Cierre | Población | N | Loss | Accuracy % | Precision % | Recall % | Especificidad % | F1 | F2 | MCC | ROC-AUC | TP | TN | FP | FN |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Best, época 100 | train_eval_stage | 58012 | 0.030855553 | 99.043301 | 98.960592 | 99.127767 | 98.958836 | 0.990441088 | 0.990942866 | 0.980867427 | 0.999392773 | 28753 | 28704 | 302 | 253 |
| Best, época 100 | test_eval_stage | 57746 | 0.038097077 | 98.715063 | 98.823284 | 98.604232 | 98.825893 | 0.987136368 | 0.986479650 | 0.974303644 | 0.999086448 | 28470 | 28534 | 339 | 403 |
| Best, época 100 | train_eval_all | 58012 | 2.616237518 | 52.554644 | 64.012859 | 11.669999 | 93.439288 | 0.197410626 | 0.139516289 | 0.088756119 | 0.585381160 | 3385 | 27103 | 1903 | 25621 |
| Best, época 100 | test_eval_all | 58012 | 2.621692819 | 52.520168 | 64.079353 | 11.470041 | 93.570296 | 0.194572782 | 0.137234359 | 0.088283762 | 0.585284694 | 3327 | 27141 | 1865 | 25679 |
| Último, época 100 | train_eval_stage | 58012 | 0.030855553 | 99.043301 | 98.960592 | 99.127767 | 98.958836 | 0.990441088 | 0.990942866 | 0.980867427 | 0.999392773 | 28753 | 28704 | 302 | 253 |
| Último, época 100 | test_eval_stage | 57746 | 0.038097077 | 98.715063 | 98.823284 | 98.604232 | 98.825893 | 0.987136368 | 0.986479650 | 0.974303644 | 0.999086448 | 28470 | 28534 | 339 | 403 |
| Último, época 100 | train_eval_all | 58012 | 2.616237518 | 52.554644 | 64.012859 | 11.669999 | 93.439288 | 0.197410626 | 0.139516289 | 0.088756119 | 0.585381160 | 3385 | 27103 | 1903 | 25621 |
| Último, época 100 | test_eval_all | 58012 | 2.621692819 | 52.520168 | 64.079353 | 11.470041 | 93.570296 | 0.194572782 | 0.137234359 | 0.088283762 | 0.585284694 | 3327 | 27141 | 1865 | 25679 |

Resultados TEST de todos los cierres de época (STAGE y ALL, mismos pesos por fila):

| Época | STAGE loss | STAGE acc % | STAGE recall % | STAGE ROC-AUC | ALL loss | ALL acc % | ALL recall % | ALL ROC-AUC |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0.672913923 | 58.263776 | 43.601288 | 0.634661627 | 0.686453207 | 56.314211 | 41.456940 | 0.611052573 |
| 2 | 0.680338583 | 57.579746 | 54.822845 | 0.615357352 | 0.703793639 | 55.014480 | 49.058815 | 0.581337887 |
| 3 | 0.640300871 | 62.925571 | 70.155509 | 0.686571442 | 0.665515994 | 59.665242 | 65.307178 | 0.630719156 |
| 4 | 0.629219229 | 64.028677 | 57.766772 | 0.703366847 | 0.683494786 | 58.744742 | 49.651796 | 0.630869604 |
| 5 | 0.662407749 | 60.478648 | 39.410522 | 0.687994372 | 0.727681447 | 56.269393 | 32.300214 | 0.624770218 |
| 6 | 0.599945484 | 66.311086 | 76.476293 | 0.741893144 | 0.682483854 | 58.660277 | 63.428256 | 0.618695208 |
| 7 | 0.591881807 | 67.047068 | 49.977488 | 0.759115002 | 0.754274506 | 56.269393 | 29.835207 | 0.618741143 |
| 8 | 0.557019779 | 70.202265 | 62.141101 | 0.784363483 | 0.754938784 | 57.436392 | 38.660967 | 0.618751369 |
| 9 | 0.565367277 | 69.869775 | 57.510477 | 0.784392175 | 0.787765344 | 56.078053 | 32.565676 | 0.617399674 |
| 10 | 0.502759360 | 73.882174 | 68.222907 | 0.830353524 | 0.748298552 | 56.215955 | 35.323726 | 0.605302716 |
| 11 | 0.490420720 | 74.373983 | 64.278045 | 0.838227947 | 0.859563541 | 54.383576 | 26.418672 | 0.595233362 |
| 12 | 0.450187057 | 77.293665 | 78.758702 | 0.867715967 | 0.790200591 | 56.988209 | 41.805144 | 0.607791132 |
| 13 | 0.447292643 | 77.944793 | 79.880858 | 0.872212629 | 0.814728938 | 56.652072 | 42.215404 | 0.606637104 |
| 14 | 0.404690629 | 80.426350 | 77.175908 | 0.893291355 | 0.960955110 | 55.814314 | 32.331242 | 0.601549133 |
| 15 | 0.387263670 | 81.380529 | 73.258754 | 0.905269508 | 0.989898541 | 54.073295 | 22.557402 | 0.593665949 |
| 16 | 0.367445242 | 82.535587 | 75.087452 | 0.914876682 | 1.017661042 | 53.850927 | 21.923050 | 0.594334787 |
| 17 | 0.363423144 | 82.854224 | 72.437918 | 0.922223140 | 1.100788600 | 53.423430 | 17.423981 | 0.595570473 |
| 18 | 0.350848901 | 83.617913 | 75.018183 | 0.925496106 | 1.095944058 | 53.645797 | 18.844377 | 0.591461590 |
| 19 | 0.335749448 | 84.741800 | 79.191632 | 0.929549427 | 1.058550971 | 54.293939 | 22.981452 | 0.593601520 |
| 20 | 0.333323029 | 84.833582 | 79.382122 | 0.930582740 | 1.072312360 | 54.276701 | 22.784941 | 0.593038084 |
| 21 | 0.426519558 | 78.756970 | 70.927856 | 0.882531063 | 0.927052675 | 54.316348 | 24.867269 | 0.591507078 |
| 22 | 0.388790154 | 81.875801 | 82.104388 | 0.907266772 | 0.853908066 | 55.991864 | 36.244225 | 0.598497486 |
| 23 | 0.387528279 | 81.889655 | 74.180030 | 0.905098130 | 1.000292474 | 54.502517 | 23.784734 | 0.592663992 |
| 24 | 0.364037979 | 83.349496 | 82.409171 | 0.917153373 | 0.924542412 | 55.364407 | 32.638075 | 0.599975413 |
| 25 | 0.346507927 | 83.929623 | 82.139023 | 0.923873070 | 1.035366590 | 53.681997 | 26.377301 | 0.585139661 |
| 26 | 0.314148536 | 86.170471 | 81.598725 | 0.943633977 | 1.003786287 | 53.266566 | 21.274909 | 0.584872049 |
| 27 | 0.316646104 | 86.075226 | 89.038202 | 0.942608344 | 1.116378031 | 56.091843 | 35.727091 | 0.602241399 |
| 28 | 0.337926780 | 85.375610 | 76.001801 | 0.943817003 | 1.515161077 | 53.076950 | 15.696752 | 0.583349042 |
| 29 | 0.252988992 | 89.036470 | 83.150348 | 0.963503614 | 1.292644953 | 53.351031 | 16.727574 | 0.591296705 |
| 30 | 0.287166976 | 87.384408 | 76.510927 | 0.968336651 | 1.659478025 | 52.146108 | 9.153279 | 0.588012772 |
| 31 | 0.220174577 | 90.839192 | 86.554913 | 0.972297680 | 1.357216692 | 53.240709 | 16.579328 | 0.589176852 |
| 32 | 0.212998288 | 90.887681 | 84.248260 | 0.978794512 | 1.584084854 | 52.527063 | 11.263187 | 0.585916526 |
| 33 | 0.200171701 | 91.640979 | 85.934957 | 0.980176996 | 1.661575253 | 52.770117 | 12.294008 | 0.589514599 |
| 34 | 0.212295277 | 90.811485 | 83.507083 | 0.981954280 | 1.816879804 | 52.383990 | 10.056540 | 0.595358286 |
| 35 | 0.171982286 | 92.858380 | 87.735947 | 0.985952156 | 1.721811643 | 52.459836 | 11.052886 | 0.584839461 |
| 36 | 0.148990848 | 94.250684 | 92.612475 | 0.986846758 | 1.556608679 | 53.351031 | 17.358478 | 0.588327996 |
| 37 | 0.148421984 | 94.068853 | 91.126658 | 0.987674488 | 1.694514174 | 53.125215 | 14.462525 | 0.589306144 |
| 38 | 0.137925806 | 94.678419 | 93.329408 | 0.988737738 | 1.593244889 | 53.395849 | 17.192995 | 0.588411035 |
| 39 | 0.144979509 | 94.224708 | 90.666020 | 0.989096996 | 1.779917725 | 52.739088 | 12.352617 | 0.589155332 |
| 40 | 0.138342595 | 94.602224 | 91.864372 | 0.989420549 | 1.722838800 | 52.973523 | 13.673033 | 0.586735743 |
| 41 | 0.216945727 | 91.299830 | 90.974267 | 0.972612653 | 1.230429777 | 54.209474 | 23.767496 | 0.593127453 |
| 42 | 0.203852719 | 91.481661 | 90.510165 | 0.975519550 | 1.351905910 | 53.859546 | 21.571399 | 0.589215561 |
| 43 | 0.228096083 | 90.591556 | 91.123195 | 0.969517589 | 1.226693898 | 53.068331 | 24.257050 | 0.567912948 |
| 44 | 0.300104108 | 87.323797 | 75.509992 | 0.981512334 | 2.206067321 | 51.485899 | 5.716059 | 0.582219536 |
| 45 | 0.220001614 | 90.518824 | 83.642157 | 0.978697327 | 1.639349875 | 52.687375 | 12.052679 | 0.589556215 |
| 46 | 0.177304296 | 93.047137 | 93.121601 | 0.981913473 | 1.388300092 | 53.957802 | 22.660829 | 0.588219924 |
| 47 | 0.168278836 | 93.258408 | 94.018633 | 0.983782144 | 1.464138342 | 53.976763 | 23.040061 | 0.588325432 |
| 48 | 0.150639606 | 94.046341 | 93.343262 | 0.986517957 | 1.559028460 | 53.230366 | 18.489278 | 0.584252170 |
| 49 | 0.138321732 | 94.453295 | 91.646175 | 0.989651309 | 1.762673161 | 52.578777 | 13.028339 | 0.583144386 |
| 50 | 0.154504198 | 93.623801 | 88.820005 | 0.991054576 | 2.264851967 | 52.297800 | 9.928980 | 0.588668909 |
| 51 | 0.143864848 | 94.191805 | 90.645239 | 0.990018333 | 1.874523202 | 52.237468 | 11.197683 | 0.583104088 |
| 52 | 0.144696163 | 94.061926 | 89.575036 | 0.991407727 | 1.942647680 | 52.315038 | 10.353030 | 0.590901248 |
| 53 | 0.096576591 | 96.524435 | 96.384165 | 0.994457488 | 1.822597396 | 53.502724 | 17.637730 | 0.592971826 |
| 54 | 0.130057182 | 94.597028 | 90.132650 | 0.994882474 | 2.261221881 | 51.965111 | 7.736330 | 0.590258719 |
| 55 | 0.088843986 | 96.875974 | 97.419735 | 0.995713236 | 1.757770079 | 53.599255 | 19.209819 | 0.584441835 |
| 56 | 0.084958436 | 96.917535 | 95.535622 | 0.996237854 | 2.003322275 | 52.792526 | 12.169896 | 0.588746058 |
| 57 | 0.079126314 | 97.163440 | 96.159041 | 0.996617314 | 2.006324053 | 52.701165 | 12.535338 | 0.584517647 |
| 58 | 0.075296192 | 97.341807 | 97.159976 | 0.996633885 | 1.971268859 | 53.321727 | 15.893263 | 0.589899278 |
| 59 | 0.073679176 | 97.411076 | 96.778998 | 0.996816750 | 2.048070029 | 52.908019 | 13.697166 | 0.586898913 |
| 60 | 0.073467276 | 97.364320 | 96.529630 | 0.996935018 | 2.094950896 | 52.770117 | 12.611184 | 0.585457914 |
| 61 | 0.144405733 | 94.430783 | 95.656842 | 0.988632673 | 1.507357827 | 53.430325 | 22.309177 | 0.578771794 |
| 62 | 0.133850565 | 94.861982 | 95.376303 | 0.990039900 | 1.530404632 | 53.728539 | 21.143901 | 0.589349265 |
| 63 | 0.182945354 | 92.279985 | 85.543587 | 0.991181710 | 2.222050290 | 52.028891 | 7.829415 | 0.596629984 |
| 64 | 0.115254503 | 95.672428 | 96.256018 | 0.992266830 | 1.676000245 | 53.778529 | 20.806040 | 0.585959965 |
| 65 | 0.124764440 | 95.384962 | 96.792851 | 0.992160703 | 1.512139561 | 53.640626 | 22.674619 | 0.581662456 |
| 66 | 0.115620566 | 95.483670 | 94.548540 | 0.991990696 | 1.877305964 | 53.504447 | 17.196442 | 0.594264592 |
| 67 | 0.102206564 | 96.190212 | 95.926991 | 0.993660044 | 1.838837623 | 53.968145 | 18.858167 | 0.594827686 |
| 68 | 0.099680420 | 96.134797 | 95.057666 | 0.994064346 | 1.948351188 | 52.885610 | 15.114114 | 0.583171502 |
| 69 | 0.104069962 | 95.823087 | 92.667890 | 0.996119555 | 2.326305899 | 52.159898 | 9.046404 | 0.590313570 |
| 70 | 0.092385578 | 96.332213 | 93.956291 | 0.996252628 | 2.279867873 | 52.349514 | 10.366821 | 0.588818345 |
| 71 | 0.096114032 | 96.586777 | 97.721054 | 0.995294756 | 1.684508017 | 53.404468 | 19.747638 | 0.580837201 |
| 72 | 0.093262840 | 96.335677 | 93.641118 | 0.996827864 | 2.489569814 | 52.104737 | 8.567193 | 0.585920206 |
| 73 | 0.069231438 | 97.485540 | 96.380702 | 0.997405177 | 2.317719653 | 52.689099 | 11.763083 | 0.592616002 |
| 74 | 0.060933386 | 97.987739 | 98.192083 | 0.997934720 | 1.982381392 | 53.123492 | 15.758809 | 0.587405018 |
| 75 | 0.056965499 | 98.015447 | 97.544419 | 0.998123561 | 2.233122485 | 52.597738 | 12.242295 | 0.583831365 |
| 76 | 0.062361676 | 97.708932 | 96.810169 | 0.997928856 | 2.347330428 | 52.527063 | 11.125284 | 0.588467510 |
| 77 | 0.051921599 | 98.183424 | 97.783396 | 0.998388900 | 2.328217737 | 52.673585 | 12.304351 | 0.588074717 |
| 78 | 0.052613744 | 98.057008 | 97.371246 | 0.998446288 | 2.492480884 | 52.465007 | 10.997725 | 0.588224718 |
| 79 | 0.049910840 | 98.256156 | 97.918471 | 0.998513902 | 2.386469117 | 52.558091 | 11.845825 | 0.586613629 |
| 80 | 0.050832281 | 98.185156 | 97.669103 | 0.998507727 | 2.442885802 | 52.461560 | 11.070123 | 0.586328085 |
| 81 | 0.186477426 | 92.434108 | 85.727150 | 0.992158558 | 2.567711404 | 51.728953 | 7.039923 | 0.592582816 |
| 82 | 0.121369924 | 94.979739 | 91.022755 | 0.995232605 | 2.328693200 | 52.132317 | 9.070537 | 0.588543065 |
| 83 | 0.097635613 | 96.226578 | 95.310498 | 0.994114662 | 2.118934739 | 53.182100 | 15.879473 | 0.593278705 |
| 84 | 0.117596960 | 95.216985 | 91.209781 | 0.996371472 | 2.517094511 | 51.889264 | 7.650141 | 0.589433278 |
| 85 | 0.093960962 | 96.295847 | 93.706923 | 0.996718420 | 2.367898383 | 52.115080 | 8.877474 | 0.583598017 |
| 86 | 0.077355474 | 97.142659 | 95.885429 | 0.996768470 | 2.242477336 | 52.675309 | 11.869958 | 0.581982683 |
| 87 | 0.066098235 | 97.580785 | 97.135732 | 0.997312753 | 2.239718798 | 53.089016 | 14.510791 | 0.587151377 |
| 88 | 0.089863419 | 96.430922 | 93.557995 | 0.997895493 | 2.918191301 | 51.709991 | 7.050265 | 0.585414864 |
| 89 | 0.063974669 | 97.757420 | 97.069927 | 0.997680189 | 2.232744074 | 52.337447 | 11.769979 | 0.576899791 |
| 90 | 0.061344274 | 97.771274 | 97.159976 | 0.997694512 | 2.249782934 | 52.639109 | 13.266221 | 0.584372575 |
| 91 | 0.060812570 | 97.942715 | 98.638867 | 0.997959094 | 2.028339362 | 53.373440 | 17.765290 | 0.591568036 |
| 92 | 0.064387275 | 97.695078 | 96.834413 | 0.997825652 | 2.132489276 | 52.335724 | 11.728608 | 0.578196020 |
| 93 | 0.050606042 | 98.133204 | 97.457833 | 0.998581938 | 2.575931093 | 52.370199 | 10.621940 | 0.586115075 |
| 94 | 0.051638966 | 98.096838 | 97.256953 | 0.998582444 | 2.689714701 | 52.382266 | 10.301317 | 0.591557336 |
| 95 | 0.043434498 | 98.451841 | 98.022374 | 0.998896252 | 2.513873759 | 52.427084 | 11.214921 | 0.583561829 |
| 96 | 0.043534695 | 98.479548 | 98.153985 | 0.998853415 | 2.569301870 | 52.478797 | 11.449355 | 0.584768642 |
| 97 | 0.049285368 | 98.173034 | 97.194611 | 0.998919892 | 2.796055333 | 52.123699 | 8.832655 | 0.588156121 |
| 98 | 0.044009252 | 98.387767 | 97.679493 | 0.999017121 | 2.784714106 | 52.090947 | 9.032614 | 0.582642845 |
| 99 | 0.038984515 | 98.676965 | 98.437987 | 0.999074989 | 2.663376354 | 52.409846 | 10.828794 | 0.585021048 |
| 100 | 0.038097077 | 98.715063 | 98.604232 | 0.999086448 | 2.621692819 | 52.520168 | 11.470041 | 0.585284694 |

### chunks_200: estado, mejor cierre y último cierre

- Épocas completas: **29**. Registros de monitor por chunk: 5,893.
- Mejor cierre por TEST STAGE loss: época **20**, loss **0.147276608**.
- Último cierre: época 29. Último monitor: época 30, chunk 93.
- Marca `completed_100_epochs.ok`: ausente.

La época 30 quedó parcial: su monitor no es un cierre de época ni garantiza pesos guardados en ese punto. No se atribuye una causa al paro sin evidencia.

| Cierre | Población | N | Loss | Accuracy % | Precision % | Recall % | Especificidad % | F1 | F2 | MCC | ROC-AUC | TP | TN | FP | FN |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Best, época 20 | train_eval_stage | 58012 | 0.142628564 | 94.785562 | 96.730098 | 92.704958 | 96.866166 | 0.946747645 | 0.934829617 | 0.896487732 | 0.988264313 | 26890 | 28097 | 909 | 2116 |
| Best, época 20 | test_eval_stage | 58012 | 0.147276608 | 94.463215 | 96.509196 | 92.263670 | 96.662759 | 0.943386915 | 0.930826273 | 0.890125993 | 0.987537667 | 26762 | 28038 | 968 | 2244 |
| Best, época 20 | train_eval_all | 58012 | 1.455925936 | 53.813004 | 64.529690 | 16.934427 | 90.691581 | 0.268283358 | 0.198647643 | 0.112932896 | 0.598550975 | 4912 | 26306 | 2700 | 24094 |
| Best, época 20 | test_eval_all | 58012 | 1.455702449 | 53.906088 | 64.990738 | 16.934427 | 90.877749 | 0.268679576 | 0.198734444 | 0.116040251 | 0.599102408 | 4912 | 26360 | 2646 | 24094 |
| Último, época 29 | train_eval_stage | 58012 | 0.164566585 | 93.444460 | 97.554625 | 89.122940 | 97.765979 | 0.931483650 | 0.906906254 | 0.872152886 | 0.986987648 | 25851 | 28358 | 648 | 3155 |
| Último, época 29 | test_eval_stage | 58012 | 0.170793106 | 93.099704 | 97.456630 | 88.509274 | 97.690133 | 0.927677103 | 0.901648556 | 0.865649993 | 0.986152320 | 25673 | 28336 | 670 | 3333 |
| Último, época 29 | train_eval_all | 58012 | 1.675140158 | 53.228642 | 66.022241 | 13.304144 | 93.153141 | 0.221457060 | 0.158325743 | 0.107262419 | 0.595169523 | 3859 | 27020 | 1986 | 25147 |
| Último, época 29 | test_eval_all | 58012 | 1.674999638 | 52.983865 | 65.007803 | 12.924912 | 93.042819 | 0.215627067 | 0.153911209 | 0.099724008 | 0.596146259 | 3749 | 26988 | 2018 | 25257 |

Resultados TEST de todos los cierres de época (STAGE y ALL, mismos pesos por fila):

| Época | STAGE loss | STAGE acc % | STAGE recall % | STAGE ROC-AUC | ALL loss | ALL acc % | ALL recall % | ALL ROC-AUC |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0.525415954 | 72.979728 | 63.862649 | 0.814822507 | 0.733674313 | 54.414604 | 31.427980 | 0.596638377 |
| 2 | 0.505695203 | 75.653313 | 67.379163 | 0.839271945 | 0.722445770 | 55.733297 | 31.772737 | 0.620998063 |
| 3 | 0.399144543 | 81.746880 | 69.830380 | 0.913460609 | 1.106050471 | 53.216576 | 16.813763 | 0.594759584 |
| 4 | 0.358148642 | 83.705095 | 72.802179 | 0.930906766 | 0.986710250 | 53.588913 | 17.020616 | 0.613533259 |
| 5 | 0.340934361 | 85.172033 | 81.607254 | 0.930538598 | 0.880825191 | 55.669517 | 28.245880 | 0.608529575 |
| 6 | 0.351012887 | 83.917121 | 75.387851 | 0.930283990 | 1.129231471 | 53.756119 | 19.647659 | 0.596185587 |
| 7 | 0.308175934 | 86.587258 | 82.582914 | 0.943334432 | 0.978191078 | 54.547335 | 24.250155 | 0.599796839 |
| 8 | 0.278077408 | 88.617872 | 84.765221 | 0.957724531 | 0.954806708 | 53.856099 | 21.171482 | 0.594633643 |
| 9 | 0.270254719 | 88.397228 | 82.076122 | 0.959887554 | 1.274582884 | 53.656140 | 17.551541 | 0.599998442 |
| 10 | 0.245277733 | 89.707302 | 82.755292 | 0.970725910 | 1.447474343 | 53.423430 | 14.131559 | 0.602409477 |
| 11 | 0.226747611 | 90.634696 | 88.864373 | 0.969598623 | 1.186459528 | 54.707647 | 23.122802 | 0.604878536 |
| 12 | 0.207533135 | 91.836172 | 88.457561 | 0.975925455 | 1.274165522 | 53.704406 | 17.617045 | 0.597267999 |
| 13 | 0.205092460 | 91.648280 | 86.113218 | 0.979466805 | 1.406381005 | 53.313108 | 13.724747 | 0.600931957 |
| 14 | 0.198196473 | 91.994760 | 86.950976 | 0.980716844 | 1.314161250 | 53.438944 | 14.590085 | 0.599769529 |
| 15 | 0.182457602 | 92.941116 | 88.854030 | 0.983114181 | 1.411268402 | 53.361374 | 14.355651 | 0.600468727 |
| 16 | 0.163014782 | 93.809901 | 91.194925 | 0.985147689 | 1.362016606 | 53.964697 | 17.320554 | 0.602227661 |
| 17 | 0.156796281 | 94.032269 | 91.181135 | 0.986294477 | 1.435490423 | 53.814728 | 16.337999 | 0.600830752 |
| 18 | 0.156239475 | 93.947804 | 90.767427 | 0.986742019 | 1.536338132 | 53.599255 | 14.934841 | 0.599102877 |
| 19 | 0.149421479 | 94.342550 | 92.067159 | 0.987229173 | 1.450428149 | 53.980211 | 16.975798 | 0.601269066 |
| 20 | 0.147276608 | 94.463215 | 92.263670 | 0.987537667 | 1.455702449 | 53.906088 | 16.934427 | 0.599102408 |
| 21 | 0.264762125 | 88.607529 | 82.051989 | 0.964179121 | 1.426404854 | 53.149348 | 15.145142 | 0.586814227 |
| 22 | 0.264034870 | 88.786803 | 79.793836 | 0.974256082 | 1.687105001 | 52.818382 | 10.659863 | 0.587702136 |
| 23 | 0.242240431 | 89.938289 | 87.106116 | 0.965363695 | 1.284110404 | 54.430118 | 21.309384 | 0.599215539 |
| 24 | 0.210088420 | 91.593119 | 90.812246 | 0.973184183 | 1.289729928 | 54.776598 | 24.260498 | 0.602166031 |
| 25 | 0.228918636 | 90.898435 | 87.044060 | 0.971319304 | 1.267220994 | 53.566503 | 17.441219 | 0.595530329 |
| 26 | 0.199574921 | 92.486037 | 91.425912 | 0.978283088 | 1.191005441 | 53.773357 | 20.581949 | 0.588064184 |
| 27 | 0.183888253 | 93.215197 | 91.677584 | 0.982675793 | 1.169227049 | 54.068124 | 20.102737 | 0.599944164 |
| 28 | 0.223850232 | 90.548507 | 83.351720 | 0.980573324 | 1.759556549 | 52.818382 | 11.394194 | 0.589927254 |
| 29 | 0.170793106 | 93.099704 | 88.509274 | 0.986152320 | 1.674999638 | 52.983865 | 12.924912 | 0.596146259 |

Último monitor parcial (época 30, chunk 93), distinto del best y del último cierre:

| Población | Loss | Accuracy % | Recall % | Especificidad % | ROC-AUC |
|---|---:|---:|---:|---:|---:|
| train_eval_stage | 0.163170344 | 93.835758 | 91.401779 | 96.269737 | 0.985309162 |
| test_eval_stage | 0.168706988 | 93.491002 | 90.888092 | 96.093912 | 0.984156097 |
| train_eval_all | 1.445316440 | 53.130387 | 15.996690 | 90.264083 | 0.580772261 |
| test_eval_all | 1.441979811 | 53.190719 | 16.227677 | 90.153761 | 0.583646478 |

### Interpretación final y trazabilidad

La etapa de 100 completó el objetivo y alcanzó una TEST STAGE accuracy de
98,7151 % y AUC 0,999086 en su mejor cierre (época 100). A la vez, TEST ALL
quedó en accuracy 52,5202 %, recall 11,4700 % y AUC 0,585285. La etapa parcial
de 200 también mantiene una diferencia importante entre aprendizaje local y
rendimiento global. Esto respalda investigar la heterogeneidad de los chunks,
pero no demuestra por sí solo una causa ni una mejora de la futura mezcla global.

Los valores se extrajeron directamente de los JSONL antes de eliminarlos; se
preservan métricas de los 129 cierres y los mejores/últimos estados. No se conservan
las 15.893 entradas individuales por chunk, sus logits ni los checkpoints.
SHA-256 de las fuentes retiradas (trazabilidad, no copia de seguridad):

- `chunks_100/history_mlp_primary_secondary.jsonl`: `7399904b0b00b49f3b99a66e0175ef23b6dc5760deeffd91f5540845045b38a5`.
- `chunks_100/monitor_history.jsonl`: `52a78cb34530049ab8dd3ac57e12de37d2734231d6792919117a91049db88dfb`.
- `chunks_200/history_mlp_primary_secondary.jsonl`: `d2475ee1dc65813e506983942df3e9dcab3c97e45bafc097a8824d26dbd140ca`.
- `chunks_200/monitor_history.jsonl`: `74e64d87768ef6b0f41b62fdf8c1954d143000fbd610d9dcfad16423d9168d9d`.
