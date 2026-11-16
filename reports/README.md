# Data reports

[reorder_chunk_label_counts_20261110.csv](reorder_chunk_label_counts_20261110.csv) records label counts before training-time balancing for each shuffled chunk.

| Column | Meaning |
|---|---|
| `chunk_id` | Zero-based physical chunk ID |
| `negative`, `positive` | Rows of each class |
| `rows` | Total rows in the chunk |
| `positive_pct` | Percentage of positive rows |

The report covers 14,499 chunks and 1,449,852,950 rows. It contains aggregate counts, not sequences or embeddings. Dataset manifests remain with their local datasets; training metrics are separate [results](../results/README.md).
