# Data

- `data_input_nn/`: original embeddings for 11 datasets. Secondary indices in the shuffled dataset reference these files through absolute paths.
- `data_input_nn_shuffled/`: 1,449,852,950 globally shuffled rows in 14,499 chunks, with splits and metadata. Preserve its paths and the original embedding paths.
- `data_input_nn_shuffled_concatenated/`: concatenated, unnormalized features with 1,792 columns. Do not use while `INCOMPLETE` exists.
- `used_data/`: compressed and verified raw, intermediate and UniRef datasets. See its README for restoration instructions.

## Code and outputs

MLP code and the completed `standardizer_all_train_chunks.npz` are in `../neural_network/MLP/`. The scaler log is `../logs/scaler_sequential_20261110.log`.

Preparation scripts are in `../data_pipeline/scripts/`, reports in `../reports/`, operational logs in `../logs/`, and the environment specification in `../env/nap_env.yml`.

This directory belongs to the root `lperez_nn/` repository. The root `.gitignore` excludes datasets while retaining this README and `used_data/README.md`. There is no separate Git repository here.
