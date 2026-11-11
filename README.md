# lperez_nn

Workspace for acquiring datasets, generating embeddings and training the MLP classifier.

| Directory | Contents |
|---|---|
| `data_pipeline/` | Data acquisition, classification, augmentation, secondary structure and embeddings. |
| `neural_network/MLP/` | Dataset loader, scaler and model training. |
| `data/` | Datasets and embeddings. Paths are preserved because indices reference them. |
| `model/` | SecondaryBERT and ProteinUnet weights. |
| `results/` | Training metrics and checkpoints. |
| `logs/` | Operational logs. |
| `reports/` | Per-chunk label counts. |
| `docs/` | MLP experiment history in `RESUMEN_EXPERIMENTOS.md`. |
| `env/` | Conda environment specification. |

## Current preparation

The completed scaler is `neural_network/MLP/standardizer_all_train_chunks.npz`. Its log is `logs/scaler_sequential_20261110.log`. The old scaler and preparation markers have been removed.

Concatenation writes to `data/data_input_nn_shuffled_concatenated/`. Do not use that output while `INCOMPLETE` exists. Preparation does not start training automatically.

## Environment and commands

```bash
conda env create -f env/nap_env.yml
conda activate nap_env
```

See [data processing steps](data_pipeline/scripts/README.md) and [MLP instructions](neural_network/MLP/README.md).

`lperez_nn/` is the only Git repository. Its root `.gitignore` excludes datasets, weights, results, logs and local files. The former nested repositories were removed; their histories are backed up outside this project. No remote is configured.
