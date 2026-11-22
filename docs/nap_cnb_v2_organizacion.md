# Organización de NAP-CNB v2

Se inventariaron **51 scripts Python** en `data_pipeline/scripts/`. La fase 3B añadió el generador v2 a `embeddings/primary_structure/`, junto al generador histórico, y dos pruebas sintéticas en un único archivo. Los cambios se limitaron a código funcional, configuración del piloto y documentación.

## Estructura que ya funciona

| Ubicación | Función |
|---|---|
| `data_pipeline/scripts/` | Código por función, con construcción, estructura, embeddings, índices y verificación |
| `env/` | Definiciones de entornos y dependencias |
| `docs/` | Decisiones, contratos y manual de operación |
| `tests/` | Pruebas de integridad y contratos del código |
| `results/` | Informes, artefactos de auditoría, piloto y futuro almacén definitivo |
| `data/` y `model/` | Datos, archivos comprimidos y pesos |
| `neural_network/` | Consumidores y experimentos de modelos |

Evitar carpetas de código por fase. Mantener la estructura funcional y consolidar utilidades compartidas cuando sus contratos se prueben. Propuesta de ruta de datos nueva `results/nap_cnb_v2_prott5/final/`. El piloto se conserva en `results/nap_cnb_v2_prott5/pilot/`.

## Inventario de código

**A** es esencial para v2 o para contratos históricos aún usados. **B** es validación o soporte reutilizable. **C** es un candidato a archivar junto a sus evidencias. **D** es un candidato a retirar del código activo cuando se resuelvan sus dependencias. Recuento de archivos A=18, B=16, C=15, D=2.

| Script | Clase | Motivo y condición |
|---|:---:|---|

