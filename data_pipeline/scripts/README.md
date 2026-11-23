# Historical data processing steps

Run documented commands from the `lperez_nn/` root. Use `nap_env` except for ProteinUnet prediction, which uses `proteinunet_env`; see [environment setup](../../env/README.md).

| Step | Module | Purpose |
|---|---|---|
| 1 | [data_download](data_download/README.md) | Download and deduplicate IEDB events. |
| 2 | [data_classification](data_classification/README.md) | Retrieve proteins and label windows. |
| 3 | [data_augmentation](data_augmentation/README.md) | Generate BLOSUM62 variants. |
| 4 | [secondary_structure_prediction](secondary_structure_prediction/README.md) | Predict and map secondary structure. |
| 5 | [secondaryBERT](secondaryBERT/README.md) | Prepare structural training data and train the representation model. |
| 6 | [embeddings](embeddings/README.md) | Generate ProtT5 and SecondaryBERT representations. |
| 7 | [data_shuffling](data_shuffling/README.md) | Globally shuffle rows and recover interrupted runs. |
| 8 | [data_splitting](data_splitting/README.md) | Assign splits, prepare metadata and validate. |
| 9 | [embedding_concatenation](embedding_concatenation/README.md) | Combine both representations. |
| 10 | [data_archiving](data_archiving/README.md) | Compress consumed sources with full verification; overlaps conversion where safe. |

Steps 3 and 4 are complementary branches. SecondaryBERT has its own pretraining workflow. The classifier scaler and launchers are in `../../neural_network/MLP/`. The MLP loader reads concatenated chunks directly; original sources can be archived after verified conversion.

Shuffling, splits, metadata and scaling are already complete for the historical training tree. The split generator can replace an existing `master_split.csv`, and metadata regeneration can replace arrays. Archive mode removes originals after verification. Use these preparation commands on separate working trees.

For certified D1, use the [data contract](../docs/data_and_models.md#certified-d1-and-planned-d2). D1 uses original observations and groups global labels and splits by exact primary sequence. D2 remains planned. The diagnostics below target historical artifacts. Their reports are written to the configured output directories.

## Sequence label contradictions

Run `python data_pipeline/scripts/find_label_contradictions.py` with `nap_env`.
It finds identical 25aa sequences with both labels across all classification sources;
it does not compare embeddings. Extracted CSVs live in
`data/used_data/contradiction_sources` (automatically extracted from the original
archive if the directory is absent). Original archives and training data are retained.

Outputs in `results/data_contradictions`: `contradictions.csv` (all original columns,
source/family/species, protein accession, local and global group IDs, source row
index and label counts), `summary.json`, and the resumable `index.sqlite`.
Local `protein_group_id` and `group_id` must be interpreted together with
`source_file`; `global_group_id` uses the shuffle manifest. Rerun the same command
to resume counting; the CSV and JSON are each replaced atomically. Inputs and batch size must stay
unchanged when resuming. Use `--output` for a separate run.

## Group split overlap and sampled modalities

```bash
python -u data_pipeline/scripts/check_group_splits.py
python -u data_pipeline/scripts/check_sampled_modalities.py --groups-per-source 3 --chunks 3 --seed 42
```

`check_group_splits.py` reads every compact group/split metadata array, using
TRAIN=0, VALIDATION=1 and TEST=2. It exports one row per observed global group
with local/source IDs and counts in each split to
`results/group_split_check/group_splits.csv`. `summary.json` reports row totals,
exclusive split combinations, pairwise overlaps and results by source. This is
a complete group scan, not a protein or sequence similarity check. It requires
about 1.3 GB for the count matrix and writes all observed groups to the CSV.

`check_sampled_modalities.py` defaults to 3 distinct groups per source (33 total
for the current 11 sources), spread across 3 randomly selected chunks. It reads
only selected Primary/Secondary source blocks, verifies archived original SHA256
checksums, and compares exact unscaled values with the concatenated dataset.
Primary is compared with the archived **shuffled** Primary, not pre-shuffle
provenance. Secondary is compared with original per-group values. Outputs are
`results/sampled_modalities_check/sampled_modalities.csv` (sample locations,
local/global group, protein group, references and differences) and `summary.json`.
The sample can be enlarged using `--groups-per-source` and changed with `--seed`.
Both checks read datasets and use writer locks for their reports. Existing
reports at the chosen output can be replaced. Use `--output` for separate reports.

## Primary embedding sensitivity to single substitutions

```bash
python -u data_pipeline/scripts/measure_primary_mutations.py --groups-per-source 10 --seed 42
```

Uses existing original ProtT5 chunks: samples 10 complete groups in one random
chunk per source, compares each original with its 25 conservative BLOSUM62
single-substitution variants, and uses all distinct-sequence original pairs
within each sampled source/chunk as a reference. Reports cosine similarity,
raw L2/relative L2 and distances after the MLP Primary scaler. Outputs CSVs,
`summary.json` and `comparison.png` in `results/primary_mutation_test`.

Variant identities are reconstructed with the retained augmentation generator;
26-row group contiguity/order, original protein/group/label and archive hashes
are checked. The augmented sequence CSV is not independently reread. This is
a descriptive sample of conservative substitutions, not arbitrary mutations,
proof of label preservation or a biological effect prediction. Reference groups
may share a protein; their sequence Hamming distance is included in the CSV.
