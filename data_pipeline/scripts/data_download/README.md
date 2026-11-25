# IEDB data download and inspection

This is the first stage of the pipeline: pull assays from IEDB, certify where
they came from, and inspect them well enough to decide how to filter. Nothing
here builds training examples — that happens in
[`../data_processing/`](../data_processing/README.md).

Run everything from the project root with the `nap_env` interpreter, which has
`pandas`, `requests` and `pyarrow`:

```bash
P=/home/nap/miniconda3/envs/nap_env/bin/python
```

## Scripts

| Script | Purpose | Status |
|---|---|---|
| [`build_iedb_dataset_v2.py`](build_iedb_dataset_v2.py) | Download assays from IEDB. **The current downloader.** | active |
| [`slim_raw_export.py`](slim_raw_export.py) | Cut the 113/162 raw columns down to a working set, drop non-peptide rows, census the values. | active |
| [`count_clean_positives.py`](count_clean_positives.py) | Count how many positives survive a given filter funnel, split by epitope origin and allele reliability. | active |
| [`build_iedb_dataset.py`](build_iedb_dataset.py) | The historical downloader. | **deprecated** |

### `build_iedb_dataset_v2.py` — download

Queries `https://query-api.iedb.org/mhc_export` and `/tcell_export` once per
species/class/family (11 families) and writes one CSV per endpoint plus a
`manifest.json`.

Three things it does that the historical script did not:

- **Keyset pagination** over `assay_id` (`order=assay_id.asc` + `assay_id=gt.N`)
  instead of `offset` with no `order`, which PostgREST does not guarantee to be
  stable between pages.
- **Negatives are not excluded by default.** The qualitative value is downloaded
  as-is and the filtering decision moves downstream.
- **The source-organism filter is an explicit profile choice**, not a decision
  buried in the code.

`--profile` is mandatory, deliberately, so nobody launches a several-million-row
download by accident:

| Profile | Qualitative filter | Source-organism filter | Use |
|---|---|---|---|
| `legacy` | `ilike.*Positive*` | `ilike.*<species>*` | Reproduce the exact universe of D1. |
| `full` | none | none | Superset: experimental negatives plus pathogen epitopes. |

Provenance: the manifest records a content fingerprint per query (row count,
min/max `assay_id`, distinct `assay_id`, distinct alleles, SHA-256, bytes), the
exact request parameters, the UTC date and the git commit. It is resumable —
queries already in the manifest are skipped unless `--force` — and it refuses to
write into a directory whose manifest belongs to a different profile.