| [check_group_splits.py](../data_pipeline/scripts/check_group_splits.py) | B | Verificación reutilizable de integridad y procedencia. Mantener la interfaz actual mientras haya consumidores. |
| [check_sampled_modalities.py](../data_pipeline/scripts/check_sampled_modalities.py) | B | Verificación reutilizable de integridad y procedencia. Mantener la interfaz actual mientras haya consumidores. |
| [data_archiving/archive_inputs.py](../data_pipeline/scripts/data_archiving/archive_inputs.py) | A | Publica y verifica archivos comprimidos usados por lectores históricos. |
| [data_augmentation/generate_blosum62_variants.py](../data_pipeline/scripts/data_augmentation/generate_blosum62_variants.py) | A | Herramientas de la ruta histórica o futura supervisada. Conservar por compatibilidad con artefactos, concatenador y pruebas. |
| [data_classification/epitope_classification.py](../data_pipeline/scripts/data_classification/epitope_classification.py) | A | Descarga y clasificación históricas que alimentan la etapa de construcción. |
| [data_classification/fetch_parent_proteins_fastas.py](../data_pipeline/scripts/data_classification/fetch_parent_proteins_fastas.py) | A | Descarga y clasificación históricas que alimentan la etapa de construcción. |
| [data_download/build_iedb_dataset.py](../data_pipeline/scripts/data_download/build_iedb_dataset.py) | A | Descarga y clasificación históricas que alimentan la etapa de construcción. |
| [data_shuffling/reorder_chunks.py](../data_pipeline/scripts/data_shuffling/reorder_chunks.py) | A | Herramientas de la ruta histórica o futura supervisada. Conservar por compatibilidad con artefactos, concatenador y pruebas. |
| [data_shuffling/resume_reorder_chunks.py](../data_pipeline/scripts/data_shuffling/resume_reorder_chunks.py) | B | Reanudación histórica especializada. Hace falta cotejar contrato de checkpoints de reorder_chunks antes de integrar. |
| [data_splitting/check_master_split.py](../data_pipeline/scripts/data_splitting/check_master_split.py) | B | Verificación reutilizable de integridad y procedencia. Mantener la interfaz actual mientras haya consumidores. |
| [data_splitting/prepare_chunk_metadata.py](../data_pipeline/scripts/data_splitting/prepare_chunk_metadata.py) | A | Herramientas de la ruta histórica o futura supervisada. Conservar por compatibilidad con artefactos, concatenador y pruebas. |
| [data_splitting/split_data.py](../data_pipeline/scripts/data_splitting/split_data.py) | A | Herramientas de la ruta histórica o futura supervisada. Conservar por compatibilidad con artefactos, concatenador y pruebas. |
| [embedding_concatenation/concatenate_primary_secondary.py](../data_pipeline/scripts/embedding_concatenation/concatenate_primary_secondary.py) | A | Herramientas de la ruta histórica o futura supervisada. Conservar por compatibilidad con artefactos, concatenador y pruebas. |
| [embeddings/primary_structure/generate_prott5_embeddings.py](../data_pipeline/scripts/embeddings/primary_structure/generate_prott5_embeddings.py) | D | Solo sustituido para la ruta v2 de secuencias únicas. Conserva valor como receta histórica y para las auditorías que importan sus funciones. |
| [embeddings/primary_structure/prott5_v2.py](../data_pipeline/scripts/embeddings/primary_structure/prott5_v2.py) | A | Generación de las representaciones originales v2. La selección definitiva y el inventario de primarias son las entradas. |
| [embeddings/secondary_structure/check_secondary_embeddings.py](../data_pipeline/scripts/embeddings/secondary_structure/check_secondary_embeddings.py) | B | Verificación reutilizable de integridad y procedencia. Mantener la interfaz actual mientras haya consumidores. |
| [embeddings/secondary_structure/generate_secondary_bert_embeddings.py](../data_pipeline/scripts/embeddings/secondary_structure/generate_secondary_bert_embeddings.py) | A | Generación de las representaciones originales v2. La selección definitiva y el inventario de primarias son las entradas. |
| [find_label_contradictions.py](../data_pipeline/scripts/find_label_contradictions.py) | D | Solapa con el índice histórico y el diagnóstico v2. Confirmar diferencias de semántica y uso desde README o CLI antes de migrar. |
| [global_epitope_labels/build.py](../data_pipeline/scripts/global_epitope_labels/build.py) | A | Construye los índices históricos de procedencia y exporta constantes y utilidades importadas por rebuild y las auditorías. |
| [global_epitope_labels/validate.py](../data_pipeline/scripts/global_epitope_labels/validate.py) | B | Verificación reutilizable de integridad y procedencia. Mantener la interfaz actual mientras haya consumidores. |
| [iedb_download_audit/audit.py](../data_pipeline/scripts/iedb_download_audit/audit.py) | B | Protocolo de validez y dirección de evidencia IEDB. Conserva consumidores en auditorías modificadas, pendientes o pruebas. |
| [iedb_download_audit/impact.py](../data_pipeline/scripts/iedb_download_audit/impact.py) | C | Informe o medición dirigido a una auditoría histórica. Conservar hasta archivar el resultado, datos mínimos y pruebas dependientes. |
| [iedb_download_audit/live.py](../data_pipeline/scripts/iedb_download_audit/live.py) | B | Protocolo de validez y dirección de evidencia IEDB. Conserva consumidores en auditorías modificadas, pendientes o pruebas. |
| [iedb_download_audit/report.py](../data_pipeline/scripts/iedb_download_audit/report.py) | C | Informe o medición dirigido a una auditoría histórica. Conservar hasta archivar el resultado, datos mínimos y pruebas dependientes. |
| [iedb_download_audit/supplement.py](../data_pipeline/scripts/iedb_download_audit/supplement.py) | C | Informe o medición dirigido a una auditoría histórica. Conservar hasta archivar el resultado, datos mínimos y pruebas dependientes. |
| [iedb_modified_audit/audit.py](../data_pipeline/scripts/iedb_modified_audit/audit.py) | B | Protocolo de validez y dirección de evidencia IEDB. Conserva consumidores en auditorías modificadas, pendientes o pruebas. |
| [iedb_modified_audit/blosum.py](../data_pipeline/scripts/iedb_modified_audit/blosum.py) | C | Informe o medición dirigido a una auditoría histórica. Conservar hasta archivar el resultado, datos mínimos y pruebas dependientes. |
| [iedb_modified_audit/impact.py](../data_pipeline/scripts/iedb_modified_audit/impact.py) | C | Informe o medición dirigido a una auditoría histórica. Conservar hasta archivar el resultado, datos mínimos y pruebas dependientes. |
| [iedb_modified_audit/report.py](../data_pipeline/scripts/iedb_modified_audit/report.py) | C | Informe o medición dirigido a una auditoría histórica. Conservar hasta archivar el resultado, datos mínimos y pruebas dependientes. |
| [iedb_pending_audit/audit.py](../data_pipeline/scripts/iedb_pending_audit/audit.py) | B | Protocolo de validez y dirección de evidencia IEDB. Conserva consumidores en auditorías modificadas, pendientes o pruebas. |
| [iedb_pending_audit/impact.py](../data_pipeline/scripts/iedb_pending_audit/impact.py) | C | Informe o medición dirigido a una auditoría histórica. Conservar hasta archivar el resultado, datos mínimos y pruebas dependientes. |
| [iedb_pending_audit/report.py](../data_pipeline/scripts/iedb_pending_audit/report.py) | C | Informe o medición dirigido a una auditoría histórica. Conservar hasta archivar el resultado, datos mínimos y pruebas dependientes. |
| [measure_primary_mutations.py](../data_pipeline/scripts/measure_primary_mutations.py) | C | Informe o medición dirigido a una auditoría histórica. Conservar hasta archivar el resultado, datos mínimos y pruebas dependientes. |
| [rebuild_iedb/final_selection.py](../data_pipeline/scripts/rebuild_iedb/final_selection.py) | A | Construcción, fuentes estructurales y selección reproducible v2. Los Parquet y manifiestos actuales dependen de este contrato. |
| [rebuild_iedb/phase1_report.py](../data_pipeline/scripts/rebuild_iedb/phase1_report.py) | B | Verificación reutilizable de integridad y procedencia. Mantener la interfaz actual mientras haya consumidores. |
| [rebuild_iedb/rebuild.py](../data_pipeline/scripts/rebuild_iedb/rebuild.py) | A | Construcción, fuentes estructurales y selección reproducible v2. Los Parquet y manifiestos actuales dependen de este contrato. |
| [rebuild_iedb/recover_structures.py](../data_pipeline/scripts/rebuild_iedb/recover_structures.py) | A | Construcción, fuentes estructurales y selección reproducible v2. Los Parquet y manifiestos actuales dependen de este contrato. |
| [rebuild_iedb/structures.py](../data_pipeline/scripts/rebuild_iedb/structures.py) | A | Construcción, fuentes estructurales y selección reproducible v2. Los Parquet y manifiestos actuales dependen de este contrato. |
| [secondaryBERT/audit_uniref30_secondary_structure_predictions.py](../data_pipeline/scripts/secondaryBERT/audit_uniref30_secondary_structure_predictions.py) | B | Comprobaciones reutilizables del corpus y modelo SecondaryBERT. |
| [secondaryBERT/build_secondary_mlm_dataset.py](../data_pipeline/scripts/secondaryBERT/build_secondary_mlm_dataset.py) | C | Reconstrucción del corpus auxiliar y de los pesos MLM. Necesario si se quiere reproducir ese entrenamiento, fuera del camino v2 actual. |
| [secondaryBERT/cluster_uniref50_to_uniref30_mmseqs.py](../data_pipeline/scripts/secondaryBERT/cluster_uniref50_to_uniref30_mmseqs.py) | C | Reconstrucción del corpus auxiliar y de los pesos MLM. Necesario si se quiere reproducir ese entrenamiento, fuera del camino v2 actual. |
| [secondaryBERT/create_uniref30_fasta_chunks.py](../data_pipeline/scripts/secondaryBERT/create_uniref30_fasta_chunks.py) | C | Reconstrucción del corpus auxiliar y de los pesos MLM. Necesario si se quiere reproducir ese entrenamiento, fuera del camino v2 actual. |
| [secondaryBERT/predict_uniref30_secondary_structure.py](../data_pipeline/scripts/secondaryBERT/predict_uniref30_secondary_structure.py) | C | Reconstrucción del corpus auxiliar y de los pesos MLM. Necesario si se quiere reproducir ese entrenamiento, fuera del camino v2 actual. |
| [secondaryBERT/train_secondary_mlm.py](../data_pipeline/scripts/secondaryBERT/train_secondary_mlm.py) | C | Reconstrucción del corpus auxiliar y de los pesos MLM. Necesario si se quiere reproducir ese entrenamiento, fuera del camino v2 actual. |
| [secondaryBERT/validate_secondary_mlm.py](../data_pipeline/scripts/secondaryBERT/validate_secondary_mlm.py) | B | Comprobaciones reutilizables del corpus y modelo SecondaryBERT. |
| [secondary_structure_prediction/add_secondary_structure.py](../data_pipeline/scripts/secondary_structure_prediction/add_secondary_structure.py) | A | Predicción y recorte C/H/E del corpus MHC. Mantener separados de la preparación del corpus MLM. |
| [secondary_structure_prediction/predict_secondary_structure.py](../data_pipeline/scripts/secondary_structure_prediction/predict_secondary_structure.py) | A | Predicción y recorte C/H/E del corpus MHC. Mantener separados de la preparación del corpus MLM. |
| [source_audits/exact_embeddings.py](../data_pipeline/scripts/source_audits/exact_embeddings.py) | B | Protocolo de validez y dirección de evidencia IEDB. Conserva consumidores en auditorías modificadas, pendientes o pruebas. |
| [source_audits/investigate_embedding_cases.py](../data_pipeline/scripts/source_audits/investigate_embedding_cases.py) | C | Informe o medición dirigido a una auditoría histórica. Conservar hasta archivar el resultado, datos mínimos y pruebas dependientes. |
| [source_audits/omitted_epitopes.py](../data_pipeline/scripts/source_audits/omitted_epitopes.py) | B | Protocolo de validez y dirección de evidencia IEDB. Conserva consumidores en auditorías modificadas, pendientes o pruebas. |
| [source_audits/recover_epitope_coordinates.py](../data_pipeline/scripts/source_audits/recover_epitope_coordinates.py) | B | Protocolo de validez y dirección de evidencia IEDB. Conserva consumidores en auditorías modificadas, pendientes o pruebas. |


