# Análisis conjunto de los datos — 17 de noviembre de 2026

Las comprobaciones solicitadas han terminado. La muestra técnica de embeddings pasó. Los hallazgos principales afectan a la definición de las etiquetas y a la independencia de los grupos entre splits; no demuestran corrupción de embeddings ni explican por sí solos el rendimiento del MLP.

## Secuencias con anotaciones mixtas

- Filas originales: 55,763,575; secuencias distintas: 15,135,904.
- Secuencias con ambas etiquetas al combinar las 11 familias: 3,494,284 (23.09 %).
- Filas que contienen esas secuencias: 21,877,306 (39.23 %).
- Filas cuya secuencia tiene ambas etiquetas dentro de su propia familia: 916,544 (1.64 % de todas las filas originales).
- Filas señaladas globalmente pero consistentes dentro de su propia familia: 20,960,762 (95.81 % de las filas señaladas). La etiqueta opuesta aparece fuera de esa familia.

El número de filas señaladas no es un número de secuencias distintas, de errores confirmados ni de entradas completas idénticas. No se compararon embeddings en esta búsqueda. Dentro de una familia, las secuencias pueden corresponder a distintas proteínas, posiciones o anotaciones; las modalidades estructurales también pueden diferir. Los negativos se construyen por ausencia de epítopos positivos anotados, no por evidencia experimental negativa.

| Familia | Filas originales | Filas con ambas etiquetas globalmente | % global | Filas con ambas etiquetas dentro de la familia | % dentro de familia |
|---|---:|---:|---:|---:|---:|
| human/mhc-I/HLA-A | 10,214,658 | 4,097,008 | 40.11 | 231,037 | 2.26 |
| human/mhc-I/HLA-B | 10,639,963 | 4,481,313 | 42.12 | 362,240 | 3.40 |
| human/mhc-I/HLA-C | 7,788,459 | 3,278,058 | 42.09 | 68,769 | 0.88 |
| human/mhc-II/HLA-DP | 5,027,325 | 2,559,927 | 50.92 | 36,880 | 0.73 |
| human/mhc-II/HLA-DQ | 2,389,441 | 1,245,355 | 52.12 | 36,079 | 1.51 |
| human/mhc-II/HLA-DR | 7,588,227 | 3,641,040 | 47.98 | 116,976 | 1.54 |
| mouse/mhc-I/H2-D | 4,244,842 | 887,062 | 20.90 | 14,313 | 0.34 |
| mouse/mhc-I/H2-K | 6,022,825 | 1,220,769 | 20.27 | 33,859 | 0.56 |
| mouse/mhc-I/H2-L | 4,448 | 2,761 | 62.07 | 0 | 0.00 |
| mouse/mhc-II/H2-IA | 1,790,731 | 446,573 | 24.94 | 16,391 | 0.92 |
| mouse/mhc-II/H2-IE | 52,656 | 17,440 | 33.12 | 0 | 0.00 |

El 93.53 % de las filas positivas tiene una secuencia que aparece como negativa en alguna parte del conjunto. Para las negativas, la proporción equivalente es 27.58 %. Esto justifica revisar el significado del objetivo y el contexto MHC disponible; no autoriza a cambiar automáticamente etiquetas ni a eliminar todos los casos.

## Distribución de grupos entre splits

Se revisaron las 1,449,852,950 filas aumentadas y 55,763,575 grupos. El reparto por filas es exactamente 80/10/10: TRAIN=1,159,882,360, VALIDATION=144,985,295, TEST=144,985,295.

- Grupos en varios splits: 55,595,967 (99.70 %).
- Grupos en los tres splits: 48,726,754 (87.38 %).
- Grupos solo en TRAIN: 167,608.
- Todos los grupos presentes en VALIDATION y TEST también aparecen en TRAIN. No hay grupos exclusivos de VALIDATION o TEST.

El solapamiento concuerda con la política implementada de repartir filas después de generar 26 variantes por grupo. No es una avería del shuffle: el reparto actual permite explícitamente compartir grupos. Sirve para evaluar variantes de grupos conocidos, pero no para estimar generalización a grupos nuevos. Cambiar a un split por grupo sería un cambio del protocolo de evaluación. Separar por proteína o clúster de similitud sería una condición adicional; esta comprobación no la ha evaluado.

## Primary/Secondary y sensibilidad a sustituciones

La muestra de 33 grupos (3 por familia, 3 chunks) coincidió exactamente con Primary shuffled archivado y Secondary original: diferencias máximas cero y valores finitos. Es evidencia favorable limitada a la muestra, no una verificación exhaustiva ni un contraste de Primary anterior al shuffle.

En la prueba de 110 grupos y 2.750 sustituciones BLOSUM62, la similitud coseno mediana fue 0,9883. La distancia mediana después del scaler fue 6,60, frente a 44,29 en 495 pares de originales distintos de la misma familia. Las variantes suelen ser próximas, aunque algunas sustituciones producen cambios grandes. No se midió el efecto sobre predicciones o accuracy. Véase `results/primary_mutation_test/report.md` para los límites de muestreo y de reconstrucción de variantes.

## Próximo paso recomendado

1. Definir si el objetivo es detectar cualquier epítopo anotado o predecirlo bajo un contexto MHC concreto. Comprobar si ese contexto debe estar en la entrada o si conviene separar tareas por familia. Un identificador numérico de grupo no sustituye al contexto biológico.
2. Revisar una muestra de anotaciones mixtas dentro de familia, incluyendo proteína, posición, epítopo seleccionado y evidencia. No eliminar por defecto el 39,23 % de filas señalado globalmente.
3. Si interesa generalizar a ejemplos nuevos, diseñar un protocolo que mantenga cada grupo y sus variantes en un único split. Para proteínas nuevas, el criterio de separación debe ampliarse; hacerlo solo por grupo no basta. El scaler de un futuro protocolo se debe ajustar con su nuevo TRAIN.
4. Reentrenar una referencia con el objetivo y la evaluación acordados antes de dedicar recursos a otros cambios de arquitectura. Las métricas antiguas siguen siendo descriptivas del protocolo anterior; tampoco eran un TEST final independiente, porque TEST STAGE seleccionaba checkpoints.

No se han modificado etiquetas, splits, embeddings o scaler durante este análisis.

Fuentes: `results/data_contradictions/{summary.json,analysis.json,contradictions.csv}`, `results/group_split_check/{summary.json,group_splits.csv}`, `results/sampled_modalities_check/summary.json` y `results/primary_mutation_test/summary.json`.
