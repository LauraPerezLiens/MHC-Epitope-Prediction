# Logistic regression with the MLP protocol

`train.py` delegates training to `MLP/mlp_layernorm_shuffled_ladder100_dualeval.py` with `--model-type logistic`. The model is a single `Linear(1792, 1)` layer: no hidden layers, dropout or LayerNorm. Binary cross entropy consumes logits; probabilities are their sigmoid.

The shared engine supplies exactly the same data loading, TRAIN-fitted standardizer, deterministic chunk selection/order, sampling, optimizer, scheduler, monitoring and checkpoint recovery as MLP:

- Every TRAIN batch is exactly 50% negative and 50% positive. Cycling samplers cover every source TRAIN row at least once, repeating minority rows and rounding up to complete batches. Single-class chunks use a deterministic TRAIN-only donor from the selected chunks.
- AdamW, learning rate 0.001, weight decay 0.0001 (including bias, as in MLP), batch size 8,192, seed 42.
- CosineAnnealingWarmRestarts with T_0=20, T_mult=1, minimum learning rate 0.00001.
- Fixed balanced TRAIN/TEST samples for STAGE and ALL, using MLP's exact chunk-stratified sampling code, target 29,006 rows per class and evaluation batch size 1,024. These are sampled evaluations, not full-split metrics.
- Reports and evaluations every 10 TRAIN chunks, including a final partial block. Each report includes ONLINE metrics for that block and fixed TRAIN/TEST evaluation metrics. Epoch aggregates are reported separately.
- BEST is selected by TEST STAGE BCE at epoch end, matching the existing MLP experiment. Thus TEST participates in model selection; it is not an independent final holdout. VALIDATION is not used by that experiment.

Defaults retain **all physical chunks**, **10 epochs**, **one GPU**, and the existing shuffled concatenated dataset. To reproduce the MLP launcher's ten-chunk subset too, pass `--max-chunks 10`; the shared selection function uses the same seed and salt. Feature rows and split metadata are never rewritten.

```bash
conda activate nap_env
CUDA_VISIBLE_DEVICES=0 bash neural_network/logistic_regression/run.sh
# Resume this balanced experiment:
CUDA_VISIBLE_DEVICES=0 bash neural_network/logistic_regression/run.sh --resume
```

The launcher accepts `PYTHON`, `DATA_ROOT`, `SCALER_PATH`, `RESULTS`, `EPOCHS`, `BATCH_SIZE`, `LR`, `L2` (AdamW weight decay), `DEVICE`, `GPUS` (must be 1), `LOG_EVERY` and `CHECKPOINT_EVERY`. Extra CLI options are forwarded. `DEVICE=cpu` forces CPU. The balanced engine follows the one-GPU MLP protocol; multi-GPU is not enabled. CPU/GPU checkpoints are portable.

Outputs default to `results/logistic_regression_balanced/`: `run.log`, scaler-hashed `config.json`, `monitor_history.jsonl`, `history_lr_primary_secondary.jsonl`, `best_lr_primary_secondary.pt`, `last_lr_primary_secondary.pt` and atomic intra-epoch `recovery_lr_primary_secondary.pt` every 10 chunks. A writer lock prevents duplicate runs in one directory. Epochs can be extended on resume; reporting/checkpoint intervals can change, but training and sampling configuration must stay fixed.

Metrics match MLP: BCE, accuracy, balanced accuracy, precision, recall, specificity, F1, F2, MCC, confusion counts and exact ROC AUC. ONLINE metrics use changing weights; fixed-sample evaluation uses frozen weights. Epoch ONLINE AUC is not accumulated. Initial data validation and disk evaluation-cache preparation run before the first training metrics and print their progress.

The previous natural-distribution run remains in `results/logistic_regression_all/`. Its implementation is retained as `train_natural.py` for reproducibility. Its checkpoints are incompatible with the balanced protocol, so the balanced experiment starts from random weights rather than continuing that fit.

Tests: `python -m unittest tests.test_logistic_regression_balanced tests.test_dataset_and_mlp -v`. Synthetic fixtures check exact balance, source-row coverage, one-layer architecture, ten-chunk reports, fixed balanced evaluation, model selection, optimizer/scheduler state and resuming. GPU correctness does not establish a throughput speedup; this dataset is also limited by disk I/O.