En los archivos inventariados se encontraron **0 grupos de scripts idénticos byte a byte**. Sí se repiten responsabilidades. Hay normalización de URL en clasificación, FASTA, recorte estructural y rebuild. Las implementaciones difieren en tratamiento de esquemas, barras y valores vacíos. Conviene estabilizar primero esos casos mediante pruebas. `archive_inputs.signature` conserva identidad física y tamaño, mientras que `rebuild.signature` usa ruta resuelta, tamaño y mtime. Consolidarlas exige preservar ambos contratos. El único lector NPY archivado compartido por varias auditorías está en `check_sampled_modalities`. Puede extraerse con su validación de SHA-256, manteniendo importaciones de compatibilidad para informes y pruebas.

Dependencias que bloquean retiradas directas:

- `rebuild_iedb/rebuild.py` importa `FAMILIES`, `ROOT`, bloqueo y JSON de `global_epitope_labels/build.py`. Eliminar el módulo rompe el constructor.
- `iedb_modified_audit` importa lógica de `iedb_pending_audit` y de descarga. Los tests comprueban esos contratos.
- `source_audits/investigate_embedding_cases.py` consume `exact_embeddings.OriginalVectors` y la utilidad de lectura de archivos. `recover_epitope_coordinates` consume `omitted_epitopes`. Conservar las dependencias hasta archivar o extraer el código común.
- Los pilotos 3A y 3A.2 importan el generador ProtT5 histórico para repetir su tokenización y pooling. `results/nap_cnb_v2_prott5_audit_3a3/` guarda el lector C++, scripts y evidencias de procedencia. Sus scripts se pueden guardar en un paquete de reproducción junto a sus informes al cerrar la investigación. Los archivos auxiliares deben evaluarse con los hashes y manifiestos correspondientes.
- El generador ProtT5 nuevo carga PyArrow, NumPy y su entorno de inferencia. Sus entradas de datos son la selección y el inventario de primarias. Su cadena de importaciones prescinde del código de pilotos históricos.

