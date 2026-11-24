# Índice de evidencia NAP-CNB

Punto de entrada único a `results/`. Cada fila dice qué demuestra un directorio,
cuánto ocupa y si sigue en uso. Ningún archivo se ha movido: este documento solo
indexa lo que ya existe.

Estado a 23 de noviembre de 2026.

## 1. Los números que importan

Todo lo demás en este índice existe para sostener esta tabla. Estimando: evidencia
global registrada sobre ventanas de 25 aa, 1.792 características en orden
ProtT5 (1.024) + SecondaryBERT (768).

| Experimento | Partición | TEST ROC-AUC | TEST AP | Informe |
|---|---|---:|---:|---|
| E1 · LR | primaria exacta | 0,654641 | 0,375738 | [d1_lr_original_baseline.md](../reports/experiments/d1_lr_original_baseline.md) |
| E2 · MLP 1792-512-128-1 | primaria exacta | 0,680107 | 0,412129 | [d1_mlp_original_baseline.md](../reports/experiments/d1_mlp_original_baseline.md) |
| Histórico · MLP, 14.499 chunks | **por fila** | 0,7955 (época 1) | — | [mlp_experiment_history.md](mlp_experiment_history.md) |

El valor histórico no es comparable: su partición reparte filas, no grupos, y el
87,38 % de los grupos aparece en TRAIN, VALIDATION y TEST a la vez. La diferencia
frente a E2 mide fuga, no capacidad.

