# IEDB data download

`build_iedb_dataset.py` retrieves MHC binding and T-cell assays from the IEDB API using offset pagination. Queries select positive linear-peptide assays for human or mouse hosts and source organisms, grouped by MHC class and family.

The default output root is `data/data_raw/`, resolved from the project location. Each `species/mhc-class/family/` directory contains:

| File | Contents |
|---|---|
| `mhc_export_full.csv` | MHC assay query results |
| `tcell_export_full.csv` | T-cell assay query results |
| `merged_unique_events.csv` | Combined, deduplicated events for classification |

The merge extracts the canonical peptide sequence, discards entries missing epitopes or coordinates, and deduplicates by `(epitope sequence, start, end, source_id, parent_id)`. `protein_id` duplicates `parent_id` for downstream compatibility. Failed API requests stop the run.

## Run

The historical downloader writes CSV files directly at the default destination. A repeat run can replace existing files, and an interruption during writing can leave a partial CSV. From the project root:

```bash
python data_pipeline/scripts/data_download/build_iedb_dataset.py
```

Protein sequence validation is performed later during [parent-protein retrieval](../data_classification/README.md).
