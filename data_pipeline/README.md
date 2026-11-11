# Data pipeline

> Local layout (11 November 2026): `data_pipeline/` was formerly named `NAP-CNB/`. MLP code is in `../neural_network/MLP/`, data preparation in `scripts/`, and training outputs in `../results/`. The scaler is complete. See `../README.md` for current paths.


NAP-CNB is a research project for antigen and epitope prediction. It prepares immunological datasets, augments protein sequence windows, predicts secondary structure and extracts complementary representations for downstream neural networks.

## Pipeline

```text
IEDB positive MHC / T-cell assays (human and mouse)
    → retrieve and validate parent proteins (UniProt / NCBI)
    → labeled 25-aa classification windows
        ├── BLOSUM62 variants → ProtT5 → (N_variants, 1024)
        └── parent-protein ProteinUnet predictions
              → map structure to original windows
              → corrected SecondaryBERT → (N_groups, 768)
    → downstream epitope model (planned; not included yet)
```

SecondaryBERT has a separate pretraining pipeline:

```text
UniRef50 → MMseqs2 clustering at 30% identity → FASTA chunks
    → ProteinUnet → cleaned C/H/E Parquet datasets
    → BERT masked-language-model pretraining → validation
```

The clustered representative set is called “UniRef30” locally; it is not an official UniRef database release.

## Repository modules

| Directory | Responsibility |
|---|---|
| [data_download](scripts/data_download/README.md) | Download and deduplicate positive IEDB events |
| [data_classification](scripts/data_classification/README.md) | Retrieve parent proteins and label 25-aa windows |
| [data_augmentation](scripts/data_augmentation/README.md) | Original sequence plus one BLOSUM62 substitution per position |
| [secondary_structure_prediction](scripts/secondary_structure_prediction/README.md) | Predict parent-protein structure and map it to classification windows |
| [secondaryBERT](scripts/secondaryBERT/README.md) | UniRef clustering, structure dataset construction, corrected BERT training and validation |
| [embeddings](scripts/embeddings/README.md) | ProtT5 and pooled SecondaryBERT representations; structural embedding checks |
| [data_shuffling](scripts/data_shuffling/README.md) | Global row shuffling and interrupted-run recovery |
| [data_splitting](scripts/data_splitting/README.md) | TRAIN/VALIDATION/TEST assignments, metadata and validation |
| [embedding_concatenation](scripts/embedding_concatenation/README.md) | Raw Primary+Secondary feature concatenation |

See [processing steps](scripts/README.md) for the complete sequence. MLP-specific scaler and launchers live in `../neural_network/MLP/`.

## Local data and models

The root repository is `lperez_nn/`; datasets and model weights are excluded by its `.gitignore`:

```text
lperez_nn/
├── data_pipeline/                 # Data-generation code and documentation
├── data/
│   ├── data_raw/            # IEDB exports and deduplicated events
│   ├── data_intermediate/   # Parent proteins, classification, BLOSUM and SS tables
│   └── data_uniref50/       # Clustering, predictions and MLM Parquet datasets
└── model/                   # ProteinUnet and local SecondaryBERT artifacts

/data/nap/lperez_nn/data/data_input_nn/
                            # Generated embeddings on a separate storage path
```

See [Data and model inventory](docs/data_and_models.md) for file layouts, model roles, storage paths and recorded validation results. Cloning this repository does not download those artifacts. Most scripts use absolute local paths; review their constants and command-line options before running on another machine.

## SecondaryBERT correction and current status

Earlier structural embeddings were reported to be identical for different inputs. The corrected workflow explicitly checks the eight-token BERT vocabulary, preserves uppercase C/H/E and verifies that `C H E C` encodes as `[2, 5, 6, 7, 5, 3]`. Training encodes biological states directly, and embedding generation validates the saved tokenizer before inference and checks output variability.

The current embedding model is `model/secondary_bert`. The embedding checker rejects configurations referencing the legacy `secondary_bert_mlm` directory. The legacy weights and unused experimental models have been removed. Training now defaults to `model/secondary_bert`; select a separate `--output-dir` for experiments to preserve the validated model.

SecondaryBERT now saves **one pooled float32 vector of 768 values per group**, not a `(25, 768)` residue matrix. Existing structural embedding logs report 11/11 datasets passing, totaling 55,763,575 rows in 551 chunks. These are recorded results, not guarantees for a future run.

Implemented: IEDB preparation, classification, BLOSUM augmentation, ProteinUnet prediction, UniRef clustering, MLM pretraining/validation and both embedding generators. Downstream epitope-model training and evaluation remain future work.

## Dataset interpretation

- A positive window fully contains a recorded positive epitope. A negative window lacks such containment; it is not necessarily an experimentally verified negative.
- BLOSUM variants inherit the original labels, an augmentation assumption rather than experimental confirmation.
- `group_id` links variants to an original classification example; `protein_group_id` identifies a protein within a dataset. IDs are local to each species/class/family dataset.
- One physical window may produce multiple examples when it contains multiple epitopes.
- Join embedding branches by dataset and identifiers, not row position. Structural embeddings describe original windows, not independently predicted mutant structures.
- Downstream evaluation should keep proteins and their derived windows/variants in the same split; use protein identity when combining datasets with local IDs.

## Technologies

Python, PyTorch, TensorFlow/Keras, Hugging Face Transformers, ProtT5, ProteinUnet, MMseqs2, NumPy, Pandas, PyArrow, Biopython and scikit-learn. The repository does not currently provide a pinned environment specification.
