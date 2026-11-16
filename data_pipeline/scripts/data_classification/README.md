# Protein retrieval and window classification

Run these scripts in order from the project root. Default paths are resolved from the script location.

## 1. Retrieve parent proteins

`fetch_parent_proteins_fastas.py` reads parent IDs from `data_raw/*/*/*/merged_unique_events.csv`, retrieves FASTA sequences from UniProt or NCBI, and tries the base accession when a full accession cannot be resolved. Only sequences composed of the 20 standard amino acids are retained.

Outputs: `data_intermediate/human_parent_protein_fasta.csv` and `mouse_parent_protein_fasta.csv`, with columns:

```text
protein_url | db | id_full | id_base | resolved_id | fasta
```

```bash
python data_pipeline/scripts/data_classification/fetch_parent_proteins_fastas.py
```

## 2. Generate classification windows

`epitope_classification.py` combines IEDB events with retrieved proteins, verifies exact epitope sequence/coordinate matches, and generates sliding 25-aa windows. Proteins without a retrieved sequence, shorter than 25 residues, or without a valid matching epitope are excluded.

A window is positive if it fully contains a validated epitope. A separate positive example is produced for each contained epitope; other windows are labeled negative. These negatives are not experimentally verified negatives.

Output: `data_intermediate/{species}/{mhc_class}/{family}/classification_*.csv`:

```text
protein_group_id | group_id | 25aa_seq | contains_epitope
selected_epitope | epitope_pos_score | protein_url | window_start
```

`protein_group_id` identifies a protein within a dataset; `group_id` identifies a classification example. A physical window containing multiple epitopes can have multiple group IDs. Downstream augmentation and structure mapping preserve these identifiers.

`epitope_pos_score` describes the epitope's relative position in the window: zero is centered, negative is left, positive is right, within `[-1, 1]`. `window_start` is one-based. Duplicate classification rows are removed before export.

```bash
python data_pipeline/scripts/data_classification/epitope_classification.py
```
