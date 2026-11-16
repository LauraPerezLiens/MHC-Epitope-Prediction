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

## CPU tests and CI

`requirements-ci.txt` is a small independent test environment: NumPy/Pandas for arrays and metadata, Biopython for BLOSUM62, SciPy/scikit-learn for metrics, and Ruff for focused correctness checks. CPU PyTorch is installed separately from its official wheel index. TensorFlow, Transformers, CUDA runtimes and pretrained models are not required by this test suite.

From the project root on Linux with Python 3.10 and the `zstd` executable available:

```bash
python3.10 -m venv /tmp/mhc-ci-env
source /tmp/mhc-ci-env/bin/activate
python -m pip install pip==26.0.1
python -m pip install torch==2.6.0 --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r env/requirements-ci.txt
python -m pip check
export CUDA_VISIBLE_DEVICES="" HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
python -m compileall -q data_pipeline neural_network examples tests
bash -n neural_network/MLP/run_shuffled_pipeline.sh
bash -n neural_network/MLP/run_chunk_ladder100_dualeval.sh
python -m ruff check --no-cache .
python -m unittest discover -s tests -t . -v
python examples/synthetic_mlp.py
```

Use a new venv path if it already contains another environment. These commands install only into the activated venv; do not run them in the research environments. Pip is pinned to the version tested with the CPU wheel index. Direct dependencies are pinned, but this is not a transitive lockfile.

The isolated installation was checked locally on Linux x86_64 with Python 3.10.13, PyTorch 2.6.0+cpu, NumPy 2.0.1, Pandas 2.3.3, SciPy 1.15.3, scikit-learn 1.7.2, Biopython 1.86 and Ruff 0.11.13. This validates the CPU test/example environment on this host, not a fresh OS installation or the full research pipeline. GitHub-hosted workflow execution remains unverified until it runs there.

The research snapshot retains Python 3.10.13, PyTorch 2.14.0, NumPy 2.0.1 and Transformers 5.17.0; its PyTorch wheel targets CUDA 13.0. ProteinUnet retains TensorFlow 2.13.0, Keras 2.13.1 and NumPy 1.24.3 in its separate environment. Package metadata checks (`pip check`) passed for both installed research environments without changing them. The full Conda snapshot still contains historical/system dependencies and has not been rebuilt from scratch in this review.
