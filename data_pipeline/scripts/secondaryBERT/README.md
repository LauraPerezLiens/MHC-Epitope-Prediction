# secondaryBERT

## Overview

This module builds and trains a BERT masked-language model using predicted protein secondary-structure sequences.

The pipeline starts from the UniRef50 protein database, reduces sequence redundancy by clustering representatives at 30% sequence identity, predicts secondary structure with ProteinUnet, prepares a C/H/E masked-language-modeling dataset, and finally trains a BERT model.

Although the original input database is UniRef50, sequences are clustered at 30% sequence identity using MMseqs2. The resulting representative sequence set is referred to throughout this documentation as **"UniRef30"**, although it is not the official UniRef30 database.

For the UniRef30 dataset used in this project:

```text
Representative sequences: 23,127,616
Chunk size: 100,000 sequences
Generated chunks: 232
```

---

## Pipeline role

```text
UniRef50 FASTA
    ↓
MMseqs2 clustering at 30% identity
    ↓
UniRef30 representative sequences
    ↓
FASTA chunking
    ↓
ProteinUnet secondary-structure prediction
    ↓
C/H/E secondary-structure dataset
    ↓
BERT MLM pretraining
```

---

## Directory structure

Expected data structure:

```text
/home/nap/lperez_nn/data/data_uniref50/
├── bert_mlm_dataset/
│   ├── all_cleaned.parquet
│   ├── train.parquet
│   ├── val.parquet
│   ├── test.parquet
│   └── vocab.txt
│
├── clustering/
│   ├── uniref50_c30_cluster.tsv
│   └── uniref50_c30_rep_seq.fasta
│
├── mmseqs2/
│   └── mmseqs/
│
└── proteinunet_prediction/
    ├── chunks/
    │   ├── chunk_00001.fasta
    │   ├── chunk_00002.fasta
    │   └── ...
    │
    ├── outputs/
    │   ├── chunk_00001.csv
    │   ├── chunk_00001_skipped.csv
    │   ├── chunk_00002.csv
    │   ├── chunk_00002_skipped.csv
    │   └── ...
    │
    └── missing_secondary_structure_audit.csv
```

---

## Scripts

### 1. `cluster_uniref50_to_uniref30_mmseqs.py`

Clusters UniRef50 sequences with MMseqs2 to obtain a representative sequence set at 30% sequence identity.

#### Input

```text
/data_uniref50/uniref50.fasta
```

#### Output

```text
/data_uniref50/clustering/uniref50_c30_cluster.tsv
/data_uniref50/clustering/uniref50_c30_rep_seq.fasta
```

#### Main parameters

```text
--min-seq-id 0.3
--coverage 0.8
--cov-mode 1
--threads 16
```

#### Run

```bash
python3 cluster_uniref50_to_uniref30_mmseqs.py
```

---

### 2. `create_uniref30_fasta_chunks.py`

Splits the UniRef30 representative FASTA file into smaller FASTA chunks.

This step is kept separate from secondary-structure prediction so that chunks can be processed independently and failed chunks can be rerun without repeating the clustering or splitting steps.

#### Input

```text
/data_uniref50/clustering/uniref50_c30_rep_seq.fasta
```

#### Output

```text
/data_uniref50/proteinunet_prediction/chunks/chunk_00001.fasta
/data_uniref50/proteinunet_prediction/chunks/chunk_00002.fasta
...
```

#### Default chunk size

```text
100,000 sequences per chunk
```

#### Run

```bash
python3 create_uniref30_fasta_chunks.py
```

Optional:

```bash
python3 create_uniref30_fasta_chunks.py \
  --sequences-per-chunk 100000
```

---

### 3. `predict_uniref30_secondary_structure.py`

Predicts secondary structure for one FASTA chunk using ProteinUnet.

The model outputs secondary structure as a string over the alphabet:

```text
C H E
```

where:

```text
C = coil
H = helix
E = beta strand
```

ProteinUnet expects sequences containing only the 20 standard amino acids. Sequences containing non-standard residues such as `X`, `U`, `B`, `Z`, `J` or `O` are skipped and written to a separate skipped file.

The prediction script writes both the successful predictions and skipped/failed proteins. The output CSV contains `id`, `protein_id`, `sequence` and `secondary_structure`, while the skipped CSV records `protein_id`, `reason` and `details`.

#### Input

```text
/data_uniref50/proteinunet_prediction/chunks/chunk_XXXXX.fasta
```

#### Output

```text
/data_uniref50/proteinunet_prediction/outputs/chunk_XXXXX.csv
/data_uniref50/proteinunet_prediction/outputs/chunk_XXXXX_skipped.csv
```

