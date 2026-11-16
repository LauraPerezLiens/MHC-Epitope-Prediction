# BLOSUM62 augmentation

`generate_blosum62_variants.py` retains each input sequence and generates one single-substitution variant per position. The replacement is the highest-scoring alternative standard amino acid in BLOSUM62. A 25-aa input produces 26 rows, with the original sequence first.

## Input and output

Input: `classification_*.csv`, requiring:

```text
protein_group_id | group_id | 25aa_seq | contains_epitope
selected_epitope | epitope_pos_score
```

Output: `classification_*_blosum.csv`:

```text
protein_group_id | group_id | original_seq | blosum_seq
contains_epitope | selected_epitope | epitope_pos_score
```

Variants retain both identifiers and the original label. Label preservation is an augmentation assumption, not experimental confirmation of mutant epitope activity. Empty sequences, non-standard amino acids and invalid identifiers are skipped.

## Run

From the project root:

```bash
python data_pipeline/scripts/data_augmentation/generate_blosum62_variants.py input.csv output.csv
```

If the output argument is omitted, `_blosum` is appended to the input filename before its extension.