## Clasificación de datos

| Clase | Conservar o revisar | Dependencia |
|---|---|---|
| A · originales | `data/used_data/` y referencias completas de IEDB | Reproducir evidencias, estructuras y coordenadas |
| B · definitivos | Parquet fase 1, selección lógica, índice de estructuras recuperadas, futuros shards v2 confirmados y sus manifiestos | Base de la tesis y uniones por claves |
| C · intermedios necesarios | Inventarios exactos primario/estructural, exclusiones, recibos, índices, cachés que enlazan evidencia con secuencias | Reanudación y verificación |
| D · históricos relevantes | Embeddings originales, barajados y concatenados, informes y muestreos de 3A–3A.3, resultados de piloto 3B | Trazabilidad de experimentos y consumidores existentes |
| E · revisar después | Bytecode `__pycache__`, logs transitorios, salidas `.partial` sin recibos, temporales de conteo comprobados regenerables, copia temporal del checkpoint ya cotejada con la persistente | Revisar que no sean de un proceso activo ni la única copia antes de retirar |

La evaluación de redundancia debe conservar la cadena de origen y las pruebas de direcciones. Los bloques SecondaryBERT `chunks_pooled/` son una fuente antigua distinta, con evidencia de colapso en H2-L. La igualdad de tamaño no autoriza una eliminación. Los concatenados históricos mantienen consumidores y se conservan completos.

