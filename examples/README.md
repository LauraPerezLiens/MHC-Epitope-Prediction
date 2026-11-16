# Synthetic MLP example

Generate and check 100 artificial embedding rows using the project's dataset loader, `ModalityStandardizer` and MLP. No biological sequences, experimental data, pretrained weights, downloads or GPU are required.

From the project root:

```bash
conda activate nap_env
python examples/synthetic_mlp.py
```

With seed 42 by default, the example writes two 50-row chunks of unnormalized `float32` features with 1,792 columns and aligned labels, group IDs and split IDs. The first feature is an artificial row marker; labels are its parity. This makes correspondence checks explicit. Splits contain 80 TRAIN, 10 VALIDATION and 10 TEST rows, balanced by class in each split.

The script reads rows in permuted order, checks metadata alignment, fits statistics using TRAIN only, saves/reloads the scaler and runs CPU inference with the real MLP architecture. Weights are randomly initialized; the example demonstrates integration, not predictive performance.

Generated files are temporary and removed when the command finishes. To retain them, select a new directory:

```bash
python examples/synthetic_mlp.py --output /tmp/synthetic_mlp_example
```

An existing output directory is refused. `--seed` controls generation; generated arrays are excluded from Git. See [data provenance and schema](../data_pipeline/docs/data_and_models.md) for the real dataset format.
