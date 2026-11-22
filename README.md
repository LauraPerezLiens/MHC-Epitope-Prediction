# MHC Epitope Prediction

Research pipeline for epitope classification using protein language models and predicted secondary structure. It combines ProtT5 sequence embeddings with a SecondaryBERT model pretrained on C/H/E structural states, then trains a PyTorch MLP on the resulting features.

Developed as part of doctoral research in computational biology and cancer immunotherapy at the Spanish National Centre for Biotechnology (CNB-CSIC).

## NAP-CNB v2 status

Use the metadata-only interface to inspect the published v2 selection, embeddings, dataset views, splits and D1.

```bash
python -B -m data_pipeline.nap_cnb_v2 --help
python -B -m data_pipeline.nap_cnb_v2 status
python -B -m data_pipeline.nap_cnb_v2 --root /path/to/repository status --json
```

The default repository root is derived from the module location. `status --root PATH` also accepts an explicit root after the subcommand. From another working directory, make the code repository available on `PYTHONPATH`. The `-B` flag prevents Python from creating bytecode caches during module startup.

| State | Meaning |
|---|---|
| `CERTIFIED` | The lightweight checks passed and prior certification evidence was found. |
| `PRESENT` | The artifact and its metadata are present, with insufficient certification evidence. |
| `MISSING` | A required artifact or reference is absent. |
| `INCONSISTENT` | Accessible metadata disagrees or violates its contract. |
| `UNKNOWN` | The bounded checks could not determine the state. |
| `NOT AVAILABLE` | Outside the current release. D2 is optional and is not built. |

Exit codes are `0` for a completed query without required-component errors, `1` for a required component that is missing, inconsistent or unknown, and `2` for invalid arguments, an invalid root or a query-level failure. Results describe file presence and prior evidence. The command does not run full integrity checks, inspect embedding matrices or start pipeline jobs. [Current data contracts](docs/nap_cnb_v2_dataset_organization.md)

### Quick contract checks

```bash
python -B -m data_pipeline.nap_cnb_v2 validate-selection
python -B -m data_pipeline.nap_cnb_v2 validate-datasets
python -B -m data_pipeline.nap_cnb_v2 validate-splits
python -B -m data_pipeline.nap_cnb_v2 validate-d1 --json
```

All four commands accept `--root` before or after the subcommand and `--json`. `PASS` means the required quick checks passed. `FAIL` indicates a missing reference or inconsistent metadata. `INCOMPLETE` means a required check could not finish. `SKIPPED` identifies checks outside this mode. Exit codes are `0` for PASS, `1` for FAIL or INCOMPLETE, and `2` for argument or startup errors.

Dataset and split checks use the existing PyArrow environment to decode footer bytes only, with a 1 MiB cap per footer. Signature checks read individual small files up to 256 KiB. Larger payloads, row-level joins, assignment regeneration and embedding integrity checks are outside the quick commands.

### Specialized quick checks

```bash
python -B -m data_pipeline.nap_cnb_v2 validate-prott5
python -B -m data_pipeline.nap_cnb_v2 validate-secondarybert
python -B -m data_pipeline.nap_cnb_v2 validate-structures
```

These commands honor the same `--root`, `--json` and exit codes. ProtT5 checks inventory footers, NPY headers and coverage of recorded batch receipts. SecondaryBERT checks certified category counts, inventory footers, catalog schemas, historical paths and receipts, and one new reference. Structures compares overlay and exclusion footers against the selection and recovery evidence. Certified SQLite catalogs are opened in immutable read-only mode after checking closure evidence, journal format and absence of sidecars. A catalog with sidecars or a changing snapshot is reported as `INCOMPLETE`. The commands do not read vector payloads, decompress historical blocks or recheck coordinates.

### Training preflight

`python -B -m data_pipeline.nap_cnb_v2 train --model lr --data original --label global --dry-run` resolves dataset metadata, feature references, splits and the selected historical profile. The v2 selector supports balanced LR and balanced MLP. The explicit engine hook uses balanced TRAIN and natural-prevalence VALIDATION and TEST. Launching from the CLI is disabled and both full TRAIN scalers are pending. [Training guide and compatibility matrix](docs/NAP_CNB_v2_training_guide.md)

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

Archive tests require `zstd`. [GitHub Actions](.github/workflows/cpu-checks.yml) is configured to run CPU tests, the synthetic example, syntax checks and focused Ruff checks in an independent minimal environment. See [test coverage](tests/README.md) and [local CI setup](env/README.md#cpu-tests-and-ci).

## Evaluation scope

A positive window contains a recorded positive epitope; other windows are labeled negative without experimental confirmation. BLOSUM variants inherit the original label and structural features.

**Current phase — exploratory experiments.** The objective is to check that the network learns and the training pipeline works with augmented data. Existing row-based splits, TRAIN/TEST STAGE/ALL monitoring and checkpoint selection by TEST STAGE are intentional and remain unchanged. Shared proteins/groups and checkpoint selection mean these results are not definitive generalization metrics.

**Future phase — generalization evaluation.** A separate study may use VALIDATION for checkpoint selection, a final independent TEST, group/protein holdouts and comparisons with external predictors. These are future protocols, not changes to the current experiment. Results and historical comparisons remain in the [experiment history](docs/mlp_experiment_history.md).
