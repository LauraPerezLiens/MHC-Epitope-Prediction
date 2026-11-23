# NAP-CNB · Baseline MLP original D1

D1 certificado con secuencias originales, etiquetas globales y 1.792 características en el orden ProtT5 (1.024) y SecondaryBERT (768). Se reutilizaron en modo lectura los bloques locales de la LR para TRAIN y VALIDATION. TEST se leyó al final desde el catálogo certificado y las copias verificadas de las dos modalidades.

| Partición | Observaciones | Positivos | Prevalencia |
|---|---:|---:|---:|
| TRAIN | 12,083,630 | 3,076,633 | 25.461165% |
| VALIDATION | 1,507,558 | 383,839 | 25.460977% |
| TEST | 1,509,404 | 384,156 | 25.450840% |

## Configuración y selección

Se reutilizó el scaler TRAIN de la LR en `results/nap_cnb_v2_training/d1_lr_original_baseline/scaler.npz`. Se comprobó su contrato de procedencia y el SHA-256 `0a983b6caa8a6674d8732ef238ca5cdc7cc623869b247786c22fcc1682d28048` antes de entrenar.

MLP histórica 1.792 → 512 → 128 → 1, con LayerNorm, ReLU y dropout 0,30 en cada capa oculta. BCEWithLogitsLoss y AdamW con tasa 0,001 y weight decay 0,0001. Tres épocas y lotes de hasta 8.192 filas, en prevalencia natural, sin BLOSUM62, remuestreo ni ponderación de clases. Semilla 42 y aleatorización por bloques igual a la LR, con semillas 42, 43 y 44 por época. PyTorch 2.14.0+cu130 en float32 con algoritmos deterministas habilitados. El SHA-256 del manifiesto D1 fue `eb55979937a89721eb3dfbd703ba4efe40ffc8e76487ce61fb366936ff47b0a6`.

VALIDATION seleccionó la época **2** por menor log loss. El umbral de logit **-1.09667778** maximizó F1 en VALIDATION, con desempate por el menor logit. TEST se puntuó después de registrar la selección.

| Época | Log loss TRAIN | Log loss VALIDATION |
|---:|---:|---:|
| 1 | 0.538539 | 0.536629 |
| 2 | 0.533632 | 0.527658 |
| 3 | 0.526445 | 0.542042 |

## Métricas y comparación

| Métrica | MLP VALIDATION | MLP TEST | LR TEST | Δ TEST (MLP − LR) |
|---|---:|---:|---:|---:|
| ROC-AUC | 0.679222 | 0.680107 | 0.654641 | +0.025466 |
| Average Precision | 0.411580 | 0.412129 | 0.375738 | +0.036391 |
| Log loss | 0.527658 | 0.527197 | 0.539791 | -0.012594 |
| Precision | 0.341075 | 0.341138 | 0.324342 | +0.016796 |
| Recall | 0.739380 | 0.740288 | 0.750640 | -0.010353 |
| F1 | 0.466811 | 0.467051 | 0.452964 | +0.014086 |
| Prevalencia | 0.254610 | 0.254508 | 0.254508 | +0.000000 |
| Observaciones | 1,507,558 | 1,509,404 | 1,509,404 | 0 |

ROC-AUC y AP se calcularon globalmente sobre todos los logits guardados, sin histogramas. Las matrices tienen filas de clase real y columnas de clase predicha, en orden 0, 1.

- MLP VALIDATION `[[575438, 548281], [100036, 283803]]`.
- MLP TEST `[[575995, 549253], [99770, 284386]]`.
- LR TEST `[[524541, 600707], [95793, 288363]]`.
- Diferencia TEST (MLP − LR) `[[51454, -51454], [3977, -3977]]`.

### Predicciones discrepantes en TEST

Se cotejaron fila por fila la secuencia primaria, la estructura secundaria y la etiqueta global de ambos modelos en VALIDATION y TEST. Se reprodujeron las métricas sobre los logits guardados.

Con los umbrales escogidos en VALIDATION, los modelos discrepan en 262,097 filas de TEST (17.36%), que corresponden a 254,243 de 1,452,793 secuencias primarias distintas.

| Etiqueta real | LR negativa → MLP positiva | LR positiva → MLP negativa |
|---:|---:|---:|
| 0 | 75,338 | 126,792 |
| 1 | 27,995 | 31,972 |

En esas filas, la MLP corrige 154,787 errores de la LR e introduce 107,310 errores donde la LR acertaba.

Las diferencias son descriptivas para este TEST y esta semilla. Las representaciones que comparten secuencia primaria, las ventanas solapadas y las secuencias similares pueden estar correlacionadas. El número de filas no equivale al número de observaciones independientes. La etiqueta global representa evidencia registrada y la clase negativa incluye ventanas sin confirmación experimental. La evaluación no estima incertidumbre fuera de D1. Como ambos modelos comparten una configuración inicial fija y solo se entrenaron durante tres épocas, el resultado corresponde a estas ejecuciones concretas.

## Tiempo y recursos

- MLP en NVIDIA GeForce RTX 3090 (GPU física 2), con dos hilos de PyTorch y un hilo BLAS/OpenMP. Entrenamiento más validación por época 1898.4 s. Tiempo interno total con la caché local 2207.3 s.
- Pico de memoria GPU de PyTorch 223.1 MiB asignados y 310.0 MiB reservados. Pico RSS 84.08 GiB, incluidas páginas de archivos mapeados.
- La LR tardó 1479.4 s en CPU incluyendo validaciones por época. La MLP tiene 985,089 parámetros entrenables y la LR tiene 1.793. El tiempo de pared refleja también el hardware y el acceso a los datos.

## Artefactos

El directorio `results/nap_cnb_v2_training/d1_mlp_original_baseline/` guarda la configuración, los checkpoints mejor y final, la selección, los logs, las métricas, los Parquet de VALIDATION y TEST con identificadores, etiquetas, logits y probabilidades, y la comparación pareada. `artifacts.sha256` registra las huellas de las salidas.
