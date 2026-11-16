# Data and model inventory

All paths are relative to the `lperez_nn/` project root unless stated otherwise. Code and documentation share one Git repository; datasets and model weights are excluded.

## Local storage

| Path | Contents |
|---|---|
| `data/data_input_nn/` | Original embeddings, now archived as verified `.zst` files |
| `data/data_input_nn_shuffled/` | Shuffled sources and metadata, archived after concatenation |
| `data/data_input_nn_shuffled_concatenate/` | Independent concatenated features and metadata for training |
| `data/used_data/` | Verified raw, intermediate and UniRef50 `.tar.zst` archives |
| `model/unet_c_ensemble/` | ProteinUnet weights |
| `model/secondary_bert/` | SecondaryBERT weights, tokenizer and local validation results |
| `neural_network/MLP/` | Classifier code and local fitted TRAIN scaler |
| `results/` | Local training metrics and checkpoints |
| `logs/` | Local operational logs |
| `reports/` | Data processing and validation reports |

See [data](../../data/README.md) and [archive restoration](../../data/used_data/README.md) before rerunning generation scripts. Historical scripts use `data/data_raw/`, `data/data_intermediate/` and `data/data_uniref50/`; those directories are currently archived. Default data and model paths are resolved from the project location. Existing CLI path options select external storage when needed.

## Dataset artifacts

| Artifact | Producer | Contents |
|---|---|---|
| `merged_unique_events.csv` | `build_iedb_dataset.py` | Deduplicated positive IEDB events |
| Parent FASTA CSVs | `fetch_parent_proteins_fastas.py` | Validated UniProt/NCBI parent sequences |
| `classification_*.csv` | `epitope_classification.py` | Labeled 25-aa examples and identifiers |
| `classification_*_blosum.csv` | `generate_blosum62_variants.py` | Original plus 25 single-substitution variants per 25-aa example |
| `secondary_struct_*.csv` | `predict_secondary_structure.py` | Full-protein C/H/E predictions |
| `classification_*_ss.csv` | `add_secondary_structure.py` | Mapped structural windows and mapping status |
| MLM Parquet splits | `build_secondary_mlm_dataset.py` | Structural sequences for BERT pretraining and evaluation |
| ProtT5 chunks | `generate_prott5_embeddings.py` | `(N_variants, 1024)` float32 features |
| SecondaryBERT chunks | `generate_secondary_bert_embeddings.py` | `(N_groups, 768)` pooled float32 features |
| Concatenated chunks | `concatenate_primary_secondary.py` | `(N_rows, 1792)` unnormalized float32 features with independent metadata |

Human datasets cover MHC-I HLA-A/B/C and MHC-II HLA-DP/DQ/DR. Mouse datasets cover MHC-I H2-D/K/L and MHC-II H2-IA/IE. These labels aggregate families, not individual alleles.

IDs are local to each classification dataset. A window containing multiple epitopes can produce multiple examples and group IDs. The current MLP split allows shared groups and proteins across splits; see [split generation](../scripts/data_splitting/README.md).

## Models

| Model | Role |
|---|---|
| ProteinUnet | TensorFlow/Keras SavedModel (`saved_model.pb`, `variables/`); predicts per-residue C/H/E states |
| SecondaryBERT | BERT MLM with an eight-token vocabulary, hidden size 768, 12 layers, 12 attention heads, intermediate size 3072 and 30 position embeddings |
| `Rostlab/prot_t5_xl_half_uniref50-enc` | ProtT5 encoder/tokenizer loaded through Hugging Face by the primary embedding generator |

SecondaryBERT must preserve uppercase C/H/E with token IDs 5/6/7. The embedding checker rejects references to the legacy `secondary_bert_mlm` directory. See [SecondaryBERT training](../scripts/secondaryBERT/README.md) for tokenizer checks and model output selection.

## Recorded validation

The local `model/secondary_bert/validation_metrics.json` records a run on 100,000 validation proteins, producing 275,119 windows and 1,031,372 masked tokens:

| Metric | Value |
|---|---:|
| MLM loss | 0.255735 |
| Perplexity | 1.291411 |
| Masked-token accuracy | 0.885621 |
| Macro-F1 C/H/E | 0.873589 |
| Original unknown tokens | 0 |
| Predicted non-C/H/E tokens | 0 |
| All synthetic-pattern embeddings identical | false |

These measure reconstruction of predicted structural states, not epitope classification or experimental structure accuracy. The run used a subset of validation, not the test split.

The structural embedding log records 11/11 datasets passing, with 55,763,575 rows in 551 chunks. Numerical finiteness and variability checks sample rows; they do not inspect every float. These logs and weights are local artifacts, not included in GitHub.
