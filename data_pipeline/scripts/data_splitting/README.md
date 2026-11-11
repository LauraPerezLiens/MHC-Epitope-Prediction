# Data splitting and metadata

Assign TRAIN/VALIDATION/TEST rows, prepare compact metadata and validate the dataset. Run from the `lperez_nn/` root with `nap_env` activated.

The current dataset already has validated splits, metadata and a fitted scaler. These instructions prepare a new dataset. Changing its split requires recalculating the corresponding scaler.

## 1. Generate splits

```bash
python data_pipeline/scripts/data_splitting/split_data.py \
  --root data/data_input_nn_shuffled_new --seed 42
```

Generates `master_split.csv` from `master_index.csv`. Assigns approximately 80/10/10 by row, stratified by label within each chunk: TRAIN=0, VALIDATION=1 and TEST=2. Groups and proteins can appear in multiple splits.

## 2. Generate compact metadata

```bash
python data_pipeline/scripts/data_splitting/prepare_chunk_metadata.py \
  --root data/data_input_nn_shuffled_new
```

Generates the per-chunk arrays consumed by the loader. `--force` regenerates metadata without changing split assignments.

## 3. Validate

```bash
python data_pipeline/scripts/data_splitting/check_master_split.py \
  --root data/data_input_nn_shuffled_new
```

Checks integrity, split proportions and consistency between CSV and arrays. This operational validation was used on the current dataset.

## 4. Calculate the scaler or concatenate

The scaler and preparation launcher belong to the [MLP module](../../../neural_network/MLP/README.md). To concatenate modalities, follow [embedding_concatenation](../embedding_concatenation/README.md). Keep inputs unchanged while another process uses them.