En curso (23 nov): ablación por modalidad y repartición por componente de proteína.
Ver [sección 6](#6-en-curso).

## 2. Dataset v2 certificado — cómo se construyó

| Directorio | Qué establece | Tamaño |
|---|---|---:|
| [nap_cnb_v2_phase1](../results/nap_cnb_v2_phase1/phase1_report.md) | Ventanas originales por familia y estructura secundaria base | 1,7G |
| [nap_cnb_v2_structure_recovery](../results/nap_cnb_v2_structure_recovery/report.md) | Recuperación de C/H/E ausente | 2,4M |
| [nap_cnb_v2_structure_completion](../results/nap_cnb_v2_structure_completion/completion_report.md) | Cierre de cobertura estructural al 100 % | 316K |
| [nap_cnb_v2_final_selection](../results/nap_cnb_v2_final_selection/final_selection_report.md) | **Selección definitiva: 49.123.503 ventanas** | 14K |
| [nap_cnb_v2_prott5](../results/nap_cnb_v2_prott5/final_report.md) | 14.530.324 embeddings ProtT5 certificados, 146 shards | 56G |
| [nap_cnb_v2_secondarybert](../results/nap_cnb_v2_secondarybert/secondarybert_report.md) | Embeddings SecondaryBERT, fase 3C | 273M |
| nap_cnb_v2_dataset_views | Vista global D1 y manifiestos de split | 852M |
| [nap_cnb_v2_d1_materialized](../results/nap_cnb_v2_d1_materialized/README.md) | 61 bloques NPY+Parquet de D1, acceso secuencial | 99G |

D1: 15.100.592 representaciones, 14.530.324 primarias únicas, split por primaria
exacta con semilla 42, prevalencia 25,46 %.

## 3. Auditorías — retiradas de `results/`, informes conservados

Las 22 carpetas de auditoría se retiraron el 23 de noviembre de 2026, tras volcar
sus hallazgos en [la auditoría consolidada](../reports/auditoria_consolidada.md).
Liberaron 3,2 GB de artefactos de datos. **Los informes se conservan en
[reports/audits/](../reports/audits/README.md)**, ahora versionados en git.

Las de datos reorientaron el proyecto:

| Informe | Hallazgo |
|---|---|
| [data_contradictions](../reports/audits/data_contradictions.md) | **El 93,53 % de filas positivas tiene una secuencia que aparece como negativa en otro sitio.** 3.494.284 secuencias con ambas etiquetas |
| [group_split_check](../reports/audits/group_split_check_summary.json) | **99,70 % de grupos en varias particiones; 87,38 % en las tres.** La partición histórica no estima generalización |
| [omitted_epitopes_full](../reports/audits/omitted_epitopes_full.md) | 596.063 filas con coincidencia de secuencia sin anotación positiva: ruido en los negativos |
| [primary_mutation_test](../reports/audits/primary_mutation_test.md) | Variantes BLOSUM62 a coseno 0,9883; distancia 6,60 frente a 44,29 entre originales distintos |

Las de embeddings y fuentes salieron limpias. Su valor es haber descartado la
hipótesis de corrupción: **el problema de rendimiento no está en los embeddings.**

| Informe | Alcance |
|---|---|
| [nap_cnb_v2_embedding_audit](../reports/audits/nap_cnb_v2_embedding_audit.md) | **0 de 14.530.324 entradas ProtT5 reutilizables con procedencia verificada** |
| [prott5_audit_3a](../reports/audits/prott5_audit_3a.md) · [3a2](../reports/audits/prott5_audit_3a2.md) · [3a3](../reports/audits/prott5_audit_3a3.md) · [estrategia](../reports/audits/prott5_audit_3a4_estrategia.md) | Procedencia del encoder histórico, sin resolver (L2 mediana 0,00178) |
| [exact_embeddings_sample](../reports/audits/exact_embeddings_sample.md) · [coste](../reports/audits/exact_embeddings_cost.md) · [sampled_modalities](../reports/audits/sampled_modalities_check_summary.json) | Redundancia exacta y coincidencia por muestra |
| [embedding_representation_cases](../reports/audits/embedding_representation_cases.md) | Seis secuencias con representaciones distintas |
| [iedb_download_audit](../reports/audits/iedb_download_audit.md) · [modified](../reports/audits/iedb_modified_audit.md) · [pending](../reports/audits/iedb_pending_evidence.md) · [piloto](../reports/audits/iedb_rebuild_v1_pilot_summary.json) | Descarga, normalización, péptidos modificados y pendientes |
| [epitope_counterfactual](../reports/audits/epitope_counterfactual.md) · [provenance](../reports/audits/epitope_coordinate_provenance.md) · [recovered](../reports/audits/recovered_epitope_coordinates.md) | Coordenadas: origen, recuperación e impacto contrafactual |
| [global_epitope_labels_sample](../reports/audits/global_epitope_labels_sample.md) | Etiqueta global |

## 5. Línea histórica — en cierre

Protocolo exploratorio con partición por fila y selección de checkpoint en TEST
STAGE. Sus cifras son descriptivas de ese protocolo y no estiman generalización.

| Directorio | Contenido | Tamaño |
|---|---|---:|
| mlp_shuffled_concatenated_14499chunks_10epochs | MLP histórica, 10 épocas sobre 14.499 chunks (**en ejecución**) | 1,6G |
| logistic_regression_balanced | LR balanceada histórica | 1,6G |
| logistic_regression_all · logistic_regression_balanced_epoch2_archived | Variantes LR | 1,0M |
| [nap_cnb_v2_blosum_preparation](../results/nap_cnb_v2_blosum_preparation/README.md) · [blosum_materialized](../results/nap_cnb_v2_blosum_materialized/README.md) | Preparación de D2 (aumentación BLOSUM62), **no ejecutado** | 1,0G |
| nap_cnb_v2_d1_experimental · d1_representations · d1_original_manifest · phase1_pilot · phase1_structure | Etapas intermedias superadas por los artefactos de la sección 2 | 507M |

## 6. En curso

| Directorio | Pregunta que responde |
|---|---|
| results/nap_cnb_v2_training/d1_mlp_ablation | ¿Aportan algo las 768 características de SecondaryBERT, o basta ProtT5? |
| [results/nap_cnb_v2_protein_split](../results/nap_cnb_v2_protein_split/split_summary.json) | ¿Cuánto de 0,680 sobrevive a una partición por proteína? |

Resultado ya disponible del segundo: las 28.872 proteínas únicas colapsan en
**16.349 componentes conexas** tras 12.523 fusiones, porque una misma primaria de
25 aa aparece en varias proteínas. Repartir por `parent_accession` habría seguido
filtrando. **16.349 es el número de unidades independientes del estudio**, frente a
los 49.123.503 de ventanas y los 1.449.852.950 de filas aumentadas del histórico.

## 7. Dónde está el espacio

| Ruta | Tamaño | Veredicto |
|---|---:|---|
| `data/data_input_nn_shuffled_concatenate/` | 9,5T | Dataset de trabajo histórico, `.npy` sin comprimir. Regenerable desde el árbol shuffled |
| `data/data_input_nn_shuffled/` | 3,6T | Archivos `.zst` + `reorder_manifest.json`. Regenerable desde `data_input_nn` |
| `data/data_input_nn/` | 3,4T | Embeddings originales `.zst`. Raíz de procedencia |
| `results/nap_cnb_v2_d1_materialized/` | 99G | En uso activo. Única ruta a D1 sin acceso aleatorio |
| `results/nap_cnb_v2_prott5/` | 56G | Almacén certificado. Referencia de los embeddings |
| `data/used_data/` | 31G | Archivos verificados de fuentes |
| Auditorías (22 carpetas) | **0** | Retiradas el 23 nov 2026; informes en [reports/audits/](../reports/audits/README.md) |
| `logs/` | 109K | Irrelevante |

`results/*` y `data/*` están en `.gitignore`: **no tienen historia en git y su
borrado es irreversible.**
