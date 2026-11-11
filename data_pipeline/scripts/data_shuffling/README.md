# Data shuffling

Globally shuffle Primary rows into new chunks while preserving provenance, labels and references to Secondary. Secondary embeddings remain at their original locations.

Run commands from the `lperez_nn/` root with `nap_env` activated.

## 1. Create a new shuffled dataset

The output must be a new directory. Do not overwrite the current shuffled dataset.

```bash
python data_pipeline/scripts/data_shuffling/reorder_chunks.py \
  --root data/data_input_nn \
  --output data/data_input_nn_shuffled_new \
  --chunk-rows 100000 --buckets 1024 --seed 42
```

Outputs include Primary chunks, `master_index.csv`, Secondary references and `reorder_manifest.json`. The dataset is not ready for split generation while `INCOMPLETE` exists.

## 2. Recover an interrupted run if needed

`resume_reorder_chunks.py` audits and recovers a shuffled dataset using the original log. It was used to complete the current shuffle. It checks metadata and sampled vectors; it does not compare every embedding exhaustively.

```bash
python data_pipeline/scripts/data_shuffling/resume_reorder_chunks.py --help
```

To invoke recovery through `reorder_chunks.py`, add `--resume --resume-log PATH_TO_LOG` and retain the original parameters.

## 3. Generate splits

Follow [data_splitting](../data_splitting/README.md). The current dataset is already shuffled and does not need this phase repeated.
