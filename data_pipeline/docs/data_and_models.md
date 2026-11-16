# Data provenance, schema and model inventory

All paths are relative to the `lperez_nn/` project root unless stated otherwise. Code and documentation share one Git repository; datasets and model weights are excluded.

## Source data and versions

| Source | Use | Recorded provenance | Version/date coverage |
|---|---|---|---|
| IEDB | Positive linear-peptide MHC and T-cell assays for human and mouse | `mhc_export` and `tcell_export` API exports; merged events retain peptide, coordinates, source and parent IDs | The downloader does not pin a database release or write a download timestamp into the exported schema |
| UniProt / NCBI Protein | Parent protein sequences used to validate epitope coordinates and generate windows | Retrieval CSVs retain `protein_url`, `db`, `id_full`, `id_base`, `resolved_id` and the retrieved sequence | Accession fallback may use a base ID; a database release or retrieval timestamp is not recorded by the script |
| UniRef50 | Protein sequences for secondary-structure MLM pretraining | Input `uniref50.fasta`, MMseqs2 cluster TSV and representative FASTA | The clustering script does not record the source release, acquisition date or original FASTA checksum in a dataset manifest |

These statements describe the provenance captured by the current scripts and inspected manifests. Download dates and exact source releases are not established here; dates in report or archive filenames are processing dates, not evidence of source acquisition. “UniRef30” names the local 30%-identity representative set derived from UniRef50, not an official database release.

The [download](../scripts/data_download/build_iedb_dataset.py), [protein retrieval](../scripts/data_classification/fetch_parent_proteins_fastas.py) and [clustering](../scripts/secondaryBERT/cluster_uniref50_to_uniref30_mmseqs.py) scripts define the queries and transformations. Their current configuration alone does not reproduce a historical upstream snapshot.

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

## Example generation and identifiers

Classification uses one-residue sliding windows of 25 amino acids, after validating epitope coordinates against the parent sequence. A window receives label 1 if it fully contains a recorded positive epitope, otherwise 0. These negatives are not experimentally verified negatives. Several contained epitopes can produce several examples for one physical window.

BLOSUM62 augmentation retains the original sequence plus one highest-scoring alternative substitution per position: 26 rows per valid 25-aa example. Variants inherit the label and the original group's structural embedding; structures are not predicted independently for each mutant.

| Identifier | Meaning and scope |
|---|---|
| `protein_group_id` | Protein ID local to an original species/class/family dataset; not globally unique after mixing datasets |
| Original `group_id` | Classification-example ID within one source dataset, shared by its augmented variants |
| `source_dataset_id` | Source entry in `reorder_manifest.json`, including its original Primary index and Secondary path |
| `source_group_id` | Original group ID before mixing |
| `source_chunk_id`, `source_row_idx_in_chunk` | Original Primary chunk and zero-based row position |
| Shuffled `group_id` | `source_group_id + group_id_offset`, using the offset recorded for that source dataset |
| `chunk_id`, `row_idx_in_chunk` | Physical output location after shuffling; row position is zero-based |

The source-row fields live in the shuffled master CSVs, now retained in verified source archives. The independent training tree contains the copied source-level `reorder_manifest.json` and compact per-chunk `y`, `group_id` and `split_id` arrays, not the full original-row provenance table. Join source data by dataset and identifiers, not by the physical row order of independently generated modalities.

## Stored schema and row order

The completed training dataset has 1,449,852,950 rows in 14,499 chunks of up to 100,000 rows. Features are unnormalized `float32` NPY arrays; column order is `[ProtT5: 0–1023 | SecondaryBERT: 1024–1791]`. For each `chunk_XXXXXX_X.npy`, position `i` corresponds to position `i` in `chunk_metadata/chunk_XXXXXX_y.npy`, `..._group_id.npy` and `..._split_id.npy`.

The shuffle manifest records seed 42, 1,024 buckets, chunk size, source mappings, offsets and final counts. Concatenation preserves shuffled row order. Split IDs are TRAIN=0, VALIDATION=1 and TEST=2; assignment is approximately 80/10/10 by row and label within each physical chunk. Groups and proteins may occur in multiple splits. The MLP uses fixed selected chunks, changes traversal order each epoch and balances TRAIN minibatches without rewriting the stored data.

## Integrity records

| Record or check | Scope |
|---|---|
| `reorder_manifest.json` | Source mappings, shuffle parameters and row/chunk totals; source paths may reflect the original machine |
| `feature_layout.json` and `INCOMPLETE` | Feature dimensions, normalization status and completion state; markers are not standalone integrity proofs |
| Per-chunk `chunk_XXXXXX_X.json` | Concatenated-output SHA-256, byte size and input signature; conversion compares every output value against its source modalities and verifies copied metadata |
| `check_master_split.py` | Split proportions, source-row consistency and agreement between CSVs and metadata |
| `check_secondary_embeddings.py` | Manifest/ID/shape checks, with sampled numerical finiteness and variability checks |
| `*.archive.json` and `ARCHIVED.json` | Per-file original/archive SHA-256 records and completed archive-tree marker; decompressed content is verified before source removal |
| `*.tar.zst.sha256` and `*.verification.json` | Historical raw/intermediate/UniRef archive checksums and records of full GNU tar comparison against original directories |

Checksums establish consistency with recorded local artifacts, not the identity of an unrecorded upstream release. See [source archiving](../scripts/data_archiving/README.md) for restoration. The concatenated training tree is independent of the source archives; those archives are needed to recover detailed source-row provenance.

## Public availability

GitHub contains the pipeline and training code, documentation, environment specifications and [aggregate chunk-label counts](../../reports/README.md). Full datasets, manifests stored inside dataset directories, model weights/tokenizers, fitted scalers, verification records, logs and training outputs remain local and are excluded by `.gitignore`.

A [synthetic example](../../examples/README.md) generates artificial data for loader, normalization and CPU inference checks without the local artifacts.

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
