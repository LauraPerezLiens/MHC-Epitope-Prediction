# Informes de auditoría conservados

Estos son los informes originales de las auditorías de datos, embeddings,
procedencia y fuentes IEDB. Sus directorios en `results/` se retiraron el
23 de noviembre de 2026 tras volcar los hallazgos en
[la auditoría consolidada](../auditoria_consolidada.md), que es el documento a
leer primero. Lo que queda aquí es el detalle completo de cada una.

Los directorios retirados contenían además los artefactos de datos —CSV, Parquet,
JSONL y matrices— que sumaban 3,2 GB. **Esos datos no se conservaron.** Por eso los
enlaces internos de estos informes a ficheros vecinos de su directorio original ya
no resuelven. Los enlaces a código y documentación del repositorio sí siguen
siendo válidos, porque la profundidad de ruta no cambió.

## Etiquetas y particiones

| Informe | Hallazgo principal |
|---|---|
| [data_contradictions.md](data_contradictions.md) · [resumen](data_contradictions_summary.json) | El 93,53 % de las filas positivas tiene una secuencia que aparece como negativa en otro sitio; 3.494.284 secuencias con ambas etiquetas |
| [group_split_check_summary.json](group_split_check_summary.json) | 99,70 % de los grupos en varias particiones, 87,38 % en las tres; ningún grupo exclusivo de VALIDATION o TEST |
| [global_epitope_labels_sample.md](global_epitope_labels_sample.md) | Construcción y verificación de la etiqueta global |
| [omitted_epitopes_full.md](omitted_epitopes_full.md) · [muestra](omitted_epitopes_sample.md) | 596.063 filas con coincidencia de secuencia sin anotación positiva: ruido en la clase negativa |

## Embeddings y representaciones

| Informe | Hallazgo principal |
|---|---|
| [exact_embeddings_sample.md](exact_embeddings_sample.md) · [coste](exact_embeddings_cost.md) | De 1.203 secuencias repetidas, 1.203 con todos los ProtT5 idénticos |
| [sampled_modalities_check_summary.json](sampled_modalities_check_summary.json) | 33 grupos con coincidencia exacta, diferencia máxima cero |
| [embedding_representation_cases.md](embedding_representation_cases.md) | Seis secuencias con representaciones distintas, caracterizadas |
| [primary_mutation_test.md](primary_mutation_test.md) | Variantes BLOSUM62 a coseno mediano 0,9883 |

## Procedencia de los embeddings históricos

| Informe | Hallazgo principal |
|---|---|
| [nap_cnb_v2_embedding_audit.md](nap_cnb_v2_embedding_audit.md) | **0 de 14.530.324 entradas ProtT5 reutilizables con procedencia verificada**; 1.819.032 SecondaryBERT sí |
| [prott5_audit_3a.md](prott5_audit_3a.md) · [3a2](prott5_audit_3a2.md) · [3a3](prott5_audit_3a3.md) | 0 ejecuciones identificables y 0 configuraciones vinculadas por recibo; H2-D sin procedencia resuelta |
| [prott5_audit_3a4_estrategia.md](prott5_audit_3a4_estrategia.md) | Propuesta de validación que motivó regenerar ProtT5 por completo |

## Fuentes IEDB y coordenadas

| Informe | Hallazgo principal |
|---|---|
| [iedb_download_audit.md](iedb_download_audit.md) | 1.985.260 registros; la reproducción A coincide exactamente con las claves de los 948.344 eventos históricos |
| [iedb_modified_audit.md](iedb_modified_audit.md) | 147.985 registros modificados y 81.679 esqueletos lineales; la normalización histórica descartaba la modificación |
| [iedb_pending_evidence.md](iedb_pending_evidence.md) | 44.907 grupos pendientes; 253 sin esqueleto y 254 sin intervalo verificado |
| [iedb_rebuild_v1_pilot_summary.json](iedb_rebuild_v1_pilot_summary.json) · [config](iedb_rebuild_v1_pilot_config.json) | Piloto de reconstrucción v1 |
| [epitope_coordinate_provenance.md](epitope_coordinate_provenance.md) | Origen y fiabilidad de las coordenadas |
| [recovered_epitope_coordinates.md](recovered_epitope_coordinates.md) | De 102.654 eventos, 102.420 con una única ocurrencia exacta |
| [epitope_counterfactual.md](epitope_counterfactual.md) · [reproducción](epitope_counterfactual_reproduccion.md) | 92.623 eventos recuperados (90,23 %); 10.031 sin resolver |
