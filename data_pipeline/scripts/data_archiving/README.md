# Verified source archiving

`archive_inputs.py` compresses files using zstd level 1. Archives stay next to their original paths as `filename.zst`, with a `filename.archive.json` verification record.

With the original present, the archiver verifies decompression and compares the resulting SHA-256 with the source hash. It publishes a receipt with both hashes and checks file identity before removing the original. Keep the tree inactive for the entire run. Archive and receipt publication each use a separate rename. Controlled interruption tests cover recovery between them. Abrupt filesystem failure is outside those tests.

With `--archive-sources`, the concatenator archives each shuffled Primary after verifying its output. `--archive-originals PATH` also archives the original dataset tree after conversion. Original Secondary embeddings remain uncompressed until all output chunks are complete. The original dataset tree and remaining shuffled metadata are then archived. An optional concatenation SSD cache is removed after archival completes. Consumed `_shuffle_work/` and `_recovery/` scratch directories are removed only after successful concatenation; they are not needed for training or restoration of the source datasets.

`ARCHIVED.json` records completion of a tree. Per-file compression supports progressive space recovery and restart.

## Standalone archive

Use only on an inactive source tree:

```bash
python data_pipeline/scripts/data_archiving/archive_inputs.py \
  --root data/data_input_nn --threads 1
```

## Restore one file

From the project root:

```bash
zstd -d data/data_input_nn_shuffled/mixed/classification_mixed_ProtT5_chunks/chunk_000000_X.npy.zst
```

This restores the NPY and keeps the compressed archive. Compare the restored NPY SHA-256 with `original_sha256` in the receipt before using it. To restore an entire source tree, decompress each `.zst` to its original path without overwriting existing files. Restoration of a legacy workflow may require all Secondary indexes and referenced files as well as Primary chunks.
