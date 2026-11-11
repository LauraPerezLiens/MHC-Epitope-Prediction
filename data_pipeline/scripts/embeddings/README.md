# embeddings

## Overview

This module generates **feature representations of protein sequences** for downstream neural network models.

Two complementary embedding strategies are implemented:

- **Primary structure embeddings** → amino acid sequence embeddings generated with ProtT5
- **Secondary structure embeddings** → secondary structure embeddings generated with SecondaryBERT

Both embedding types preserve the relationship between proteins, windows and labels through `protein_group_id` and `group_id`, allowing complete traceability throughout the pipeline.

---

## Pipeline role

```text
classification windows
    ├── BLOSUM augmentation → ProtT5 embeddings
    └── mapped ProteinUnet structure → SecondaryBERT embeddings
        → downstream model training (planned)
```

**Input**

```text
classification_*_blosum.csv
classification_*_ss.csv
```

**Output**

```text
ProtT5 embeddings
SecondaryBERT embeddings
```

---

## Structure

```text
embeddings/
├── primary_structure/
│   └── generate_prott5_embeddings.py
└── secondary_structure/
    ├── generate_secondary_bert_embeddings.py
    └── check_secondary_embeddings.py
```

---

# Primary structure embeddings

## Script

### `generate_prott5_embeddings.py`

### Description

Generates sequence-level embeddings from amino acid windows using the ProtT5 protein language model.

The script:

1. Loads augmented sequence windows from classification datasets.
2. Cleans protein sequences and converts them to the ProtT5 token format.
3. Computes ProtT5 token embeddings.
4. Applies mean pooling across sequence positions.
5. Saves embeddings, labels and metadata in chunked files.

To reduce computation, identical sequences within a chunk are embedded only once and reused through sequence factorization.

---

### Input

```text
classification_{species}_{class}_{haplotype}_blosum.csv
```

Required columns:

```text
protein_group_id
group_id
blosum_seq
contains_epitope
epitope_pos_score
```

---

### Embedding details

| Parameter | Value |
|------------|---------|
| Model | Rostlab/prot_t5_xl_half_uniref50-enc |
| Embedding size | 1024 |
| Pooling | Mean pooling |
| Maximum length | 30 |
| Chunk size | 100,000 rows |
| Batch size | 32 |

Output shape:

```text
(N, 1024)
```

One embedding vector per sequence window.

---

### Output

For each chunk:

```text
chunk_000000_X.npy
chunk_000000_y.npy
chunk_000000_pos.npy
chunk_000000_group_id.npy
chunk_000000_protein_group_id.npy
chunk_000000_metadata.csv
chunk_000000_index.csv
```

Global index:

```text
master_index.csv
```

---

### Output files

#### Embeddings

```text
chunk_XXXXXX_X.npy
```

Shape:

```text
(N, 1024)
```

---

#### Labels

```text
chunk_XXXXXX_y.npy
```

Binary epitope labels.

---

#### Positional score

```text
chunk_XXXXXX_pos.npy
```

Epitope position score.

---

#### Group identifiers

```text
chunk_XXXXXX_group_id.npy
chunk_XXXXXX_protein_group_id.npy
```

Used to track windows and proteins across the pipeline.

---

#### Metadata

```text
chunk_XXXXXX_metadata.csv
```

Contains:

```text
protein_group_id
group_id
blosum_seq
contains_epitope
epitope_pos_score
```

---

#### Index

```text
chunk_XXXXXX_index.csv
```

Maps:

```text
chunk_id
row_idx_in_chunk
protein_group_id
group_id
y
```

---

# Secondary structure embeddings

## Script

### `generate_secondary_bert_embeddings.py`

### Description

Generates contextual embeddings from predicted secondary structure sequences using the pretrained SecondaryBERT model.

The script:

1. Loads secondary structure annotations.
2. Keeps only windows with valid secondary structure predictions (`ss_status == ok`).
3. Cleans and normalizes C/H/E sequences.
4. Encodes C/H/E directly as IDs 5/6/7 after validating the saved tokenizer.
5. Computes contextual embeddings and averages the 25 biological positions, excluding `[CLS]` and `[SEP]`.
6. Saves one float32 embedding per `group_id`, with identifiers and manifests; metadata is written unless `--no-metadata` is selected.

The saved representation is a pooled window vector. Token-level contextualization occurs inside BERT, but the saved array does not retain a separate vector for each residue.

---

### Input

```text
classification_{species}_{class}_{haplotype}_ss.csv
```

Required columns:

```text
protein_group_id
group_id
25aa_seq
secondary_structure
contains_epitope
epitope_pos_score
protein_url
window_start
```

Optional columns:

```text
selected_epitope
protein_found
sequence_match
ss_status
```

---

### Filtering

If present:

```text
ss_status == "ok"
```

When `ss_status` is present, only `ok` rows are used. Empty structures are skipped. The current cleaner uppercases the string, replaces unexpected symbols with `C`, truncates strings longer than 25 and pads shorter strings with `C`; this is normalization, not strict rejection of every malformed input. Only the first retained row per `group_id` is embedded.

---

### Embedding details

| Parameter | Value |
|------------|---------|
| Model | SecondaryBERT |
| Hidden size | 768 |
| Window size | 25 |
| Maximum length | 30 |
| Chunk size | 102,400 rows |
| Batch size per GPU | 1024 |
| Pooling | Mean over 25 biological tokens |

Output shape:

```text
(N, 768)
```

Each original classification group receives one 768-dimensional vector.

---

### Output structure