IEDB publishes no release or version endpoint (checked across all 39 swagger
endpoints; the swagger's `"version": "14.3"` is PostgREST's, not the database's),
so the content fingerprint is the substitute: two downloads are comparable
byte for byte even though IEDB will not say which version it is on.

```bash
$P -u data_pipeline/scripts/data_download/build_iedb_dataset_v2.py \
    --profile full --out data/data_raw_full_YYYYMMDD
# one family only:
$P -u ... --profile full --out DIR --only mouse/mhc-I/H2-K
```

### `slim_raw_export.py` — column projection, row filter, value census

The raw export has 113 columns (`mhc_export`) and 162 (`tcell_export`), and the
schema is identical across all 11 families, so one curated list serves all of
them. The curated list is **fixed, not derived from any one file's fill rate**:
a column that is empty in H2-K can be well populated in HLA-A or in class II.

Two column profiles:

- `--columns core` (default) — **11 columns**, and the four row filters below.
  This is the working set.
- `--columns full` — the wide curated list, 75 columns, no row filters. An
  inventory for looking things up, not a working set.

The core columns:

| Column | Why |
|---|---|
| `assay_id` | unique key; provenance and dedup |
| `epitope__name` | the peptide sequence |
| `epitope__molecule_parent_iri` | UniProt/NCBI accession — the only way back to the source protein |
| `epitope__starting_position`, `epitope__ending_position` | position within that protein |
| `epitope__source_organism` | strain detail; the species itself is now constant per file |
| `mhc_restriction__name` | the literal allele |
| `assay__method` | assay type, so positives can be counted per type |
| `assay__qualitative_measurement` | the label |
| `reference__pmid`, `reference__date` | publication-leakage axis and temporal split |

### Row filters

`--columns core` applies five filters, in this order. Each one removes rows that
cannot be a valid example, and the manifest records what each removed and with
which values.

| Filter | Condition | Why |
|---|---|---|
| `epitope__object_type` | `== "Linear peptide"` | Removes nothing — the IEDB query already filters it upstream — so it acts as an assertion and the column is dropped as constant. |
| `epitope__modifications` | empty | An oxidised or acetylated peptide is not the same molecule, and its amino acid sequence does not say so: it would enter as if unmodified. The column is used to filter and is **not** kept. |
| `epitope__name` | only the 20 canonical amino acids | Entries such as `GPPGPAGPAGERGEQG + HYL(P3)` are not plain peptides. |
| `epitope__molecule_parent_iri` | not empty | Without an accession the source protein cannot be recovered, so the row cannot become a window or a same-proteome decoy. |
| `epitope__species` | contains the family's own species | `Homo sapiens` for the human families, `Mus musculus` for the murine ones. Cheap: in eluted ligands only 0.50 % of positives came from another organism. |

In `tcell_export` there is one extra object-type filter,
`assay_antigen__object_type`, which does bite — it removes rows whose assayed
antigen was a whole organism, a protein or a tumour cell. `--keep-nonpeptide`
disables the object-type filters.

Not filtered, on purpose: the qualitative value and
`assay_antigen__epitope_relation`. **Note that negatives are not used in this
project**, and the accession requirement happens to remove most of them anyway
(575.559 → 12.133), since binding-assay negatives are largely synthetic peptides
with no parent protein.

`--kind` defaults to `mhc`; `tcell` is set aside for now.

Output is Parquet (the working artefact: typed, columnar, roughly ten times
smaller) **and** CSV (the copy you can read by eye), because inspecting the data
by hand is part of deciding the remaining filters. `--format` takes `parquet`,
`csv` or `both` (default); `--emit-csv` writes the CSV next to an existing
Parquet without re-reading the raw files, which is useful once the raw CSVs have
been archived.

Other modes:

- `--census` — value counts for every categorical column, aggregated over all 11
  families, written into the manifest.
- `--audit-dropped` — fill rate of the **discarded** columns over all 11
  families. This is the safety check on the curation: any discarded column with
  appreciable fill is a curation error. Re-run it after changing the lists.

The manifest records, per file: input and output row counts, what each row filter
removed and which values it removed, kept columns with fill rate and
cardinality, discarded columns with the reason, SHA-256 and bytes of input and
every output, and the git commit.

```bash
$P -u data_pipeline/scripts/data_download/slim_raw_export.py \
    --raw data/_extract_tmp/data_raw_full_20261124 \
    --out data/data_raw_full_20261124_clean \
    --kind mhc --columns core --format both --census
```

### `count_clean_positives.py` — how many positives survive

Applies a cumulative funnel over the clean Parquet files and breaks the
survivors down by epitope origin and allele reliability. Note that since the
clean dataset now applies the modification, canonical-peptide and own-species
filters itself, steps 3, 4 and the origin split are no-ops on it; the script
stays useful for re-running the funnel over a `--columns full` projection or a
fresh download:

1. all rows
2. `+` eluted ligand — `assay__response_measured == 'ligand presentation'`
3. `+` no chemical modification — `epitope__modifications` empty
4. `+` canonical peptide — only the 20 standard amino acids
5. `+` positive — `assay__qualitative_measurement` starts with `Positive`

then splits into origin (self / other organism / unannotated) and allele class
(natural / point mutant / low-resolution serotype).

Step 2 only exists in `mhc_export`: `tcell_export` has **zero**
`ligand presentation` rows, because it measures immunogenicity (IFNg release,
cytotoxicity, proliferation), not presentation. `--kind` defaults to `mhc` for
that reason.

Why these filters: eluted ligand is the supervised target chosen for the
project; a chemically modified peptide is not the same molecule and its amino
acid sequence does not say so; entries like `GPPGPAGPAGERGEQG + HYL(P3)` are not
plain peptides at all; a point mutant such as `HLA-A*02:01 K66A mutant` inherits
the wild-type reference pseudosequence, so training on it attributes to the
wild-type allele the behaviour of a protein engineered in a lab; and a serotype
such as `HLA-A2` names a serological group, not an allele.

```bash
$P -u data_pipeline/scripts/data_download/count_clean_positives.py \
    --clean data/data_raw_full_20261124_clean --kind mhc \
    --json-out reports/audits/recuento_positivos_limpios_YYYYMMDD.json
```

### `build_iedb_dataset.py` — deprecated

The historical downloader. **Do not use it for new data.** It is kept only to
reproduce the provenance of D1.

It paginated by `offset` with no `order`, which risks losing and duplicating
rows between pages. That turned out not to have damaged the data — a re-download
with keyset pagination found 0 duplicates, 1 row present only in the old
snapshot, and 33 interleaved rows out of 192.416 new ones — but the design is
fragile and `build_iedb_dataset_v2.py` replaces it.

Its filters, for the record, since they define the universe D1 was trained on:
`epitope__object_type = eq.Linear peptide`,
`assay__qualitative_measurement = ilike.*Positive*` (**so not a single
experimental negative was ever downloaded**), `mhc_restriction__class`,
`host__name = ilike.*{species}*`,
`mhc_restriction__name = ilike.*{family}*` (substring match, which is how 276
alleles collapsed into 11 family labels) and
`epitope__source_organism = ilike.*{species}*` (which excluded every
pathogen-derived epitope).

## Data locations

| What | Where | Note |
|---|---|---|
| Raw download, `full` profile | `data/used_data/data_raw_full_20261124.tar.zst` | 98 MB archived, 4.8 GB extracted. **Archived on purpose: not for routine use.** Extract to re-run the projection. |
| Clean working set | `data/data_raw_full_20261124_clean/` | Parquet plus CSV, 11 columns, `mhc` only, 1.979.022 rows, with `manifest_slim.json`. |
| Positive counts | `reports/audits/recuento_positivos_limpios_20261125.json` | |

```bash
# restore the raw download when the projection has to be re-run
tar -I zstd -xf data/used_data/data_raw_full_20261124.tar.zst -C data
```

None of `data/` is tracked in git apart from READMEs, so these artefacts live
only on this server. The archive carries a `.sha256` next to it, and every CSV
inside it was verified against the SHA-256 the clean manifest recorded for it
before the uncompressed copy was removed.
