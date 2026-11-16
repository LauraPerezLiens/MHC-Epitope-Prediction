# Training outputs

Only this README is versioned. Metrics, checkpoints, logs and evaluation caches remain local.

The MLP launcher creates a run directory with one `chunks_N/` directory per stage:

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
