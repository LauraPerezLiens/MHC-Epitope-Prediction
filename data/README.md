# Data

Local datasets are excluded from Git. Only this README and [used_data/README.md](used_data/README.md) are versioned.

| Directory | Contents |
|---|---|
| `data_input_nn/` | Original embeddings for 11 datasets, archived as verified `.zst` files. |
| `data_input_nn_shuffled/` | Shuffled source embeddings and metadata, archived after concatenation. |
| `data_input_nn_shuffled_concatenate/` | Uncompressed concatenated features and per-chunk labels, group IDs and split IDs used by the MLP. |
| `used_data/` | Archives of raw, intermediate and UniRef50 datasets. |

The concatenated dataset contains 1,449,852,950 rows in 14,499 chunks. Each row has 1,792 unnormalized `float32` features: 1,024 from ProtT5 and 768 from SecondaryBERT. Training uses this dataset independently of the source archives. An `INCOMPLETE` marker indicates that preparation has not finished; do not train from that directory until it is removed by the preparation process.

Source archives have per-file `.archive.json` checksum records; `ARCHIVED.json` marks a completed archive tree. See [archiving and restoration](../data_pipeline/scripts/data_archiving/README.md).

See the [data pipeline](../data_pipeline/README.md) for preparation and the [MLP documentation](../neural_network/MLP/README.md) for normalization and training. Datasets and the fitted scaler are not included in a clone of this repository.
