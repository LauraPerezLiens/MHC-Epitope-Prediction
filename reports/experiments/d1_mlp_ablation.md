# NAP-CNB · Ablación por modalidad sobre D1

Mismo protocolo que E1/E2: D1 certificado con representaciones originales y
etiqueta global, partición por **primaria exacta** con semilla 42
(TRAIN 12.083.630 / VALIDATION 1.507.558 / TEST 1.509.404, prevalencia 25,46 %),
manifiesto D1 `eb559799…`, scaler de E1 `0a983b6c…` **sin reajustar**, 3 épocas,
AdamW 1e-3 / 1e-4, lotes de 8.192, prevalencia natural, selección de época por
mínima log loss de VALIDATION, umbral por F1 máximo en VALIDATION y TEST puntuado
una sola vez. Entre las tres filas cambia **únicamente el subconjunto de columnas**.

| Modelo | Características | Época | TEST ROC-AUC | TEST AP | TEST log loss |
|---|---:|---:|---:|---:|---:|
| **Solo ProtT5** | 1.024 (cols 0–1024) | 2 | **0,682302** | **0,415255** | **0,526036** |
| E2 · ProtT5 + SecondaryBERT | 1.792 | 2 | 0,680107 | 0,412129 | 0,527197 |
| Solo SecondaryBERT | 768 (cols 1024–1792) | 2 | 0,601431 | 0,316272 | 0,555252 |

Δ de quitar SecondaryBERT a E2: **+0,002195 ROC-AUC**, +0,003126 AP, −0,001161
log loss.

Matrices de confusión en TEST, con filas de clase real y columnas de clase
predicha en orden 0, 1:

- Solo ProtT5 `[[577633, 547615], [98826, 285330]]`
- E2 `[[575995, 549253], [99770, 284386]]`
- Solo SecondaryBERT `[[386989, 738259], [78139, 306017]]`

## Contexto de información

Referencias medidas sobre las mismas particiones, para situar el 0,601 de la
modalidad secundaria:

| Representación | Características | VALIDATION ROC-AUC |
|---|---:|---:|
| Composición C/H/E, regresión logística | 3 | 0,592364 |
| C/H/E posicional one-hot, regresión logística | 75 | 0,594317 |
| SecondaryBERT promediado, MLP | 768 | 0,601155 |
| ProtT5 promediado, MLP | 1.024 | 0,681629 |

El recuento de C, H y E en la ventana alcanza 0,592364. El aporte de SecondaryBERT
sobre esos tres enteros es de +0,0088 ROC-AUC, y su aporte sobre ProtT5 es
negativo. Detalle y cotas de información en
[la auditoría consolidada](../auditoria_consolidada.md), sección 8.4.

## Alcance

Una sola semilla y una sola ejecución por modalidad. La diferencia de +0,0022
entre ProtT5 solo y las 1.792 características es pequeña; lo que estos resultados
sostienen no es que ProtT5 solo sea mejor, sino que **añadir SecondaryBERT no
mejora de forma medible**. Para afirmar el signo del efecto harían falta varias
semillas. La partición por primaria exacta deja vecinos inmediatos entre
particiones, de modo que los tres niveles absolutos están afectados en la misma
dirección; la comparación entre modalidades no lo está.

Artefactos en `results/nap_cnb_v2_training/d1_mlp_ablation/{primary,secondary}/`
con configuración, checkpoints, selección, métricas y los Parquet de predicciones.
