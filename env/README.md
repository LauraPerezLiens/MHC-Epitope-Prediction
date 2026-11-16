# Runtime environment

`nap_env.yml` records the installed `nap_env` environment, synchronized on 2026-11-16 using `conda env export -n nap_env --no-builds`. It preserves Conda/Pip package versions and channels and omits the machine-specific `prefix`. This is an environment snapshot, not a lockfile; recreating it on a clean machine has not been validated.

```bash
conda env create -f env/nap_env.yml
conda activate nap_env
```

Launchers accept `PYTHON` to select another interpreter. Moving code does not install or change dependencies; running processes retain their original interpreter.

## ProteinUnet

ProteinUnet inference uses a separate environment to retain the SavedModel-compatible TensorFlow 2.13 / Keras 2 stack without changing the PyTorch environment:

```bash
conda env create -f env/proteinunet_env.yml
conda run -n proteinunet_env python data_pipeline/scripts/secondary_structure_prediction/predict_secondary_structure.py --help
```

Both `predict_secondary_structure.py` and `predict_uniref30_secondary_structure.py` use this environment. Other pipeline steps use `nap_env`. Put the model weights in `model/unet_c_ensemble/`. Keras 3 does not support loading this SavedModel with `load_model()`; see the [Keras migration guide](https://keras.io/guides/migrating_to_keras_3/).

Validated locally with the saved ProteinUnet model: both prediction scripts produced C/H/E sequences of the expected length for 25- and 1,100-residue inputs on CPU. GPU execution was not tested.