## Índice de decisiones e informes conservados

| Fase | Resultado enlazado |
|---|---|
| Construcción, etiquetas y estructura inicial | [Informe de fase 1](../results/nap_cnb_v2_phase1/phase1_report.md) |
| Recuperación y límite de ProteinUnet | [Recuperación](../results/nap_cnb_v2_phase1/structure_recovery_report.md) · [Inventario de pendientes](../results/nap_cnb_v2_structure_completion/completion_report.md) |
| Selección estructural y distribución por familia | [Selección definitiva](../results/nap_cnb_v2_final_selection/final_selection_report.md) |
| Cobertura de embeddings | [Auditoría de fuentes](../results/nap_cnb_v2_embedding_audit/embedding_audit_report.md) |
| ProtT5 histórico | [3A](../results/nap_cnb_v2_prott5_audit_3a/prott5_phase_3a_report.md) · [3A.2](../results/nap_cnb_v2_prott5_audit_3a2/prott5_phase_3a2_report.md) · [3A.3](../results/nap_cnb_v2_prott5_audit_3a3/prott5_phase_3a3_report.md) |
| Decisión de regenerar ProtT5 | [Protocolo 3B](nap_cnb_v2_prott5.md) · [Piloto](../results/nap_cnb_v2_prott5/pilot_report.md) |

Para una futura consolidación, conservar informes e inventarios y agrupar scripts experimentales con sus pruebas y referencias. Tras revisar importaciones y consumidores, proponer extracciones pequeñas de utilidades, luego trasladar o retirar C y D por grupos. Cualquier traslado o retirada de scripts, copias históricas o datos queda pendiente de una revisión y autorización separadas.
