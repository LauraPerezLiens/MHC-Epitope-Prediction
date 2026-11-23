# SecondaryBERT pretraining

Build a BERT masked-language model from ProteinUnet-predicted C/H/E sequences:

```text
UniRef50 → MMseqs2 clustering → FASTA chunks → ProteinUnet
  → prediction audit → cleaned Parquet splits → MLM training → validation
```

“UniRef30” is the local name for representatives clustered at 30% identity, not an official UniRef release. The recorded build has 23,127,616 representatives in 232 FASTA chunks of up to 100,000 sequences.

Run commands from the project root. Examples use `data/data_uniref50/`; restore the [local archive](../../../data/used_data/README.md) first if needed. ProteinUnet uses the separate [proteinunet_env](../../../env/README.md) and local weights in `model/unet_c_ensemble/`. Clustering requires an MMseqs2 executable; its default path is `<data-dir>/mmseqs2/mmseqs/bin/mmseqs`, overridable with `--mmseqs-bin`.

## 1. Prepare structural sequences

| Script | Input → output | Defaults and behavior |
|---|---|---|
| `cluster_uniref50_to_uniref30_mmseqs.py` | `uniref50.fasta` → `clustering/uniref50_c30_rep_seq.fasta` and cluster TSV | Identity 0.3, target coverage 0.8, coverage mode 1, 16 threads |
| `create_uniref30_fasta_chunks.py` | Representative FASTA → `proteinunet_prediction/chunks/chunk_XXXXX.fasta` | 100,000 sequences per chunk |
| `predict_uniref30_secondary_structure.py` | One FASTA chunk → `proteinunet_prediction/outputs/chunk_XXXXX.csv` and `_skipped.csv` | Full-protein C/H/E predictions; non-standard amino acids are skipped |
| `audit_uniref30_secondary_structure_predictions.py` | Input FASTA chunks and predictions → `missing_secondary_structure_audit.csv` | Reports missing proteins and invalid residues |
| `build_secondary_mlm_dataset.py` | Prediction CSVs → `bert_mlm_dataset/` Parquet files and vocabulary | Excludes skipped CSVs; retains nonempty C/H/E strings with matching sequence/structure lengths |

```bash
python data_pipeline/scripts/secondaryBERT/cluster_uniref50_to_uniref30_mmseqs.py   --data-dir data/data_uniref50

python data_pipeline/scripts/secondaryBERT/create_uniref30_fasta_chunks.py   --data-dir data/data_uniref50 --sequences-per-chunk 100000

conda run -n proteinunet_env python data_pipeline/scripts/secondaryBERT/predict_uniref30_secondary_structure.py   --data-dir data/data_uniref50   --model-path model/unet_c_ensemble   -i data/data_uniref50/proteinunet_prediction/chunks/chunk_00001.fasta
```

Repeat prediction for every chunk before auditing and building the dataset:

```bash
python data_pipeline/scripts/secondaryBERT/audit_uniref30_secondary_structure_predictions.py   --data-dir data/data_uniref50

python data_pipeline/scripts/secondaryBERT/build_secondary_mlm_dataset.py   --data-dir data/data_uniref50
```

Prediction CSVs contain `id`, `protein_id`, `sequence` and `secondary_structure`; skipped CSVs contain `protein_id`, `reason` and `details`. The audit distinguishes `non_standard_residues`, `missing_output_csv` and `missing_unknown_reason`.

The builder requires a new output directory and publishes the staged dataset after writing all files. It writes `all_cleaned.parquet`, `train.parquet`, `val.parquet`, `test.parquet` and `vocab.txt`. Splits are assigned by row. They default to 80/10/10 with seed 42; validation size is a fraction of the full cleaned dataset. Recorded source-protein counts are 18,374,944 TRAIN, 2,296,868 validation and 2,296,869 TEST (22,968,681 total).

## 2. Train the model

`train_secondary_mlm.py` streams Parquet rows with PyArrow and selects `min(3, L // 25)` non-overlapping 25-state windows per protein. Proteins shorter than 25 contribute none. Selection is deterministic from the seed, split and source-row index. Inputs contain 27 tokens: CLS, 25 states and SEP.

The saved tokenizer is checked at startup and after saving. It must preserve uppercase symbols with this mapping:

| Token | PAD | UNK | CLS | SEP | MASK | C | H | E |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| ID | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |

The special tokens are spelled `[PAD]`, `[UNK]`, `[CLS]`, `[SEP]` and `[MASK]`. `C H E C` must encode as `[2, 5, 6, 7, 5, 3]`. These checks were introduced after earlier embeddings were reported to be identical for different structural inputs.

| Parameter | Default |
|---|---:|
| Hidden size | 768 |
| Layers / attention heads | 12 / 12 |
| Intermediate size / position embeddings | 3072 / 30 |
| Batch size per rank | 256 |
| Epochs | 1 |
| MLM probability | 0.15 |
| Learning rate / weight decay | 1e-4 / 0.01 |
| Warmup ratio | 0.05 |
| Seed | 42 |
| Parquet batch rows / DataLoader workers | 8192 / 0 |

Selected MLM positions use 80% MASK, 10% random-token and 10% unchanged corruption; special positions are excluded. DDP assigns disjoint Parquet work units with balanced per-rank step budgets. Window counts are cached in `secondary_mlm_rowgroup_stats.json`.

Use a separate output directory for new experiments to preserve the validated `model/secondary_bert`:

```bash
python data_pipeline/scripts/secondaryBERT/train_secondary_mlm.py   --data-dir data/data_uniref50 --output-dir model/secondary_bert_experiment
```

For two GPUs, replace `python` with `torchrun --standalone --nproc_per_node=2`. `--max-train-proteins` and `--max-val-proteins` limit source proteins, not generated windows. Training uses validation data for startup sanity checks; held-out MLM metrics are computed separately.

## 3. Validate

`validate_secondary_mlm.py` evaluates `val.parquet` using deterministic windows and seeded MLM corruption. It reports masked-token loss, perplexity, C/H/E precision/recall/F1, a confusion matrix, unknown/non-biological token counts and synthetic embedding variability. It supports single-process and `torchrun` execution.

```bash
python data_pipeline/scripts/secondaryBERT/validate_secondary_mlm.py   --dataset-dir data/data_uniref50/bert_mlm_dataset   --model-dir model/secondary_bert --max-val-proteins 100000
```

Results default to `<model-dir>/validation_metrics.json`; `--output-json` overrides the path. Omit `--max-val-proteins` to use the full validation split. These are structural reconstruction metrics, not epitope-prediction results. Recorded results are in the [model inventory](../../docs/data_and_models.md).

After validation, use the [embedding generator](../embeddings/README.md) for classification-window features.
