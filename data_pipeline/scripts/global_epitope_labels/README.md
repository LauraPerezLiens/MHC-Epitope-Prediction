# Global epitope labels

A 25-character original sequence is globally positive if at least one original row for that exact sequence has `contains_epitope = 1`. A global zero is **unlabeled** in the input scope. Matching compares the sequence as stored, including case. The global label records evidence across the available families and does not establish binding to every MHC, immunogenicity in every organism, or experimental evidence of absence. Evidence counts are annotation rows.

The original family-specific label and the biological context of every source row are retained for future family-specific analysis. This pipeline reads the original classification CSVs and creates a separate dataset. It has no training or data preparation step for embeddings, BLOSUM62 variants, scalers, or split assignments.

## Sources

The default root is `data/used_data/contradiction_sources/`, which contains the 11 pre-augmentation classification CSVs used in the [contradiction analysis](../../../results/data_contradictions/analysis.md). Each file is under `organism/mhc_class/family/classification_<organism>_<mhc_class>_<family>.csv`.

| Organism | MHC class | Families |
|---|---|---|
| human | mhc-I | HLA-A, HLA-B, HLA-C |
| human | mhc-II | HLA-DP, HLA-DQ, HLA-DR |
| mouse | mhc-I | H2-D, H2-K, H2-L |
| mouse | mhc-II | H2-IA, H2-IE |

The source sequence field here is `25aa_seq`. Compatible inputs can call it `original_seq`. If both fields exist, their values must agree. All eleven CSVs must have the same header. Organism, MHC class, and family come from their verified paths. `source_file` plus the zero-based `source_row_index` identifies an original record. `protein_group_id` and `group_id` retain their source-local scope.

## Run from the repository root

Use `nap_env`, which includes pandas and PyArrow. The small run takes the first records in each file and reports statistics for that limited scope.

```bash
conda activate nap_env
python -m unittest tests.test_global_epitope_labels
python -m data_pipeline.scripts.global_epitope_labels.build \
  --rows-per-family 10000 \
  --output results/global_epitope_labels_sample_20261118
```

The full run is an explicit invocation with a separate destination.

```bash
python -m data_pipeline.scripts.global_epitope_labels.build \
  --full --batch-rows 100000 \
  --output data/global_epitope_labels
```

Use `--sources` to supply an alternative source root with the same family layout. A rerun with the same arguments resumes completed SQLite batches and reuses fully written Parquet files. An interrupted export restarts the affected file. The final validation pass runs from the start and checks source file paths, sizes, and modification times against the saved manifest. The output directory is locked during writes. A different input manifest, batch size, or sample scope requires a new directory.

Add `--ram-index` for hosts with spare memory to reduce SQLite I/O. This keeps the working index in memory and commits a transactional snapshot to disk at the end of each family and every 20 newly processed batches. Restart uses the last committed snapshot and replays subsequent input batches. The audit also uses in-memory indexes in this mode. Allow **4 GiB of process RAM** as a planning estimate for this option.

The 11 input CSVs occupy about **4.7 GiB**. For a full run at the default batch size, budget **10–20 GiB free disk** for compressed outputs, the SQLite index, WAL files, and the temporary validation index. Budget **2 GiB process RAM** as a planning allowance. These are estimates, since the full corpus and default batch size were not benchmarked end to end. The real-data prefix test used about **218 MiB peak RSS**. Reducing the batch size before starting a new run lowers the in-process working set.

## Outputs and audit

| Path inside the output | Content |
|---|---|
| `rows/*.parquet` | Eleven compressed tables in original source order. Original CSV fields are retained, including lexical values such as empty strings and leading zeros. The original label is stored as an integer and other original CSV fields as text. |
| `sequences.parquet` | One row per exact original sequence sorted by sequence, with the five global annotation columns. |
| `config.json` | Input paths and file signatures, schema, sequence key, sample scope, batch size, and format. |
| `summary.json`, `report.md` | Original and global statistics, mixed-label counts, evidence across families, and validation status. |
| `families.csv`, `family_count_distribution.csv` | Per-family row counts and conversions, and distribution of positive-family counts. |
| `index.sqlite` | On-disk evidence aggregation and progress used for resume and validation. |

The global fields are `global_contains_epitope`, `global_label_status`, `global_positive_family_count`, `global_positive_families` (an ordered list), and `global_positive_evidence_count`. The converted percentage per family uses the number of original label-zero rows in that family as its denominator.

To verify an existing build and regenerate its reports:

```bash
python -m data_pipeline.scripts.global_epitope_labels.validate \
  --output data/global_epitope_labels
```

The validator compares every Parquet row with its CSV record and independently rebuilds sequence and family counts from the source files into a temporary SQLite index. It verifies the exact-sequence table and cross-checks totals at both levels. With the full default source set, the report compares counts with the earlier contradiction analysis when its summary is available.
