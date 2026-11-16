# Embedding concatenation

Concatenate Primary (ProtT5, 1,024 columns) and Secondary (SecondaryBERT, 768 columns) into 1,792 unnormalized float32 features per row. Secondary is matched by group ID, including repeated and nonconsecutive groups.

Run from the `lperez_nn/` root with `nap_env` activated.

## 1. Inputs

The shuffle, split and compact `chunk_metadata/` must already be complete and validated. Keep the source metadata and original Secondary embeddings unchanged while converting. The optimized path reads prepared arrays instead of reparsing the full source CSVs.

## 2. Convert and archive progressively

```bash
python -u data_pipeline/scripts/embedding_concatenation/concatenate_primary_secondary.py \
  --root data/data_input_nn_shuffled \
  --output data/data_input_nn_shuffled_concatenate \
  --workers 4 --block-rows 16384 \
  --secondary-cache-dir /tmp/lperez_nn_secondary_cache \
  --archive-sources --archive-originals data/data_input_nn \
  --archive-threads 1
```

Workers perform CPU/I/O conversion; no GPU is needed. The optional SSD cache is populated once with SHA-256-verified Secondary files, then reused for random reads. It is removed after successful source archival. It must be separate from all dataset trees. Each worker stages one chunk's Secondary values in RAM, writes sequentially and compares every output value against its inputs before publication. Checksums and signatures allow verified outputs from the earlier implementation to be reused. Per-chunk labels, group IDs and split IDs are copied and verified independently.

A bounded background worker compresses consumed shuffled Primary files while conversion continues. Originals are removed only after decompression matches their SHA-256. Secondary files remain available until every output chunk is complete; they are then archived with the original dataset and remaining shuffled metadata. See [archiving](../data_archiving/README.md).

The output contains its own features, metadata, feature layout and provenance manifest. Training does not require the original CSVs or Secondary paths retained as historical provenance.

## 3. Completion and restart

`PROGRESS` messages report completed chunks and observed throughput. Do not start a second writer against the same output.

Do not train while `INCOMPLETE` exists. The final layout records verified row and chunk totals. `TRAINING READY` means concatenation is complete; source archival may continue afterwards. Restart the same command after interruption. It verifies existing outputs and reuses them, including chunks whose original Primary is already compressed.

A normal rerun checks feature counts, byte sizes, shapes and dtypes, and hashes every metadata array. New records include feature modification times; a changed timestamp triggers a feature hash check for that file. Unchanged large feature payloads are not reread. Quick checks do not detect same-size corruption with a preserved timestamp; older records without timestamps receive only structural feature checks.

For full cryptographic verification, run:

```bash
python data_pipeline/scripts/embedding_concatenation/concatenate_primary_secondary.py \
  --verify-only --output data/data_input_nn_shuffled_concatenate
```

This reads every feature and metadata file, checks SHA-256 and refuses incomplete datasets. It requires the persistent `.writer.lock` and takes a shared lock before reading payloads; writers take an exclusive lock. A missing lock is an error, not permission to verify without synchronization. The verifier never creates a lock. Do not delete or replace lockfiles while any process uses the dataset. It does not convert, archive, delete, create locks or update records. Full verification of the real dataset can read several terabytes; it is an explicit operation, not part of normal training startup. Archival always uses full verification before removing remaining sources.

New records store `metadata_sha256` for labels, group IDs and split IDs. Older records require source metadata or its archived `original_sha256` evidence. Missing evidence is an error in either mode; historical data are not silently certified or upgraded. Training does not require source archives, but full metadata verification of historical records may need their checksum records.

`--max-chunks` and `--start-chunk` are benchmark options and always leave output incomplete. `--in-place` retains the legacy conversion mode; it cannot be combined with progressive archival.

## 4. Train using concatenated data only

```bash
bash neural_network/MLP/run_chunk_ladder100_dualeval.sh
```

The launcher defaults to `data/data_input_nn_shuffled_concatenate/`. The loader reads its 1,792-column arrays directly and applies the existing TRAIN scaler separately to the 1,024 Primary and 768 Secondary columns. No original Secondary lookup is performed. The previous 50/50 training and evaluation policies remain unchanged.
