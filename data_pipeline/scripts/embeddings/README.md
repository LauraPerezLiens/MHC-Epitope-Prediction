# Protein embeddings

Para las primarias originales de NAP-CNB v2, consultar el [pipeline ProtT5 v2 y su piloto](../../../docs/nap_cnb_v2_prott5.md).

Generate float32 features for the [MLP classifier](../../../neural_network/MLP/README.md). Primary embeddings describe augmented amino acid windows; secondary embeddings describe the original structural window shared by a group. Join by dataset and identifiers, not row order.

| Property | ProtT5 | SecondaryBERT |
|---|---|---|
| Input | `classification_*_blosum.csv` | `classification_*_ss.csv` |
| Features per row | 1,024 | 768 |
| Pooling | Mean over attention-mask-valid tokens, including EOS | Mean over 25 biological tokens, excluding CLS/SEP |
| Chunk size | 100,000 | 102,400 |
| Batch size | 32 | 1,024 per GPU |
| Representation | One vector per sequence | One vector per original group |

Both branches preserve `protein_group_id` and `group_id`. Structural features reused for BLOSUM variants describe the original protein; mutant structures are not predicted independently.

## ProtT5

`primary_structure/generate_prott5_embeddings.py` loads `Rostlab/prot_t5_xl_half_uniref50-enc`, pools token embeddings and reuses embeddings for identical sequences within a chunk.

Required columns: `protein_group_id`, `group_id`, `blosum_seq`, `contains_epitope` and `epitope_pos_score`.

Each chunk writes:

| File | Contents |
|---|---|
| `chunk_XXXXXX_X.npy` | `(N, 1024)` features |
| `chunk_XXXXXX_y.npy` | Binary labels |
| `chunk_XXXXXX_pos.npy` | Epitope position scores |
| `chunk_XXXXXX_group_id.npy`, `chunk_XXXXXX_protein_group_id.npy` | Identifiers |
| `chunk_XXXXXX_metadata.csv` | Input columns |
| `chunk_XXXXXX_index.csv` | Chunk/row position, identifiers and label |

`master_index.csv` combines the chunk indexes.

## SecondaryBERT

`secondary_structure/generate_secondary_bert_embeddings.py` validates the saved tokenizer, encodes C/H/E as IDs 5/6/7 and pools the 25 biological positions. It saves `(N, 768)` arrays, not residue-level matrices.

Required columns: `protein_group_id`, `group_id`, `25aa_seq`, `secondary_structure`, `contains_epitope`, `epitope_pos_score`, `protein_url` and `window_start`. Optional columns are preserved in metadata.

When `ss_status` exists, only `ok` rows are retained. Empty structures are skipped. The cleaner uppercases strings, replaces unexpected symbols with C, truncates to 25 states and pads shorter strings with C. It does not strictly reject all malformed inputs. Only the first retained row per `group_id` is embedded.

Output under `classification_*_SecondaryBERT_by_group/`:

| File | Contents |
|---|---|
| `chunks/chunk_XXXXXX_X_ss.npy` | Pooled features |
| `chunks/chunk_XXXXXX_group_id.npy`, `chunks/chunk_XXXXXX_protein_group_id.npy` | Chunk identifiers |
| `group_id.npy`, `protein_group_id.npy` | Global identifiers |
| `index.csv` | Identifiers and `row_idx_in_X_ss` |
| `chunks_manifest.csv` | Chunk IDs, row ranges, counts and array paths |
| `metadata.csv` | Input fields and cleaned structures; omitted with `--no-metadata` |
| `embedding_config.json` | Source, model identity, token mapping, dimensions and generation settings |
| `done.flag` | Completion marker |

The model fingerprint uses configuration contents and weight-file metadata, not a full weight checksum. Resume checks configuration identity and existing chunk shapes/dtypes. `--force` removes selected dataset outputs before regenerating them.

## Run

Commands are run from the `lperez_nn/` project root. Inputs must be under the project’s `data/data_intermediate/` tree. Both generators default to `data/data_input_nn/`, preserving species/class/family directories. The original intermediate datasets are now [archived](../../../data/used_data/README.md).

```bash
python data_pipeline/scripts/embeddings/primary_structure/generate_prott5_embeddings.py   --input data/data_intermediate/human/mhc-I/HLA-A/classification_human_mhc-I_HLA-A_blosum.csv

python data_pipeline/scripts/embeddings/secondary_structure/generate_secondary_bert_embeddings.py   --csv data/data_intermediate/human/mhc-I/HLA-A/classification_human_mhc-I_HLA-A_ss.csv
```

SecondaryBERT defaults to `model/secondary_bert`. Use `--model-dir` to select another model. To discover all configured datasets and distribute chunks across two GPUs:

```bash
torchrun --standalone --nproc_per_node=2   data_pipeline/scripts/embeddings/secondary_structure/generate_secondary_bert_embeddings.py   --batch-size 1024 --chunk-size 102400
```

`--species human` or `--species mouse` restricts discovery. All ranks traverse the same dataset list; chunk `k` belongs to rank `k % world_size`. CSV input is streamed in 100,000-row batches by default; the seen-group-ID set grows with dataset size. CUDA fp16 inference saves float32 arrays through temporary memory-mapped files. CPU execution requires `--allow-cpu`.

## Check structural embeddings

```bash
python data_pipeline/scripts/embeddings/secondary_structure/check_secondary_embeddings.py
```

The checker uses a fixed local output root and expects 11 species/class/family datasets. It checks completion markers, configuration, contiguous manifest ranges, chunk counts, array shape/dtype, and chunk/global ID agreement and ordering. Missing metadata/index CSVs are warnings; legacy `secondary_bert_mlm` model references are rejected.

Finiteness and variability are checked on up to 512 sampled rows per chunk. Generation also checks tokenizer behavior and four contrasting C/H/E patterns. Identical inputs may legitimately produce identical vectors; variability does not establish epitope-prediction quality.

Recorded counts and validation metrics are in the [data and model inventory](../../docs/data_and_models.md).
