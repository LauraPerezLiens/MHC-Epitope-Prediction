# NAP-CNB · Baseline LR original D1

D1 certificado, solo representaciones originales con etiqueta global y sin BLOSUM62. Cada observación se identifica mediante la primaria exacta y la cadena C/H/E. Se usan 1.024 características ProtT5 y 768 SecondaryBERT, en ese orden. Las asignaciones certificadas permanecen fijas.

| Split | Observaciones | Positivos | Prevalencia |
|---|---:|---:|---:|
| TRAIN | 12,083,630 | 3,076,633 | 25.4612% |
| VALIDATION | 1,507,558 | 383,839 | 25.4610% |
| TEST | 1,509,404 | 384,156 | 25.4508% |

## Preparación y protocolo fijado

Los diez SHA-256 de insumos publicados en el manifiesto D1 se cotejan antes de preparar el experimento. La caché compacta local de SecondaryBERT comprueba los recibos de archivos históricos, límites de offsets y hashes por clave y vector nuevo. Los 146 shards ProtT5 se copiaron a disco local y se verificaron cabecera, finitud, cobertura y el digest certificado de cada lote ligado a sus claves.

El ajuste del scaler está configurado para 12.083.630 representaciones TRAIN, lotes de hasta 8.192, momentos poblacionales acumulados de forma estable en float64 y parámetros guardados en float32 según el formato v2. Se usa escala 1 en características constantes o con desviación por debajo del umbral contractual. El mismo archivo se aplica en los tres splits.

Regresión logística afín del motor existente, con el lector explícito D1 y un bucle que conserva prevalencia natural. AdamW, tasa 0,001, weight decay 0,0001, tres épocas fijadas, lotes de hasta 8.192, semilla 42 y sin ponderación de clase ni remuestreo. Menor log loss de VALIDATION para elegir época y máximo F1 en VALIDATION para fijar umbral. Los demás hiperparámetros se fijan de antemano. TEST se puntúa una vez tras registrar la selección.

Ejecución en Intel Xeon Gold 5218R, dos hilos PyTorch y un hilo de BLAS/OpenMP, con prioridad baja de CPU y disco y CUDA oculto al proceso. Al inicio, el host mostraba 170 GiB de RAM disponible y 20 TiB libres en el volumen de trabajo.
Pico RSS del proceso de preparación por bloques y LR: 143.24 GiB.
Scaler publicado en `results/nap_cnb_v2_training/d1_lr_original_baseline/scaler.npz`. SHA-256: `0a983b6caa8a6674d8732ef238ca5cdc7cc623869b247786c22fcc1682d28048`.

## Resultados

Época seleccionada: **2**. Ajuste LR y validaciones por época: **1479.4 s**. Ajuste del scaler: **1394.3 s**. Tiempo del proceso con bloques locales, scaler, LR y evaluación final: **3684.8 s**; excluye la preparación inicial de las modalidades.

| Métrica | VALIDATION | TEST |
|---|---:|---:|
| roc_auc | 0.653706 | 0.654641 |
| average_precision | 0.375348 | 0.375738 |
| log_loss | 0.540307 | 0.539791 |
| precision | 0.324327 | 0.324342 |
| recall | 0.750541 | 0.750640 |
| f1 | 0.452931 | 0.452964 |
| prevalence | 0.254610 | 0.254508 |
| rows | 1507558 | 1509404 |
| confusion_matrix | [[523545, 600174], [95752, 288087]] | [[524541, 600707], [95793, 288363]] |

ROC-AUC y AP calculados globalmente sobre todos los logits, sin histogramas. Matriz con filas de clase real y columnas de clase predicha, en orden 0, 1. Las métricas de VALIDATION corresponden al checkpoint y umbral seleccionados en esa partición.

## Artefactos y comparabilidad

Directorio aislado: `results/nap_cnb_v2_training/d1_lr_original_baseline`. Los logs registran el progreso. Para amortizar el acceso por claves se materializaron bloques locales temporales de TRAIN y VALIDATION, con seis lectores y un cotejo por fila de la ruta original en una muestra. TEST se leyó al final desde los catálogos certificados y las copias verificadas de sus modalidades. La primera preparación en el volumen compartido se estancó durante la sincronización de la caché temporal. La segunda prepara la caché en disco local con hasta seis lectores de archivo por lotes de claves. El resultado completo guarda scaler.npz, config.json, best.pt, last.pt, selection.json, metrics.json y los Parquet de predicciones VALIDATION/TEST con claves, etiquetas, logits y probabilidades.

El estimando es evidencia global registrada para primarias exactas retenidas. Puede haber proteínas compartidas y secuencias similares entre splits. Para comparar con MLP y escenarios posteriores se preservarán las claves y asignaciones originales de TEST y se registrarán población de ajuste, scaler y protocolo de selección por variante experimental. Los derivados futuros deben heredar la partición del original.

## Verificación de cierre

Se cotejaron las claves y etiquetas de todas las filas de ambos Parquet de predicciones contra D1 y se reprodujeron las métricas a partir de los logits guardados, sin volver a puntuar TEST. El digest del manifiesto D1 y el del informe de splits permanecieron iguales. Las huellas de las salidas están en `artifacts.sha256` dentro del directorio del experimento.

El pico RSS incluye páginas de archivos mapeados, además de memoria de trabajo. Las copias en disco local sirvieron de caché de ejecución. Los almacenes certificados siguen siendo la referencia de los embeddings. La MLP histórica permaneció activa durante la ejecución.
