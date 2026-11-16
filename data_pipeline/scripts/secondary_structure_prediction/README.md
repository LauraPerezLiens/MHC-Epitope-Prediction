# Secondary structure prediction and mapping

Predict C/H/E states for IEDB parent proteins, then map them to the original 25-aa classification windows. Create [proteinunet_env](../../../env/README.md) and provide weights in `model/unet_c_ensemble/`.

## 1. Predict parent-protein structure

`predict_secondary_structure.py` reads a parent-protein CSV containing `protein_url` and `fasta`. It writes `protein_url`, `sequence` and `secondary_structure` columns, where C is coil, H is helix and E is beta strand.

Only the 20 standard amino acids are accepted. Proteins longer than 1,024 residues use overlapping windows with 200-residue overlap; probabilities are averaged in overlapping regions before assigning states. Output lengths are checked against input lengths.

The model defaults to `model/unet_c_ensemble/`. From the project root:

```bash
conda run -n proteinunet_env python data_pipeline/scripts/secondary_structure_prediction/predict_secondary_structure.py   -i parent_proteins.csv -o secondary_struct_human.csv
```

## 2. Map predictions to classification windows

`add_secondary_structure.py` reads the human/mouse structure predictions and `classification_*.csv` files from configured paths. Required classification columns are `protein_group_id`, `group_id`, `25aa_seq`, `protein_url` and `window_start`.

It matches normalized protein URLs, checks coordinates and exact sequence agreement, then extracts the corresponding structural window. Output files are named `classification_*_ss.csv` and preserve the original columns plus:

| Column | Contents |
|---|---|
| `secondary_structure` | Mapped 25-state sequence |
| `protein_found` | Whether the parent protein was found |
| `sequence_match` | Whether the protein window matches the classification sequence |
| `ss_status` | Mapping result |

Status values are `ok`, `protein_not_found`, `invalid_window_start`, `window_out_of_range` and `sequence_mismatch`.

```bash
python data_pipeline/scripts/secondary_structure_prediction/add_secondary_structure.py
```

Mapping applies to original windows, not BLOSUM-mutated sequences. Variants later reuse their group's structural features. See [embeddings](../embeddings/README.md) for SecondaryBERT vectors and [secondaryBERT](../secondaryBERT/README.md) for the separate UniRef pretraining workflow.
