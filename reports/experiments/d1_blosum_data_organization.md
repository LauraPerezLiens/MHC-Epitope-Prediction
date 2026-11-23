# NAP-CNB · Organización de artefactos históricos BLOSUM62

**Fecha** 23 de noviembre de 2026 (UTC).

El catálogo organiza D1 y las vistas históricas mediante referencias a sus archivos existentes. E3 y E4 quedan registrados como **no ejecutados**. [Catálogo de artefactos](../../results/nap_cnb_v2_blosum_preparation/organization/artifact_catalog.json) · [Plantilla de comparación](../../results/nap_cnb_v2_blosum_preparation/organization/experiment_comparison.json)

## Ubicación y reutilización

Las rutas del catálogo se resuelven desde la raíz del repositorio. El directorio `results/nap_cnb_v2_blosum_preparation/organization/` contiene dos manifiestos JSON de esquema 1. El catálogo usa `path` como clave de consulta del manifiesto de integridad existente. Allí figuran por archivo el recibo, la huella de cada flujo y su estado. Las dimensiones, los recuentos y la configuración se consultan en el catálogo y sus manifiestos de origen.

| Componente | Ubicación y uso documentado |
|---|---|
| D1 original | `results/nap_cnb_v2_d1_original_manifest/manifest.json` y `original_observations.parquet`. El catálogo SQLite original reside en `results/nap_cnb_v2_blosum_preparation/d1_original_catalog.sqlite`. Estas referencias conservan las claves, etiquetas y splits certificados. |
| Secuencias BLOSUM62 históricas | `data/used_data/data_intermediate.tar.zst` conserva los once CSV inventariados. Su SHA-256 de contenedor coincide con el recibo. La consulta por miembro requiere su nombre interno exacto. |
| ProtT5 familiar | `data/data_input_nn/{especie}/{clase}/{familia}/*_blosum_ProtT5_chunks/`. NPY.ZST de 1.024 float32, con CSV por bloque, índice maestro comprimido y recibos. |
| SecondaryBERT familiar | `data/data_input_nn/{especie}/{clase}/{familia}/*_SecondaryBERT_by_group/`. NPY.ZST canónicos en `chunks/`, dimensión 768 float32 por grupo, con configuración y manifiestos familiares. |
| Reordenado histórico | `data/data_input_nn_shuffled/`. Conserva ProtT5 reordenado, índices maestros mixtos de dirección y split, arrays auxiliares y referencias a SecondaryBERT. |
| Concatenado histórico | `data/data_input_nn_shuffled_concatenate/`. Contiene 14.499 NPY directos de 1.792 float32 con recibos, metadatos y dos manifiestos en la raíz. Es una vista mixta histórica. |
| Procedencia e integridad | El manifiesto familiar de reordenamiento identifica fuentes mediante IDs. Los recibos de archivo `verified_zstd_v1` distinguen la huella de los bytes comprimidos de la del flujo expandido. `feature_layout.json` declara el formato `primary_secondary_float32_v1`. El manifiesto de reordenamiento histórico carece de versión explícita de esquema. |

Los archivos pueden reutilizarse para consultar el material archivado y su trazabilidad a nivel de archivo. Los manifiestos históricos conservan rutas absolutas bajo `/data/nap/lperez_nn` y configuraciones con rutas bajo `/home/nap/lperez_nn`. Las once rutas planas de los índices familiares y las 1.128 dependencias de la firma común de concatenación se resuelven por sus copias `.zst` y recibos en el árbol de origen. El concatenado depende del árbol reordenado para los índices maestros. El directorio expandido de intermedios quedó vacío tras el archivado. [Procedencia](d1_blosum_artifact_provenance.md) · [Manifiesto por archivo](d1_blosum_integrity_manifest.jsonl)

## Disponibilidad por familia

| Familia | BLOSUM62 | ProtT5 | SecondaryBERT | Concatenado | Estado |
|---|---|---:|---:|---|---|
| HLA-A | CSV en TAR¹ | 2.656 bloques | 100 bloques | Vista mixta² | SHA-256 expandido cotejado en 3 ProtT5 y 3 SecondaryBERT |
| HLA-B | CSV en TAR¹ | 2.767 bloques | 104 bloques | Vista mixta² | SHA-256 expandido cotejado en 2 ProtT5 y 2 SecondaryBERT |
| HLA-C | CSV en TAR¹ | 2.025 bloques | 77 bloques | Vista mixta² | SHA-256 expandido cotejado en 2 ProtT5 y 2 SecondaryBERT |
| HLA-DP | CSV en TAR¹ | 1.308 bloques | 50 bloques | Vista mixta² | SHA-256 expandido cotejado en 2 ProtT5 y 2 SecondaryBERT |
| HLA-DQ | CSV en TAR¹ | 622 bloques | 24 bloques | Vista mixta² | SHA-256 expandido cotejado en 2 ProtT5 y 2 SecondaryBERT |
| HLA-DR | CSV en TAR¹ | 1.973 bloques | 75 bloques | Vista mixta² | SHA-256 expandido cotejado en 2 ProtT5 y 2 SecondaryBERT |
| H2-D | CSV en TAR¹ | 1.104 bloques | 42 bloques | Vista mixta² | SHA-256 expandido cotejado en 2 ProtT5 y 2 SecondaryBERT |
| H2-K | CSV en TAR¹ | 1.566 bloques | 59 bloques | Vista mixta² | SHA-256 expandido cotejado en 2 ProtT5 y 2 SecondaryBERT |
| H2-L | CSV en TAR¹ | 2 bloques | 1 bloques | Vista mixta² | SHA-256 expandido cotejado en 1 ProtT5 y 1 SecondaryBERT |
| H2-IA | CSV en TAR¹ | 466 bloques | 18 bloques | Vista mixta² | SHA-256 expandido cotejado en 2 ProtT5 y 2 SecondaryBERT |
| H2-IE | CSV en TAR¹ | 14 bloques | 1 bloques | Vista mixta² | SHA-256 expandido cotejado en 2 ProtT5 y 1 SecondaryBERT |

