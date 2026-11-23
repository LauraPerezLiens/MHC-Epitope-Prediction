# NAP-CNB · E3 · LR con aumento BLOSUM62

**Estado de E3.** El entrenamiento y la evaluación de E3 están pendientes. Generar o vincular variantes proteicas para entrenar un predictor de epítopos sobre secuencias mutadas podría facilitar el diseño de cambios que alteren el reconocimiento inmunitario. Esa etapa impide completar el experimento. El coste de cómputo de E3 queda sin medir.

## Referencia verificada

Se cotejaron las huellas SHA-256 de los artefactos publicados de E1 y E2. El registro de comparación verificado documenta coincidencia fila por fila de la secuencia primaria, la estructura secundaria y la etiqueta global entre ambos experimentos en VALIDATION y TEST.

| Partición D1 original | Filas | Positivos | Prevalencia |
|---|---:|---:|---:|
| TRAIN | 12.083.630 | 3.076.633 | 25,4612 % |
| VALIDATION | 1.507.558 | 383.839 | 25,4610 % |
| TEST | 1.509.404 | 384.156 | 25,4508 % |

El scaler de referencia se ajustó sobre TRAIN original, en el orden ProtT5 (1.024 características) y SecondaryBERT (768). Su SHA-256 verificado es `0a983b6caa8a6674d8732ef238ca5cdc7cc623869b247786c22fcc1682d28048`.

## Métricas de referencia en TEST

| Métrica | E1 · LR original | E2 · MLP original |
|---|---:|---:|
| ROC-AUC | 0,654641 | 0,680107 |
| Average Precision | 0,375738 | 0,412129 |
| Log loss | 0,539791 | 0,527197 |
| Precision | 0,324342 | 0,341138 |
| Recall | 0,750640 | 0,740288 |
| F1 | 0,452964 | 0,467051 |
| Falsos positivos | 600.707 | 549.253 |
| Falsos negativos | 95.793 | 99.770 |
| Entrenamiento y validaciones | 1.479,4 s en CPU | 1.898,4 s en RTX 3090 |

La procedencia y el número de variantes de E3, su herencia de etiquetas y particiones, el presupuesto efectivo de actualizaciones y las métricas de VALIDATION y TEST quedan sin verificar. Las cifras de E1 y E2 corresponden a entrenamientos sobre D1 original. La diferencia entre ellas no permite estimar el efecto del aumento BLOSUM62.

## Artefactos de referencia

- [Informe E1](d1_lr_original_baseline.md) y [artefactos E1](../../results/nap_cnb_v2_training/d1_lr_original_baseline).
- [Informe E2](d1_mlp_original_baseline.md) y [comparación pareada E1/E2](../../results/nap_cnb_v2_training/d1_mlp_original_baseline/comparison.json).
