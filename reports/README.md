# Data reports

**Empieza aquí:** [Auditoría consolidada, diagnóstico y plan](auditoria_consolidada.md)
reúne qué se auditó, qué se encontró, qué se hizo y qué se propone, con el
inventario de lo que se conserva, se comprime o se retira. Los experimentos
individuales están en [experiments/](experiments/).

[reorder_chunk_label_counts_20261110.csv](reorder_chunk_label_counts_20261110.csv) records label counts before training-time balancing for each historical shuffled chunk.

| Column | Meaning |
|---|---|
| `chunk_id` | Zero-based physical chunk ID |
| `negative`, `positive` | Rows of each class |
| `rows` | Total rows in the chunk |
| `positive_pct` | Percentage of positive rows |

The report covers 14,499 chunks and 1,449,852,950 rows. It contains aggregate counts. Use the local reorder manifest to identify the corresponding dataset. The CSV describes class prevalence before sampling and provides no evaluation metrics or checkpoint identity. Dataset manifests remain with their local datasets; training metrics are separate [results](../results/README.md).

For evaluation protocols and checkpoint interpretation, see [training outputs](../results/README.md). The [technical inventory](../data_pipeline/docs/data_and_models.md) describes certified D1 and planned D2.
