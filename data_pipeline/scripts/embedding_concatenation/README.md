# Embedding concatenation

Concatenate Primary (ProtT5, 1,024 columns) and Secondary (SecondaryBERT, 768 columns) into 1,792 unnormalized float32 features per row. Secondary is matched by group rather than row position.

Run from the `lperez_nn/` root with `nap_env` activated.

## 1. Check inputs

The shuffled dataset must be complete, without `INCOMPLETE`. To include prepared splits and metadata in the output, complete [data_splitting](../data_splitting/README.md) first. Keep inputs unchanged during conversion.

## 2. Generate a separate output

```bash
python data_pipeline/scripts/embedding_concatenation/concatenate_primary_secondary.py \
  --root data/data_input_nn_shuffled \
  --output data/data_input_nn_shuffled_concatenated \
  --block-rows 256
```

The run launched on 10 November 2026 was active during reorganization. Its log is `logs/concatenation_20261110.log`. Do not launch a second writer against the same output while it is active.

## 3. Check completion

Do not use the output while `INCOMPLETE` exists. Each chunk is verified before publication. Restarting the command after interruption skips chunks with valid completion records.

`--in-place` replaces the original Primary files with concatenated files. Do not use it alongside scaling or training. Use the separate-output command above to preserve the original files.

## 4. Training

The current MLP loader expects 1,024-column Primary files and separate Secondary embeddings. Adapt it before training on concatenated 1,792-column files.
