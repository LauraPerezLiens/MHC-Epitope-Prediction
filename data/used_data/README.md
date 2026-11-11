# Archived data

These archives contain previous data preparation stages and SecondaryBERT training datasets. MLP scaling and concatenation use `data_input_nn` and `data_input_nn_shuffled`, which remain at their original locations.

Each `.tar.zst` archive is compared in full against its original directory using GNU `tar --compare` before that directory is removed. `.sha256` files support later integrity checks; `.verification.json` files record verification. Progress is recorded in `archive_20261110.log`. A `.partial` file is not a verified final archive.

To verify an archive, run from this directory:

```bash
sha256sum -c data_raw.tar.zst.sha256
```

To restore a directory, run from the project root after confirming that the destination directory does not already exist:

```bash
tar --use-compress-program=zstd --keep-old-files -xf data/used_data/data_raw.tar.zst -C data
```

Replace `data_raw` with `data_intermediate` or `data_uniref50` as needed. Restoration requires space for uncompressed data. Earlier processing scripts may require the original directory paths; they do not read compressed archives directly.
