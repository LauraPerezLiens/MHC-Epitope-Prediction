# Local data and model inventory

This documentation belongs to the Git repository `lperez_nn/data_pipeline/`; a separate local repository also exists in `lperez_nn/data/`. The sibling `data/` and `model/` directories and the external embedding storage are not included when cloning GitHub. This page describes their role without committing large datasets or weights. Paths below reflect the current local configuration, not portable installation defaults.

## Storage layout (updated 10 November 2026)

```text
/home/nap/data/lperez_nn/
├── data/
│   ├── data_input_nn/              # Original Primary and Secondary embeddings
│   ├── data_input_nn_shuffled/     # Mixed rows, splits, metadata and provenance
│   ├── used_data/                  # Verified compressed raw/intermediate/UniRef data
│   ├── NN/Multilayer_Percepton/    # Preserved temporarily for the active scaler
│   └── scaler_sequential_20261110.log  # Active log, retained in place
├── neural_network/MLP/             # Current MLP code, historical summary, results link
├── scripts/                        # Shuffle, split, metadata, validation, concatenation
├── model/
│   ├── unet_c_ensemble/
│   └── secondary_bert/
├── logs/                           # Closed logs and link to the active scaler log
├── reports/                        # Counts and reorganization inventory
├── env/nap_env.yml
├── docs/                           # Previous local documentation
└── data_pipeline/                        # This repository
```

The raw, intermediate and UniRef folders were compressed, compared in full with
their originals, and their originals removed on 10 November 2026. Archives are in
`data/used_data/`; its README explains verification and restoration. Original
names and paths are restored before rerunning older generation scripts. The
archives occupy about 30 GiB rather than about 55 GiB unpacked.

The original embedding trees have not moved. The merged Secondary manifest uses
absolute references into `data/data_input_nn/`; keep these inputs available.
`neural_network/MLP/results/chunk_ladder100_mixed_shuffled_20261110` links to the
unchanged output directory of the currently running scaler. The active source
files and log remain at their original locations. See the workspace-root README
for transition details. No datasets or model weights are duplicated by these links.

Both `data_pipeline/.git` and `data/.git` remain in place as independent repositories.
New sibling workspace folders are not automatically tracked by either repository;
no Git history or index was moved during this reorganization.

## Dataset roles

| Artifact | Producer | Purpose |
|---|---|---|
| `merged_unique_events.csv` | `build_iedb_dataset.py` | Deduplicated positive IEDB events |
| Parent FASTA CSVs | `fetch_parent_proteins_fastas.py` | Validated parent sequences from UniProt/NCBI |
| `classification_*.csv` | `epitope_classification.py` | 25-aa labeled examples with protein/window IDs |
| `classification_*_blosum.csv` | `generate_blosum62_variants.py` | Original plus 25 single-substitution variants for each 25-aa example |
| `secondary_struct_*.csv` | `predict_secondary_structure.py` | Full-protein predicted C/H/E strings |
| `classification_*_ss.csv` | `add_secondary_structure.py` | Original examples with mapped structures and mapping status |
| MLM Parquet splits | `build_secondary_mlm_dataset.py` | Cleaned structural sequences for BERT training and evaluation |
| ProtT5 chunks | `generate_prott5_embeddings.py` | `(N_variants, 1024)` float32 features, labels and IDs |
| SecondaryBERT chunks | `generate_secondary_bert_embeddings.py` | `(N_groups, 768)` float32 pooled structural features |

Human sets cover MHC-I HLA-A/B/C and MHC-II HLA-DP/DQ/DR. Mouse sets cover MHC-I H2-D/K/L and MHC-II H2-IA/IE. These directory labels aggregate families; they do not identify an individual allele.

IDs are local to each classification dataset. A physical window containing multiple epitopes can yield multiple labeled examples and group IDs. Preserve dataset identity when joining artifacts. The current MLP split is intentionally by row and can share groups/proteins across splits; it does not measure generalization to unseen groups or proteins.

## Models

| Artifact | Role and current use |
|---|---|
| `model/unet_c_ensemble/` | TensorFlow/Keras ProteinUnet SavedModel (`saved_model.pb` and `variables/`); predicts per-residue C/H/E from amino acids |
| `model/secondary_bert/` | Corrected model used by default for structural embeddings and validation; BERT MLM weights/configuration and saved tokenizer; includes local `validation_metrics.json` |
| `model/secondary_bert_mlm/` (removed) | Legacy weights/checkpoint removed during cleanup; historical references remain rejected by the embedding checker |
| `secondary_bert_test`, `secondary_bert_test_64/128/256`, `secondary_bert_final_test`, `secondary_bert_optimized_test` (removed) | Unused experimental artifacts removed during cleanup |
| `Rostlab/prot_t5_xl_half_uniref50-enc` | ProtT5 encoder/tokenizer loaded through Hugging Face by the primary embedding script; not a dedicated model directory in this inventory |

The corrected SecondaryBERT has vocabulary size 8, hidden size 768, 12 layers, 12 attention heads, intermediate size 3072 and 30 position embeddings. Its tokenizer must preserve uppercase C/H/E with IDs 5/6/7. See [training and validation](../scripts/secondaryBERT/README.md) for the correction and explicit output-directory selection.

## Recorded validation results

The saved `model/secondary_bert/validation_metrics.json` reports evaluation on 100,000 validation proteins, yielding 275,119 windows and 1,031,372 masked tokens:

| Metric | Recorded value |
|---|---:|
| MLM loss | 0.255735 |
| Perplexity | 1.291411 |
| Masked-token accuracy | 0.885621 |
| Macro-F1 C/H/E | 0.873589 |
| Original unknown tokens | 0 |
| Predicted non-C/H/E tokens | 0 |
| All synthetic-pattern embeddings identical | false |

These evaluate reconstruction of predicted structural states, not biological epitope classification or experimental structure accuracy. This was a limited validation run, not the full test split.

The structural embedding log reports all 11 datasets passing, with 55,763,575 rows in 551 chunks. The manifests and completion flags were also present during review. Numerical checks in the checker are sampled; the result is not an exhaustive scan of every float or proof of downstream model performance.

## Reproducing the workflow elsewhere

Clone the code, provide source data and ProteinUnet weights, and review path constants/CLI options before running the module workflows. There is no automatic artifact downloader or pinned environment file in this repository. Existing local weights, caches, logs and data are not supplied by GitHub. Keep a matching tokenizer/configuration with each BERT checkpoint and validate it before regenerating structural embeddings.
