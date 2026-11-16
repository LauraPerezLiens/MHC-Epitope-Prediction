# MHC Epitope Prediction

Research pipeline for epitope classification using protein language models and predicted secondary structure. It combines ProtT5 sequence embeddings with a SecondaryBERT model pretrained on C/H/E structural states, then trains a PyTorch MLP on the resulting features.

Developed as part of doctoral research in computational biology and cancer immunotherapy at the Spanish National Centre for Biotechnology (CNB-CSIC).

## Workflow

```text
Positive IEDB assays → parent proteins → labeled 25-aa windows
  ├── BLOSUM62 variants → ProtT5 (1,024 features)
  └── ProteinUnet predictions → SecondaryBERT (768 features per group)
  → global row shuffle → TRAIN/VALIDATION/TEST splits
  → feature concatenation → TRAIN normalization → MLP training and evaluation
```

SecondaryBERT has a separate pretraining workflow: UniRef50 sequences are clustered at 30% identity, processed with ProteinUnet and used for masked-language modeling.

The data pipeline uses chunked processing, disk-backed statistics, restartable conversion and verified source compression. The current concatenated dataset contains 1,449,852,950 rows in 14,499 chunks, with 1,792 features per row. These are augmented training examples, not independent experimental observations.

## Repository structure

| Directory | Contents |
|---|---|
| [data_pipeline/](data_pipeline/README.md) | Data acquisition, classification, augmentation, structure prediction and embeddings |
| [neural_network/](neural_network/README.md) | Dataset loading, normalization, MLP training and evaluation |
| [docs/](docs/mlp_experiment_history.md) | Experiment history, results and evaluation limitations |
| [env/](env/README.md) | PyTorch and ProteinUnet environment specifications |
| [data/](data/README.md) | Local dataset inventory and archive documentation |
| [model/](model/README.md) | Local pretrained model inventory |
| [reports/](reports/README.md) | Aggregate data preparation reports |
| [results/](results/README.md) | Documentation of local training outputs |

Datasets, fitted scalers, model weights, training outputs and operational logs are excluded from Git. A clone contains code, documentation and the aggregate chunk-label report; it does not include the artifacts needed to run every stage.

## Setup and training

Create the main environment from the project root:

```bash
conda env create -f env/nap_env.yml
conda activate nap_env
```

ProteinUnet inference uses a separate TensorFlow/Keras environment:

```bash
conda env create -f env/proteinunet_env.yml
```

Default data and model paths are resolved from the project location. See [environment setup](env/README.md) and [processing steps](data_pipeline/scripts/README.md) for dependencies, input preparation and commands.

With the concatenated dataset and its fitted TRAIN scaler available, launch training with:

```bash
bash neural_network/MLP/run_chunk_ladder100_dualeval.sh
```

The launcher defaults to 200 epochs over 10 fixed chunks, with TRAIN/TEST STAGE and ALL evaluations at each epoch end. ALL uses a fixed balanced sample across the full chunk pool. See [MLP configuration](neural_network/MLP/README.md) for overrides, checkpoints and resumption.

## Synthetic example

Check chunk loading, metadata, splits, TRAIN normalization and CPU inference without the original data or model weights:

```bash
python examples/synthetic_mlp.py
```

See [the synthetic example](examples/README.md) for its generated schema and checks.

## Tests

Run the CPU regression suite with synthetic inputs:

```bash
python -m unittest discover -s tests -t . -v
```

Archive tests require `zstd`. Two known verification gaps are tracked as expected failures; see [test coverage and limitations](tests/README.md).

## Evaluation scope

A positive window contains a recorded positive epitope; other windows are labeled negative without experimental confirmation. BLOSUM variants inherit the original label and structural features.

The current split is by row and allows shared groups and proteins across splits. TEST STAGE loss selects checkpoints, so the reported metrics are exploratory and do not establish performance on unseen proteins. Results and comparisons are recorded in the [experiment history](docs/mlp_experiment_history.md).