¹ El inventario acredita once CSV dentro del TAR. Los nombres base del catálogo son pistas derivadas de las rutas familiares. La ruta interna exacta por familia queda pendiente de identificar en el listado del contenedor.

² La vista mixta referencia las once fuentes en el manifiesto de reordenamiento. La tabla carece de recuentos concatenados atribuidos por familia. Los 1.449.852.950 registros históricos declarados mezclan originales y derivados. SecondaryBERT cuenta 55.763.575 entradas de grupo. Esas unidades dejan indeterminada la alineación por fila y la cobertura respecto a D1.

## Integridad y correspondencias pendientes

La revisión previa registró 1.218 coincidencias nuevas y conservó 38 previas. Quedan 44.527 comprobaciones de flujo pendientes en 29.515 archivos. El estado de la verificación se conserva por flujo y por familia. Para una consulta futura están pendientes la verificación de los bytes de los archivos concretos que se requieran, los nombres internos de los CSV y la evidencia de revisión, tokenizador y ejecución de los lotes históricos ProtT5. Sigue sin acreditarse la correspondencia variante–embedding, la alineación individual entre representaciones y la identidad respecto a D1. [Informe de integridad](d1_blosum_integrity_verification.md)

## Comparación experimental

D1 identifica cada observación por primaria exacta y cadena C/H/E. La etiqueta `label_global` expresa evidencia registrada. La clase negativa incluye ventanas sin confirmación experimental. El scaler de E1 se ajustó solo sobre las 12.083.630 filas de TRAIN y E2 reutilizó el mismo archivo. El orden de entrada es ProtT5 (1.024) seguido de SecondaryBERT (768). El scaler está en `results/nap_cnb_v2_training/d1_lr_original_baseline/scaler.npz`. Su SHA-256 publicado es `0a983b6caa8a6674d8732ef238ca5cdc7cc623869b247786c22fcc1682d28048`.

| Partición original | Filas | Positivos |
|---|---:|---:|
| TRAIN | 12.083.630 | 3.076.633 |
| VALIDATION | 1.507.558 | 383.839 |
| TEST | 1.509.404 | 384.156 |

E1 y E2 usaron tres épocas, lotes de hasta 8.192, AdamW con tasa 0,001 y weight decay 0,0001, semilla 42 y prevalencia natural. La MLP empleó capas ocultas de 512 y 128, LayerNorm, ReLU y dropout 0,30. Ambos seleccionaron la época 2 por menor log loss en VALIDATION original. Fijaron el umbral por máximo F1 en VALIDATION, con desempate por el menor logit. Los umbrales fueron −1,29552305 en E1 y −1,09667778 en E2. La clase predicha es positiva si el logit es mayor o igual al umbral. [E1](d1_lr_original_baseline.md) · [E2](d1_mlp_original_baseline.md)

| Métrica de TEST | E1 LR | E2 MLP | E3 LR | E4 MLP |
|---|---:|---:|---|---|
| ROC-AUC | 0.654641 | 0.680107 | Pendiente | Pendiente |
| Average Precision | 0.375738 | 0.412129 | Pendiente | Pendiente |
| Log loss | 0.539791 | 0.527197 | Pendiente | Pendiente |
| Precisión | 0.324342 | 0.341138 | Pendiente | Pendiente |
| Recall | 0.750640 | 0.740288 | Pendiente | Pendiente |
| F1 | 0.452964 | 0.467051 | Pendiente | Pendiente |
| Matriz de confusión | `[[524541,600707],[95793,288363]]` | `[[575995,549253],[99770,284386]]` | Pendiente | Pendiente |

Para una comparación válida, fijar las mismas claves, etiquetas y asignaciones D1, seleccionar checkpoint y umbral solo en VALIDATION original y puntuar el mismo TEST después de la selección. Conservar el scaler común para el contraste de referencia. Registrar por separado cualquier cambio de preprocesamiento, población de ajuste, presupuesto de actualizaciones o hiperparámetros. Usar ROC-AUC y AP globales sobre logits, log loss sobre probabilidades y matrices con filas reales y columnas predichas en orden 0, 1. Calcular diferencias E3 − E1 y E4 − E2 sobre ese TEST. La plantilla conserva métricas de VALIDATION y TEST y deja los campos de E3 y E4 en `null`. Las diferencias E2 − E1 describen las ejecuciones originales y no estiman un efecto del aumento.
