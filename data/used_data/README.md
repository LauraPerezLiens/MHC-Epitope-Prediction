# Archived data

Local archives of earlier preparation stages: `data_raw.tar.zst`, `data_intermediate.tar.zst` and `data_uniref50.tar.zst`. These files are excluded from Git. See the [data inventory](../README.md) for the current training dataset.

Each archive was compared against its original directory using GNU `tar --compare` before the original was removed. The accompanying `.sha256` and `.verification.json` files record checksums and verification. Files ending in `.partial` are unfinished archives.

To verify an archive, run from this directory:

```bash
sha256sum -c data_raw.tar.zst.sha256
```

Verify the archive checksum first. Restore from the project root after confirming that the destination directory does not already exist. Extraction writes files directly; an error can leave a partial destination.

```bash
tar --use-compress-program=zstd --keep-old-files -xf data/used_data/data_raw.tar.zst -C data
```

Replace `data_raw` with `data_intermediate` or `data_uniref50` as needed. Restoration requires space for uncompressed data. Earlier processing scripts may require the original directory paths; they do not read compressed archives directly.
