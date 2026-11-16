# Verified source archiving

`archive_inputs.py` compresses files using zstd level 1. Archives stay next to their original paths as `filename.zst`, with a `filename.archive.json` verification record.

Each original is removed only after its archive has been decompressed, compared by SHA-256 and recorded with both checksums. Temporary files and atomic publication support interrupted-run recovery; existing archives are checked before reuse.

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

This restores the NPY and keeps the compressed archive. The verification record contains its expected uncompressed SHA-256. To restore an entire source tree, decompress each `.zst` to its original path without overwriting existing files. Restoration of a legacy workflow may require all Secondary indexes and referenced files as well as Primary chunks.
