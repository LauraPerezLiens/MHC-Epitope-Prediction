# MLP on Primary and Secondary embeddings

| File | Purpose |
|---|---|
| `dataset.py` | Chunk loading, Secondary lookup by group, minibatches and normalization. |
| `fit_shuffled_scaler.py` | Fit the scaler on all TRAIN chunks; blockwise Primary and sequential Secondary weighted by TRAIN occurrences. |
| `mlp_layernorm_shuffled_ladder100_dualeval.py` | LayerNorm training and STAGE/ALL evaluation. |
| `run_shuffled_pipeline.sh` | Prepare splits, metadata, validation and scaling; does not start training. |
| `run_chunk_ladder100_dualeval.sh` | Train in increments of 100 chunks, for 100 epochs per stage. |
| `../../docs/RESUMEN_EXPERIMENTOS.md` | Experiment history and records of removed outputs. |
| `standardizer_all_train_chunks.npz` | Current scaler fitted on TRAIN. |
| `../../results/` | Training outputs. |

## Current layout

This directory contains the reference implementation. Training outputs go to `../../results/`. The completed scaler is `standardizer_all_train_chunks.npz`; its log is `../../logs/scaler_sequential_20261110.log`.

## Commands from the project root

For a future scaler calculation, when no other scaler is active and the output does not already exist:

```bash
python neural_network/MLP/fit_shuffled_scaler.py \
  --root data/data_input_nn_shuffled \
  --output neural_network/MLP/standardizer_all_train_chunks.npz \
  --block-rows 2048
```

The scaler format is compatible with `ModalityStandardizer`. It uses TRAIN only; each Secondary embedding contributes as many times as its group appears in TRAIN. Counts are temporarily stored on disk without duplicating embeddings. PRIMARY and SECONDARY messages report the two phases.

To train with a completed scaler:

```bash
bash neural_network/MLP/run_chunk_ladder100_dualeval.sh
```

The launcher accepts `DATA_ROOT`, `RESULTS`, `SCALER_PATH`, `PYTHON` and `CUDA_VISIBLE_DEVICES`. The default GPU is 2. TEST STAGE selects the best checkpoint; ALL provides diagnostics. Historical evaluation metrics remain exploratory.

The current loader expects 1,024-column Primary files and separate 768-column Secondary embeddings. It requires adaptation before training on concatenated 1,792-column files.

## Preparation launcher

```bash
bash neural_network/MLP/run_shuffled_pipeline.sh
```

This uses `data_pipeline/scripts/data_splitting/`. When the scaler exists, preparation is skipped and the current split is preserved. For a new dataset, set `DATA_ROOT` and `SCALER_PATH` to new paths. Preparation does not use `.ok` markers.