```text
classification_*_SecondaryBERT_by_group/
│
├── metadata.csv                 # omitted with --no-metadata
├── index.csv
├── protein_group_id.npy
├── group_id.npy
├── chunks_manifest.csv
├── embedding_config.json
├── done.flag
│
└── chunks/
    ├── chunk_000000_X_ss.npy
    ├── chunk_000000_protein_group_id.npy
    ├── chunk_000000_group_id.npy
    ├── chunk_000001_X_ss.npy
    └── ...
```

---

### Metadata

```text
metadata.csv
```

Contains:

```text
protein_group_id
group_id
25aa_seq
secondary_structure
clean_ss
contains_epitope
epitope_pos_score
protein_url
window_start
```

plus any optional columns present in the original dataset.

---

### Index

```text
index.csv
```

Maps:

```text
protein_group_id
group_id
row_idx_in_X_ss
```

allowing reconstruction of the relationship between embeddings and original windows.

---

### Chunk manifest

```text
chunks_manifest.csv
```

Contains:

```text
chunk_id
start
end
n_rows
x_file
protein_group_id_file
group_id_file
```

and allows efficient loading of large embedding collections.

---

### Configuration

```text
embedding_config.json
```

Stores:

```text
source_csv
chunk_size
batch_size
hidden_size
window_size
model_dir
```

for reproducibility. The current configuration also records `config_version`, `total_rows`, `dtype`, `pooling`, `output_shape_per_row`, `model_fingerprint`, ID column names and the token mapping. The fingerprint uses configuration contents and weight-file metadata; it is not a full checksum of the weights.

---

## Key differences

| Feature | Primary (ProtT5) | Secondary (SecondaryBERT) |
|----------|----------|----------|
| Input | Amino acid sequence | Secondary structure sequence |
| Tokens | Amino acids | C / H / E |
| Model | ProtT5 | SecondaryBERT |
| Output shape per row | (1024,) | (768,) |
| Pooling | Attention-mask mean pooling | Mean over 25 biological tokens |
| Saves separate residue vectors | No | No |
| Information captured | Sequence semantics | Structural patterns |

---

## Important notes

- Primary and secondary embeddings are complementary.
- Both embedding types preserve `protein_group_id` and `group_id`.
- SecondaryBERT embeddings are generated only for proteins with valid secondary structure predictions.
- ProtT5 embeddings are sequence-level representations.
- SecondaryBERT saves pooled structural window vectors.
- ProtT5 pooling includes all attention-mask-valid tokens, including its end-of-sequence token.
- Primary embeddings contain augmented rows; structural embeddings describe original groups. Join by dataset and IDs, not row order. Structural features reused for variants represent the original protein, not a new mutant prediction.
- Both embedding sets are intended as features for downstream neural network training; that training pipeline is not included yet.

---

## Execution

Run the following examples from the `data_pipeline` repository root. Input files must be inside the configured `DATA_INTERMEDIATE` tree. Both generators write outside the repository under `/data/nap/lperez_nn/data/data_input_nn/`, preserving species/class/family directories. Review the path constants when moving to another machine.

### ProtT5

```bash
python3 scripts/embeddings/primary_structure/generate_prott5_embeddings.py \
  --input /home/nap/lperez_nn/data/data_intermediate/human/mhc-I/HLA-A/classification_human_mhc-I_HLA-A_blosum.csv
```

### Corrected SecondaryBERT

The default model directory is `/home/nap/lperez_nn/model/secondary_bert`. The eight-token vocabulary contract and historical identical-embedding issue are documented in [secondaryBERT](../secondaryBERT/README.md).

```bash
python3 scripts/embeddings/secondary_structure/generate_secondary_bert_embeddings.py \
  --csv /home/nap/lperez_nn/data/data_intermediate/human/mhc-I/HLA-A/classification_human_mhc-I_HLA-A_ss.csv
```

Process all datasets cooperatively on two GPUs:

```bash
torchrun --standalone --nproc_per_node=2 \
  scripts/embeddings/secondary_structure/generate_secondary_bert_embeddings.py \
  --batch-size 1024 --chunk-size 102400
```

Use `--species human` or `--species mouse` to restrict discovery. All ranks process the same dataset order; chunk `k` belongs to rank `k % world_size`. CSV reading is streamed (`--csv-chunk-rows`, default 100,000), while a set of seen group IDs grows with the number of groups. Inference uses CUDA fp16 autocast and saves float32 arrays through memory-mapped temporary files and atomic publication.

CUDA is required by default; `--allow-cpu` explicitly enables CPU execution. `--no-metadata` skips metadata CSV generation. Resume compares configuration/model identity and checks existing chunk shapes/dtypes. `--force` removes previous outputs for each selected dataset and regenerates them. A completion marker is written after final chunk validation and index generation.

### `check_secondary_embeddings.py`

```bash
python3 scripts/embeddings/secondary_structure/check_secondary_embeddings.py
```

This standalone checker reads the fixed external output root and checks all 11 expected species/class/family datasets. It verifies completion markers, configuration, contiguous manifest ranges, physical chunk counts, `(N, 768)` float32 arrays, chunk/global ID agreement and unique ordered group IDs. Numerical finiteness and variability are checked on up to 512 sampled rows per chunk, not every embedding value. Missing metadata/index CSVs are warnings. Configurations containing `secondary_bert_mlm` are rejected as legacy references.

Generation also checks the tokenizer and compares embeddings for four contrasting C/H/E patterns before processing data. Different structural strings must not all collapse to an effectively identical vector. Identical structural inputs can legitimately produce identical vectors; variability checks do not establish epitope-prediction quality.

The recorded local check reports **11/11 PASS**, **55,763,575 rows** and **551 chunks**. The log is a local artifact (`*.log` is ignored by Git); these counts are documented here so the result remains visible in GitHub. See [Data and models](../../docs/data_and_models.md) for the artifact inventory and model validation summary.
