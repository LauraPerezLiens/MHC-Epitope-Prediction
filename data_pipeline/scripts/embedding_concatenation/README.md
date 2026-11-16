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

Rerunning a completed conversion verifies feature and metadata checksums before returning, even without archival; this reads all output files. New chunk records store `metadata_sha256` for labels, group IDs and split IDs. For older records, verification uses source metadata or the original hashes retained in its archive records. Missing evidence or a content mismatch stops verification. This check does not rewrite outputs or upgrade old records.

`--max-chunks` and `--start-chunk` are benchmark options and always leave output incomplete. `--in-place` retains the legacy conversion mode; it cannot be combined with progressive archival.

## 4. Train using concatenated data only

```bash
bash neural_network/MLP/run_chunk_ladder100_dualeval.sh
```

The launcher defaults to `data/data_input_nn_shuffled_concatenate/`. The loader reads its 1,792-column arrays directly and applies the existing TRAIN scaler separately to the 1,024 Primary and 768 Secondary columns. No original Secondary lookup is performed. The previous 50/50 training and evaluation policies remain unchanged.
