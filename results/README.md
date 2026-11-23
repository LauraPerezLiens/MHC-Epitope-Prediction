# Training outputs

Only this README is versioned. Metrics, checkpoints, logs and evaluation caches remain local.

The historical MLP launcher creates a run directory with one `chunks_N/` directory per stage:

| Artifact | Contents |
|---|---|
| `history_mlp_primary_secondary.jsonl` | Epoch-end training and STAGE/ALL evaluation metrics |
| `monitor_history.jsonl` | Fixed-sample evaluations at the configured frequency |
| `best_mlp_primary_secondary.pt` | Checkpoint selected by TEST STAGE loss |
| `last_mlp_primary_secondary.pt` | Last completed epoch, including optimizer and scheduler state |
| `recovery_mlp_primary_secondary.pt` | Intra-epoch recovery when a checkpoint interval is reached |
| `run.log` | Stage execution output |
| `eval_stage/`, `shared_global_eval/` | Fixed STAGE samples and shared ALL samples |

`shared_global_eval/` belongs to the run directory; `eval_stage/` belongs to each stage. Use a new `RESULTS` path for an independent experiment. See [MLP instructions](../neural_network/MLP/README.md) for training and resumption, and [experiment history](../docs/mlp_experiment_history.md) for recorded earlier results.


## Interpretation

The historical MLP uses TEST STAGE to select BEST. In the audited historical comparison, TEST STAGE and TEST ALL each contained 58,012 unique rows and shared 36. TEST ALL is therefore a partially overlapping diagnostic for that comparison. Report the sample, dataset, scaler, mode and checkpoint when comparing runs.

The v2 hook selects by VALIDATION loss and evaluates TEST at the end. D1 uses original observations and exact-primary partitioning. D2 remains planned. Natural LR reports histogram-based average precision. A synthetic bin collision gave 0.5 where exact ranking gave 1.0. Global ROC-AUC can also differ from the mean of per-chunk ROC-AUC values.

A checkpoint supplies training state for its own protocol. Reproduction also needs the matching dataset and split manifests, scaler, configuration, code and evaluation sample. Some diagnostic scripts replace individual CSV and JSON files at their output paths. Use a separate destination to preserve prior reports.
