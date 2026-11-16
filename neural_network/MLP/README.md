# MLP classifier

Binary classifier using 1,024 ProtT5 and 768 SecondaryBERT features. The architecture is `1792 → 512 → 128 → 1`, with LayerNorm, ReLU and dropout 0.30. Training uses BCEWithLogitsLoss and AdamW.

| File | Purpose |
|---|---|
| `dataset.py` | Chunk loading, metadata, modality lookup, sampling and normalization |
| `fit_shuffled_scaler.py` | Fit TRAIN statistics with sequential Secondary reads and disk-backed group counts |
| `mlp_layernorm_shuffled_ladder100_dualeval.py` | Training, fixed STAGE/ALL evaluation and checkpointing |
| `run_chunk_ladder100_dualeval.sh` | Training launcher and optional incremental chunk stages |
| `run_shuffled_pipeline.sh` | Validate existing preparation and fit only a missing scaler; does not start training |
| `check_preparation.py` | Read-only checks of existing splits, metadata, feature dimensions and scaler manifest |

## Train

From the project root, activate `nap_env` and use a completed concatenated dataset and its fitted scaler:

```bash
conda activate nap_env
bash neural_network/MLP/run_chunk_ladder100_dualeval.sh
```

| Setting | Launcher default |
|---|---|
| Dataset | `data/data_input_nn_shuffled_concatenate/` |
| Scaler | `neural_network/MLP/standardizer_all_train_chunks.npz` |
| Epochs / selected chunks | 200 / 10 |
| Batch size | 8,192, exactly 50/50 |
| Seed / GPU | 42 / 2, single GPU |
| Learning rate / weight decay | 0.001 / 0.0001 |
| Cosine warm restarts | T0=20, Tmult=1, minimum LR=0.00001 |
| Evaluation | Once per epoch; 1,024-row batches |
| Outputs | `results/mlp_shuffled_concatenated_10chunks_200epochs_20261116/` |

The selected chunks stay fixed; traversal order changes deterministically each epoch. Both modalities are standardized with the precomputed TRAIN scaler. Training reads concatenated features and metadata without opening source archives. An `INCOMPLETE` marker prevents training from unfinished data.

Override `DATA_ROOT`, `SCALER_PATH`, `RESULTS`, `PYTHON`, `CUDA_VISIBLE_DEVICES`, `EPOCHS`, `STEP`, `FINAL_CHUNKS` or `EVAL_EVERY` as environment variables. `PYTHON` defaults to `python` from the activated environment. `STEP` controls optional increasing chunk stages; later stages load the previous stage's best weights. The filenames retain `ladder100` for compatibility; stage size is configurable.

## Evaluation and checkpoints

TRAIN ONLINE reports metrics during chunk updates. TRAIN/TEST STAGE evaluate fixed 50/50 samples from the selected chunks; TRAIN/TEST ALL use fixed 50/50 samples drawn across the full chunk pool. The target is 29,006 rows per class, subject to available rows. ALL does not evaluate every dataset row. Set `EVAL_EVERY=chunk` for evaluation after each chunk.

The current experiment is exploratory: its purpose is to check that the network learns and the training pipeline works. TEST STAGE loss intentionally selects the best checkpoint; TRAIN, TEST STAGE and ALL monitor training behavior. ALL is diagnostic and no early stopping is used. Row-based partitions and this selection policy remain unchanged. These metrics are not a definitive evaluation on unseen proteins.

A future, separate generalization study may use VALIDATION for selection, a final independent TEST, group/protein partitions and external predictors. Those protocols are not implemented or applied to current or historical experiments.

Each stage writes `run.log`, JSONL histories and best/last checkpoints. Intra-epoch recovery checkpoints are saved every 100 chunks; for the 10-chunk run, recovery is from the last completed epoch. Rerunning the launcher resumes available checkpoints or skips completed stages. Use a new `RESULTS` directory for an independent experiment.

## Prepare a new scaler

`fit_shuffled_scaler.py` requires prepared, uncompressed Primary files, metadata and a separate Secondary store. It is not a scaler fitter for the independent concatenated-only tree. The current sources are [archived](../../data/README.md); the current fitted scaler is reused for training.

For a new prepared dataset, with an unused output path:

```bash
python neural_network/MLP/fit_shuffled_scaler.py   --root data/data_input_nn_shuffled_new   --output neural_network/MLP/standardizer_new.npz --block-rows 2048
```

Statistics use every TRAIN occurrence without class balancing. Secondary vectors are weighted by their group's TRAIN occurrence count. The output scaler is never overwritten.

`run_shuffled_pipeline.sh` never creates splits or metadata and never uses `--force`. Missing/invalid preparation stops the launcher with an error. It validates the existing files read-only and fits only a missing scaler from separate modalities. A valid existing scaler is retained and checked against the chunk manifest. Concatenated-only inputs require their existing scaler and use compact split arrays; they do not require source CSVs. The launcher does not start training.

Prepare new partitions/metadata explicitly through the [data pipeline](../../data_pipeline/scripts/data_splitting/README.md) before using the launcher with new `DATA_ROOT` and `SCALER_PATH` values. Do not run preparation against an active dataset.

Datasets, scalers and training outputs are excluded from Git. See the [experiment history](../../docs/mlp_experiment_history.md) for earlier runs and the [data pipeline](../../data_pipeline/README.md) for feature preparation.