#### Run

```bash
python3 predict_uniref30_secondary_structure.py \
  -i /home/nap/lperez_nn/data/data_uniref50/proteinunet_prediction/chunks/chunk_00001.fasta
```

Optional custom output name:

```bash
python3 predict_uniref30_secondary_structure.py \
  -i /home/nap/lperez_nn/data/data_uniref50/proteinunet_prediction/chunks/chunk_00001.fasta \
  -o chunk_00001.csv
```

---

### 4. `audit_uniref30_secondary_structure_predictions.py`

Audits the ProteinUnet prediction step by comparing every input FASTA chunk against its corresponding output CSV.

For each protein present in the FASTA but absent from the prediction output, the script checks whether the protein contains non-standard amino acids.

#### Input

```text
/data_uniref50/proteinunet_prediction/chunks/chunk_XXXXX.fasta
/data_uniref50/proteinunet_prediction/outputs/chunk_XXXXX.csv
```

#### Output

```text
/data_uniref50/proteinunet_prediction/missing_secondary_structure_audit.csv
```

#### Output columns

```text
chunk
protein_id
sequence_length
missing_reason
invalid_residues
sequence
```

Possible `missing_reason` values include:

```text
non_standard_residues
missing_output_csv
missing_unknown_reason
```

#### Run

```bash
python3 audit_uniref30_secondary_structure_predictions.py
```

---

### 5. `build_secondary_mlm_dataset.py`

Builds the final secondary-structure MLM dataset for BERT pretraining.

This script merges all ProteinUnet prediction CSV files, removes invalid rows, checks that sequence length and secondary-structure length match, converts C/H/E strings into space-separated token sequences, and splits the dataset into train, validation and test sets.

#### Input

```text
/data_uniref50/proteinunet_prediction/outputs/chunk_XXXXX.csv
```

Skipped files are ignored:

```text
chunk_XXXXX_skipped.csv
```

#### Output

```text
/data_uniref50/bert_mlm_dataset/all_cleaned.parquet
/data_uniref50/bert_mlm_dataset/train.parquet
/data_uniref50/bert_mlm_dataset/val.parquet
/data_uniref50/bert_mlm_dataset/test.parquet
/data_uniref50/bert_mlm_dataset/vocab.txt
```

#### Vocabulary

```text
[PAD]
[UNK]
[CLS]
[SEP]
[MASK]
C
H
E
```

#### Default split

```text
train: 80%
validation: 10%
test: 10%
random seed: 42
```

The validation size is interpreted as a fraction of the full cleaned dataset, not as a fraction of the remaining train/validation subset.

#### Run

```bash
python3 build_secondary_mlm_dataset.py
```

---

### 6. `train_secondary_mlm.py`

Trains a new `BertForMaskedLM` from the cleaned Parquet dataset. The script streams `secondary_structure_spaced` in PyArrow batches, rather than loading all proteins into memory. It validates the tokenizer at startup and after saving.

#### Corrected vocabulary contract

Earlier embeddings were reported to be identical across different structural inputs, and the BERT dictionary/tokenizer was revised. The current implementation enforces this exact mapping:

| Token | ID |
|---|---:|
| `[PAD]` | 0 |
| `[UNK]` | 1 |
| `[CLS]` | 2 |
| `[SEP]` | 3 |
| `[MASK]` | 4 |
| `C` | 5 |
| `H` | 6 |
| `E` | 7 |

`do_lower_case=False` preserves the biological symbols. The startup check requires:

```text
C H E C → [2, 5, 6, 7, 5, 3]
```

Training windows are encoded directly using the same IDs. Each input contains `[CLS]`, 25 biological states and `[SEP]`: **27 tokens**, within the model's 30-position capacity. Correct vocabulary mapping prevents different biological symbols from being lost as unknown tokens; output variability is checked separately during validation and embedding generation. The previous failure is not diagnosed solely by a model directory name.

#### Inputs and window sampling

Required files: `train.parquet`, `val.parquet` and `vocab.txt` under `bert_mlm_dataset/`. The validation split is used for startup data sanity checks in this training script; held-out MLM metrics are computed separately by `validate_secondary_mlm.py`.

For a protein of length `L`, training selects `min(3, L // 25)` non-overlapping windows; proteins shorter than 25 positions contribute none. Starts are deterministic from the seed, split name and source-row index. This replaces the old description of taking only the first 25 positions.

Dataset sizes recorded for the project build (source proteins, not sampled windows):

