# Data

Local datasets are excluded from Git. Only this README and [used_data/README.md](used_data/README.md) are versioned.

The directories below describe the historical pipeline.

| Directory | Contents |
|---|---|
| `data_input_nn/` | Original embeddings for 11 datasets, archived as verified `.zst` files. |
| `data_input_nn_shuffled/` | Shuffled source embeddings and metadata, archived after concatenation. |
| `data_input_nn_shuffled_concatenate/` | Uncompressed concatenated features and per-chunk labels, group IDs and split IDs used by the MLP. |
| `used_data/` | Archives of raw, intermediate and UniRef50 datasets. |

Historical MLP training reads the concatenated dataset independently of the source archives. Its split is assigned by row and may separate observations from the same group. See [data provenance and schema](../data_pipeline/docs/data_and_models.md) for sources, version coverage, identifiers, feature layout and integrity records. An `INCOMPLETE` marker indicates that preparation has not finished; do not train from that directory until it is removed by the preparation process.

Source archives have per-file `.archive.json` checksum records; `ARCHIVED.json` records tree completion. Verify the archive or restored file against its receipt before reuse. Interrupted tar extraction can leave a partial destination. See [archiving and restoration](../data_pipeline/scripts/data_archiving/README.md).

See the [data pipeline](../data_pipeline/README.md) for preparation and the [MLP documentation](../neural_network/MLP/README.md) for normalization and training. Datasets and the fitted scaler are not included in a clone of this repository.

A [synthetic example](../examples/README.md) generates 100 artificial rows to check loading, normalization and MLP inference without these datasets.

The certified D1 view and split manifests live under `../results/nap_cnb_v2_dataset_views/`. It uses original observations, global `int8` labels and splits assigned by exact primary sequence. This partitioning leaves homology and shared proteins possible across splits. D2 remains planned and requires a link from each variant to its original observation, with explicit label and split inheritance. See the [D1 contract](../data_pipeline/docs/data_and_models.md#certified-d1-and-planned-d2).