| Split | Proteins |
|---|---:|
| Train | 18,374,944 |
| Validation | 2,296,868 |
| Test | 2,296,869 |
| Total | 22,968,681 |

#### Current defaults

| Parameter | Value |
|---|---:|
| Vocabulary size | 8 |
| Hidden size | 768 |
| Transformer layers / attention heads | 12 / 12 |
| Intermediate size | 3072 |
| Maximum position embeddings | 30 |
| Window size / maximum windows per protein | 25 / 3 |
| Batch size per rank | 256 |
| Epochs | 1 |
| MLM probability | 0.15 |
| Learning rate | 1e-4 |
| Weight decay | 0.01 |
| Warmup ratio | 0.05 |
| Seed | 42 |
| Parquet batch rows | 8192 |
| DataLoader workers | 0 |

Dynamic MLM corruption uses the standard 80% mask / 10% random token / 10% unchanged policy among selected positions. Special positions are not selected as targets. Distributed training uses DDP, balanced Parquet row-group assignments and equal per-rank step budgets. Resource monitoring reports memory/GPU usage when optional monitoring dependencies are available.

#### Run from the repository root

Training, embedding generation and validation now default to `model/secondary_bert`. The legacy `secondary_bert_mlm` weights have been removed. Training saves model/tokenizer artifacts to the selected output directory; use a separate `--output-dir` for experiments to preserve the validated model.

```bash
python3 scripts/secondaryBERT/train_secondary_mlm.py \
  --output-dir /home/nap/lperez_nn/model/secondary_bert
```

Two-GPU example:

```bash
torchrun --standalone --nproc_per_node=2 \
  scripts/secondaryBERT/train_secondary_mlm.py \
  --output-dir /home/nap/lperez_nn/model/secondary_bert \
  --batch-size 256
```

Use a separate `--output-dir` for experiments. `--max-train-proteins` and `--max-val-proteins` limit source proteins for small runs; they do not set the number of generated windows. Row-group window counts are cached in `secondary_mlm_rowgroup_stats.json`.

### 7. `validate_secondary_mlm.py`

Evaluates the saved model on `val.parquet`, with deterministic window sampling and seeded MLM corruption. Supports single-process and `torchrun` execution. It reports masked-token loss, perplexity, accuracy, C/H/E precision/recall/F1, a confusion matrix, unknown/non-biological token counts and a synthetic embedding variability check.

```bash
python3 scripts/secondaryBERT/validate_secondary_mlm.py \
  --model-dir /home/nap/lperez_nn/model/secondary_bert \
  --max-val-proteins 100000
```

By default the result is written to `<model-dir>/validation_metrics.json`; `--output-json` selects another file. Omitting the limit evaluates the full validation split.

The saved project result covers 100,000 proteins and 275,119 windows: loss 0.255735, perplexity 1.291411, masked-token accuracy 0.885621 and macro-F1 0.873589. Original unknown-token count is zero and the synthetic embeddings are not all identical. These are **structural MLM metrics**, not epitope-prediction performance or final test-set results.

## Execution order

Run clustering, FASTA chunking, prediction for every chunk, prediction auditing and dataset construction in that order, using the commands above from this module's directory. Then run the training and validation commands from the repository root. After validation, generate classification-window embeddings using [the embeddings module](../embeddings/README.md).

---

## Handling of non-standard amino acids

ProteinUnet uses one-hot encoding over the 20 standard amino acids only:

```text
A D N R C E Q G H I L K M F P S T W Y V
```

Proteins containing residues outside this set are not passed to the model. They are written to the corresponding skipped file:

```text
proteinunet_prediction/outputs/chunk_XXXXX_skipped.csv
```

This avoids generating unreliable secondary-structure predictions for sequences that the model cannot encode.

---

## Dataset cleaning

Before BERT pretraining, the merged ProteinUnet outputs are cleaned.

Rows are retained only if:

```text
secondary_structure contains only C/H/E
sequence length == secondary_structure length
secondary_structure is not empty
```

The cleaned dataset is saved as:

```text
bert_mlm_dataset/all_cleaned.parquet
```

Then it is split into:

```text
train.parquet
val.parquet
test.parquet
```

---

## Notes

* The pipeline uses UniRef50 as the original source database.
* After MMseqs2 clustering at 30% sequence identity, the working representative set is referred to as UniRef30.
* ProteinUnet prediction is the main computational bottleneck.
* FASTA chunking is intentionally separated from prediction to simplify parallel execution and reruns.
* BERT is trained only on valid C/H/E secondary-structure strings.
* Sequences skipped by ProteinUnet are not included in the BERT pretraining dataset.
