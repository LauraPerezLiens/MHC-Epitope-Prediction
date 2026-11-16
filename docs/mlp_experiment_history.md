# MLP experiment history

## Experimental scope

The current phase is exploratory: test whether the network learns and whether training works with augmented data. Row-based partitions, TRAIN/TEST STAGE/ALL monitoring and selection by TEST STAGE are intentional. The historical results below are not a final estimate of generalization.

A future, separate evaluation may select checkpoints with VALIDATION, reserve TEST for final assessment, separate groups/proteins and compare external predictors. That protocol is not implemented here and does not revise historical partitions or selection criteria.

Historical compilation: 26 October 2026. Historical update: 28 October 2026. Archive removal: 10 November 2026.
Sections 1–13 preserve the original historical snapshot; section 14 records the later status and data preparation in progress at that time. This document is a snapshot, not a report of 100 completed epochs for every experiment.
Historical values were reconstructed from archived JSONL histories. BatchNorm figures come from the technical record retained before its outputs were deleted.

## 1. Reference configuration and how to interpret the figures

The task is binary classification using precomputed embeddings: ProtT5 with 1,024 dimensions and SecondaryBERT with 768 dimensions, for 1,792 features in total. The reference architecture is 1792 → 512 → 128 → 1, with normalization, ReLU and dropout 0.30. Training uses BCEWithLogitsLoss, AdamW, an initial learning rate of 0.001, weight decay of 0.0001 and batches of 8,192 rows, with 4,096 rows per class. The ladder scheduler uses cosine warm restarts: T0=20 epochs, Tmult=1 and a minimum learning rate of 0.00001. The seed is 42; each stage targets 100 epochs without early stopping, using one GPU per training run.

The original data comprise 11 datasets and 14,503 physical chunks. TRAIN, VALIDATION and TEST are identified by `split_id`. The agreed policy splits by row and permits groups/proteins to appear in multiple splits. It was not redefined as a grouped split. These results do not establish generalization to entirely new proteins or groups.

Each ladder stage inherits the previous stage's best weights and resets the optimizer and scheduler. These are cumulative training runs, rather than independent models trained from scratch at each size.

Unless otherwise stated, tables report the checkpoint with the lowest TEST loss within the stage, which is not necessarily the last epoch or the highest accuracy. TEST participates in checkpoint selection, so these results are exploratory. VALIDATION did not replace TEST as the selection criterion in the completed experiments.

## 2. BatchNorm: baseline and inference-statistics diagnosis

A baseline and a diagnostic run using 10 chunks and 100 epochs were completed. The symptom was a discrepancy between training and evaluation behavior. The same weights and samples were evaluated using BatchNorm running statistics and, diagnostically, batch statistics, with dropout disabled and without modifying the original model.

Documented TEST results at epoch 100:

| Normalization / evaluation | Loss | Accuracy | Recall | ROC-AUC |
|---|---:|---:|---:|---:|
| BatchNorm, running statistics | 1.880200 | 76.9167 % | 53.8600 % | 0.986282 |
| BatchNorm, batch statistics — diagnostic | 0.050603 | 98.5450 % | 98.3391 % | 0.998883 |
| LayerNorm, standard evaluation | 0.003121 | 99.9170 % | 99.8538 % | 0.999991 |

Interpretation: the normalization method used at inference strongly affected BatchNorm results. High AUC alongside worse accuracy, recall and loss also indicates that ranking examples and classifying them at a fixed threshold are different tasks. Evaluation using batch statistics was a diagnostic check, not validation of a model whose inference is independent of batch composition.

A BatchNorm ladder was also started and stopped during the 20-chunk stage. Its outputs and scripts were deleted at the user's request; no reliable numerical table remains for that stage. Subsequent experiments used LayerNorm.

## 3. Replacing BatchNorm with LayerNorm

Both normalization layers were replaced with LayerNorm. It normalizes each sample's activations without batch-dependent running means or variances. The first 10-chunk run completed 100 epochs.

- Best checkpoint: epoch 98, TEST loss 0.002926; accuracy 99.9269%; recall 99.8738%; AUC 0.999990; 3 false positives and 19 false negatives.
- Last checkpoint: epoch 100, loss 0.003121; accuracy 99.9170%; 3 false positives and 22 false negatives.
- Evaluated TEST population: 30,104 rows, with 15,052 per class.

Operational conclusion: LayerNorm resolved the large discrepancy associated with BatchNorm statistics in this experiment and was adopted for later runs. The comparison used one seed and does not establish that one normalization method is universally superior for every population.

## 4. LayerNorm and cosine ladder in increments of 10 chunks, without epoch-wise chunk shuffling

Stages used 10, 20, 30… chunks. The scaler was fitted on TRAIN from 2 chunks, and chunk order remained fixed between epochs. Samples were shuffled during training, but chunk visitation order was not. TRAIN EVAL and TEST EVAL were globally balanced using all positive rows in the stage's split and an equal number of fixed negative rows.

| Chunks | Completed epochs | Best epoch | TEST loss | Accuracy | Recall | ROC-AUC |
|---:|---:|---:|---:|---:|---:|---:|
| 10 | 100 | 98 | 0.002926 | 99.9269 % | 99.8738 % | 0.999990 |
| 20 | 100 | 100 | 0.003898 | 99.8859 % | 99.7902 % | 0.999991 |
| 30 | 100 | 100 | 0.005635 | 99.8248 % | 99.7578 % | 0.999966 |
| 40 | 100 | 100 | 0.010749 | 99.6793 % | 99.5837 % | 0.999907 |
| 50 | 100 | 100 | 0.015396 | 99.5222 % | 99.2825 % | 0.999882 |
| 60 | 100 | 100 | 0.041782 | 98.5328 % | 97.7107 % | 0.999421 |
| 70 | 100 | 100 | 0.048620 | 98.2409 % | 97.1894 % | 0.999216 |
| 80 | 100 | 100 | 0.048334 | 98.2566 % | 97.2959 % | 0.999075 |
| 90 | 71 | 60 | 0.055978 | 97.9806 % | 96.9819 % | 0.998624 |

The 90-chunk stage stopped during epoch 72, leaving 71 completed epochs. Loss and recall worsened as the ladder expanded; best-checkpoint accuracy decreased from 99.93% with 10 chunks to 97.98% in the partial 90-chunk stage. This does not establish that adding data is harmful: the evaluation population, its heterogeneity and the accumulated training history all change.

An auxiliary analysis also examined chunk composition. Dataset differences and ordering effects were proposed as explanations, but no controlled intervention isolated a single cause.

## 5. Shuffling chunk order in every epoch

A variant changed only the TRAIN chunk visitation order in each epoch, deterministically from the seed and epoch. The subset of chunks in each stage and the evaluation samples remained fixed. The first stage started from scratch; later stages inherited that run's own best checkpoint.

| Chunks | Completed epochs | Best epoch | TEST loss | Accuracy | Recall | ROC-AUC |
|---:|---:|---:|---:|---:|---:|---:|
| 10 | 100 | 93 | 0.002078 | 99.9502 % | 99.9269 % | 0.999995 |
| 20 | 100 | 95 | 0.002680 | 99.9121 % | 99.8550 % | 0.999994 |
| 30 | 100 | 95 | 0.003949 | 99.8973 % | 99.8422 % | 0.999974 |
| 40 | 100 | 96 | 0.006852 | 99.8031 % | 99.7665 % | 0.999947 |
| 50 | 100 | 77 | 0.009908 | 99.6910 % | 99.6000 % | 0.999930 |
| 60 | 8 | 8 | 0.039510 | 98.5424 % | 98.0706 % | 0.999097 |

The 60-chunk stage stopped during epoch 9. Its figures reflect only 8 completed epochs and are not equivalent to a 100-epoch run.

Best-loss comparison with and without shuffling, using completed stages in both cases:

| Chunks | Without shuffling | With shuffling | Relative loss reduction |
|---:|---:|---:|---:|
| 10 | 0.002926 | 0.002078 | 29.0 % |
| 20 | 0.003898 | 0.002680 | 31.3 % |
| 30 | 0.005635 | 0.003949 | 29.9 % |
| 40 | 0.010749 | 0.006852 | 36.3 % |
| 50 | 0.015396 | 0.009908 | 35.6 % |

The improvement was consistent across 10–50 chunks. Errors decreased from 456 to 280 with 40 chunks and from 903 to 584 with 50 chunks. The effect includes weights accumulated in previous stages; these are not five independent experiments trained from scratch.

Many best checkpoints occurred near epoch 100. Extending training to 200 epochs was proposed, but that comparison was not run. Minima tended to coincide with the ends of the 20-epoch cosine cycles.

## 6. StandardScaler: 2 chunks, a 10-chunk trial and fitting on all chunks

The original scaler used all TRAIN rows from 2 physical chunks, independently of the chunks selected for each MLP stage. A comparison using 10 chunks was prepared; its directory was eventually removed when fitting the full scaler was chosen instead. No verifiable figures for the 2-versus-10 comparison are retained here, so no quantitative conclusion is claimed.

The full scaler finished with 14,503 chunks and **1,159,882,361 TRAIN rows**. TEST and VALIDATION rows were not used to estimate means or scales.

| Difference from the 2-chunk scaler | Primary, 1,024 variables | Secondary, 768 variables |
|---|---:|---:|
| Median mean shift, in full-scaler sigma units | 0.110 | 0.215 |
| Median relative scale difference | 5.11 % | 4.70 % |
| Maximum relative scale difference | 28.87 % | 18.65 % |
| Variables with scale differences greater than 10 % | 169 —16.5 %— | 76 —9.9 %— |
| RMS difference between normalized values across all TRAIN | 0.179 | 0.236 |

Means and scales changed across all 1,792 features. The difference justified a training comparison but did not establish an improvement in advance. The full scaler was used by the run described as current in this historical snapshot.

## 7. Shuffled ladder with the full scaler

A separate copy of the shuffled training implementation loaded the full scaler without recalculating it and wrote to an independent directory. The 10-chunk stage started from scratch.

| Chunks | Completed epochs | Best epoch | TEST loss | Accuracy | Recall | ROC-AUC |
|---:|---:|---:|---:|---:|---:|---:|
| 10 | 100 | 96 | 0.003006 | 99.9336 % | 99.9070 % | 0.999988 |
| 20 | 100 | 95 | 0.002944 | 99.9167 % | 99.8581 % | 0.999996 |
| 30 | 20 | 20 | 0.010867 | 99.6532 % | 99.4496 % | 0.999915 |

The 10- and 20-chunk stages completed 100 epochs. The 30-chunk stage stopped during epoch 21, with 20 epochs completed. Compared with shuffling and the 2-chunk scaler:

- 10 chunks: loss 0.002078 → 0.003005; accuracy 99.9502% → 99.9336%.
- 20 chunks: loss 0.002680 → 0.002944; accuracy 99.9121% → 99.9167%.

Therefore, **using the full scaler did not produce a uniform improvement**: loss was higher in both comparable stages, while accuracy improved slightly with 20 chunks. One seed and small differences do not establish general superiority. The partial 30-chunk stage is not treated as completed.

## 8. Direct training with all 14,503 chunks

Training was launched from scratch with LayerNorm, shuffling, the full scaler, a target of 100 epochs and all chunks included from the first epoch. TRAIN ONLINE remained 50/50. TRAIN EVAL and TEST EVAL were added after each chunk using fixed global samples of 58,012 rows: 29,006 positive and 29,006 negative. This monitor tracked the same population as more data passed through training.

The first implementation kept indices and samples in RAM; approximately 10 GiB was observed during preparation. It was stopped and changed to batchwise reading with disk caches. Global accumulation of logits/predictions was later removed, retaining epoch counters and exact AUC in the monitors. Approximately 1–1.7 GiB RAM and 563 MiB VRAM were observed during training; these are point measurements, not guaranteed limits.

Initially, evaluation on all balanced rows was retained at the end of each epoch. After all 14,503 chunks of epoch 1 had finished, that phase continued for approximately one day without progress messages. The run was stopped, restored from chunk 14,500, and the last 3 chunks were repeated. The final evaluation was replaced by the fixed monitors already computed. This allowed best/last checkpoints to be saved and epoch 2 to begin.

| Snapshot | TEST loss | Accuracy | Recall | Specificity | ROC-AUC |
|---|---:|---:|---:|---:|---:|
| End of epoch 1, saved checkpoint | 0.649533 | 61.47 % | 56.53 % | 66.42 % | 0.665027 |
| Last monitor before stopping, epoch 2/chunk 601 | 0.645867 | 62.06 % | 70.67 % | 53.45 % | 0.670063 |

The run stopped with 1 completed epoch and a recoverable checkpoint through chunk 600 of epoch 2. The saved best checkpoint corresponds to epoch 1; best was not saved after every chunk. This experiment did not complete 100 epochs.

Interpretation: the model learned relative to initialization, but global performance stabilized around AUC 0.67, with fluctuating recall/specificity. It did not reach the approximately 99% figures seen in small experiments. Those evaluations use different populations and epoch counts and are not directly comparable. Continuing was rejected because of cost and insufficient performance to justify the experiment, rather than a demonstrated execution failure.

## 9. Performance, concurrency and operational changes

GPU, CPU, disk and RAM were inspected. The three concurrent training runs used different GPUs. No global CPU saturation was observed; there was substantial system/data-management work and low instantaneous GPU activity.

The other two ladders were stopped to investigate interference. A short subsequent sample included chunks taking 7–9 seconds, but also a 69-second spike. The comparison was not sufficiently controlled to attribute sustained acceleration to removing concurrency.

Epoch-duration estimates varied by segment, approximately 40–79 hours, plus the final global evaluation when it existed. These were not measured durations for 100 completed epochs. The 23-second field in the recovered epoch-1 closing record measures only the repeated segment, not the whole epoch.

Atomic checkpoints, PyTorch/CUDA random state, intra-epoch recovery, separate best/last/recovery checkpoints and duplicate-history cleanup after resuming were added. Automated checks validated balancing, fixed samples, evaluation reproducibility and correct best-checkpoint selection. These were software checks, not additional predictive-quality experiments.

## 10. Experiment at the time: ladder in increments of 100 chunks with dual evaluation

Planned stages: 100, 200, 300… 14,500 and 14,503 chunks; 100 epochs per stage. LayerNorm, shuffling, the full scaler, cosine scheduling and the remaining configuration were retained. The first stage starts from scratch; the next inherits the previous stage's TEST STAGE best weights and resets the optimizer/scheduler.

Four fixed 50/50 samples are evaluated after every chunk:

| Evaluation, 100-chunk stage at this snapshot | Positive rows | Negative rows | Total |
|---|---:|---:|---:|
| TRAIN EVAL STAGE —100 chunks— | 29,006 | 29,006 | 58,012 |
| TEST EVAL STAGE —100 chunks— | 28,873 | 28,873 | 57,746 |
| TRAIN EVAL ALL —14,503 chunks— | 29,006 | 29,006 | 58,012 |
| TEST EVAL ALL —14,503 chunks— | 29,006 | 29,006 | 58,012 |

ALL samples are reused across stages. STAGE samples remain fixed within a stage and change when its chunk subset expands. Rows are sampled without replacement using per-chunk quotas; evaluation does not traverse every row or necessarily weight each chunk by its size. TEST STAGE selects the best checkpoint; ALL is diagnostic only. TRAIN ALL includes chunks not yet trained in that stage, so it is not solely error on examples already used to fit weights.

Snapshot at compilation: 22 completed epochs, with epoch 23/chunk 38 in progress. The best epoch-end record by TEST STAGE loss was epoch 20:

| Evaluation, epoch 20 | Loss | Accuracy | Recall | Specificity | ROC-AUC |
|---|---:|---:|---:|---:|---:|
| TRAIN STAGE | 0.317686 | 85.44 % | 80.49 % | 90.39 % | 0.936854 |
| TEST STAGE | 0.333323 | 84.83 % | 79.38 % | 90.29 % | 0.930583 |
| TRAIN ALL | 1.079969 | 54.03 % | 22.47 % | 85.60 % | 0.590878 |
| TEST ALL | 1.072312 | 54.28 % | 22.78 % | 85.77 % | 0.593038 |

Local TEST improved from loss 0.672914, accuracy 58.26% and AUC 0.634662 in epoch 1 to loss 0.333323, accuracy 84.83% and AUC 0.930583 in epoch 20. However, TEST ALL changed from loss 0.686453 and AUC 0.611053 to loss 1.072312 and AUC 0.593038.

This is an important result: **improving within the 100 chunks was not translating into improvement across all chunks**. Global recall at that epoch was 22.78%, with specificity 85.77%: many global positive examples tended to be classified as negative. The difference is not explained solely by local TRAIN-versus-TEST behavior; it may reflect specialization to the subset or distribution shifts between chunks. The causal mechanism was not isolated.

After the cosine restart at epoch 21, TEST STAGE temporarily worsened to loss 0.426520 and AUC 0.882531; epoch 22 improved again to 0.388790 and 0.907267. At this snapshot, the first stage had not completed and the 200-chunk stage had not begun.

## 11. Proposals that were not completed experiments

- Compare one and two GPUs with the same global batch: proposed, not performed as a quality comparison. Using different GPUs for independent runs is not training one model on two GPUs.
- Evaluate or train at natural prevalence without balancing: discussed; the final request retained 50/50 balancing. No balanced-versus-natural comparison results are available.
- Extend a stage to 200 epochs: proposed after observing late best checkpoints, but not performed.
- Reduce the learning rate or update cosine scheduling per minibatch/chunk: a hypothesis, not a separate experiment with available results.
- Mix/interleave minibatches from several chunks using a small buffer: proposed to investigate adaptation to the most recent chunk, but not implemented as an experiment.
- Select checkpoints using VALIDATION: recommended for an independent final evaluation; TEST STAGE was retained at the user's request.

## 12. Accumulated conclusions and limitations

1. The BatchNorm diagnosis showed a substantial problem when changing inference statistics; LayerNorm clearly improved the 10-chunk experiment.
2. Shuffling improved loss in comparable completed stages using 10–50 chunks.
3. The full scaler appreciably changed normalization but did not uniformly improve early-stage metrics relative to the 2-chunk scaler.
4. Near-perfect results on small subsets did not transfer to direct all-chunk training or evaluation across all chunks.
5. Dual evaluation distinguishes local learning from global performance: at this snapshot, local improvement was substantial and global transfer was limited.
6. RAM usage and epoch-end cost were substantially reduced, improving feasibility without independently correcting predictive quality.
7. There is no multiple-seed comparison, controlled LR/chunk-mixing experiment, DDP quality experiment or independent evaluation on new groups.

## 13. Sources used to reconstruct the results

- `archive/legacy_experiments_2026-10-26.tar.gz` (deleted on 10 November 2026): EXPERIMENTS.md, earlier ladders, epoch histories and the all-chunk experiment archive.
- `archive/auxiliary_tools_and_scaler_analysis.tar.gz` (deleted on 10 November 2026): scaler comparison, counts/provenance and checking tools.
- Historical directory `chunk_ladder100_layernorm_cosine_shuffled_allscaler_dualeval_100epochs_1GPU/` (deleted on 10 November 2026; final results in section 16): epoch history, per-chunk monitoring, logs and checkpoints active at the time.

Histories contain more decimal places than logs. Figures are presented rounded. Interrupted stages are identified, and their results are not extrapolated to 100 epochs. Archiving or deleting an auxiliary file does not itself imply that the experiment failed scientifically.

## 14. Update on 28 October: global shuffling before split generation

### Previous training status

During the 28 October review, no MLP training was active and all four RTX 3090 GPUs had no compute processes. The 100-chunk-increment ladder log had advanced beyond the snapshot in section 10: its last entry was epoch 30/100, chunk 93/200, within the 200-chunk stage. The log was last modified on 27 October at 16:06 Madrid time. No final message established why the run stopped. This per-chunk entry does not certify an epoch-end result or a saved checkpoint.

Last TEST metrics visible in that monitor:

| Population | Loss | Accuracy | Recall | ROC-AUC |
|---|---:|---:|---:|---:|
| STAGE, 200 chunks | 0.168707 | 93.49 % | 90.89 % | 0.9842 |
| ALL, 14,503 chunks | 1.441980 | 53.19 % | 16.23 % | 0.5836 |

These are the last monitor's values, not a best-checkpoint selection or final results. The local/global performance gap persists. The new preparation aims to distribute data from different sources across chunks; it does not yet demonstrate that this intervention improves model metrics.

### What was running at that snapshot

`reorder_chunks.py` was running from the project root in `nap_env`:

```bash
python -u reorder_chunks.py --root data_input_nn \
  --output data_input_nn_shuffled --chunk-rows 100000 --buckets 1024 --seed 42
```

Output was recorded in `reorder_chunks.log`. The PID observed in that session was 2314483; it identifies that particular run and is not a fixed identifier.

Shuffling in earlier experiments changed chunk visitation order within each epoch while preserving chunk composition. This script physically mixes rows and their Primary embeddings across the 11 datasets before creating a new split. It does not train a model or perform 50/50 balancing.

### Algorithm, integrity and files

1. Locate original `master_index.csv` files in path order. Check columns, binary labels, consecutive indices, correspondence with Primary embeddings, and compatible dimensions and types across sources.
2. Preserve provenance in `source_dataset_id`, `source_chunk_id`, `source_row_idx_in_chunk` and `source_group_id`. Offset `group_id` per source to prevent collisions when looking up SecondaryBERT. Retain `protein_group_id`, which must be interpreted together with the source dataset.
3. `PARTITION` phase: randomly assign each sample to one of 1,024 buckets using seed 42. Store metadata in `_shuffle_work/000000.csv` and corresponding Primary embeddings in `_shuffle_work/000000.bin`, in the same order. BIN files are raw binary without headers; reading requires the type and dimensions. The filename number identifies a temporary bucket.
4. After distributing all inputs, permute rows within each bucket and write final chunks of 100,000 samples, except for a possible smaller last chunk. Emit `WRITE chunk=...` messages. Store embeddings in `mixed/classification_mixed_ProtT5_chunks/chunk_XXXXXX_X.npy` and metadata in its `master_index.csv`, with new chunk and row indices.
5. Delete each CSV/BIN pair after consuming it. Check that the emitted total equals the input total, write `reorder_manifest.json`, and remove `_shuffle_work` and `INCOMPLETE` on successful completion.

Each row is emitted once, without sampling with replacement. Random assignment does not guarantee exact class, species or MHC proportions in each chunk. Reproducibility requires the same inputs, seed and bucket count.

Secondary embeddings are not copied: the combined index in `mixed/classification_mixed_SecondaryBERT_by_group` references the original files through absolute paths. Those files must remain available. The script does not overwrite inputs and requires a new, separate output directory. At this historical snapshot, it did not implement automatic resumption of partial runs.

### Resources and monitoring for this run

The job uses CPU and disk, not GPU. Approximately 30% of one core was observed as a cumulative average, with higher instantaneous readings. `top`'s `TIME+` is accumulated CPU time; `ps`'s `ELAPSED` is wall-clock duration, including disk waits. RAM does not hold all embeddings: processing retains one original chunk and, during the second phase, one bucket's metadata/permutation and the blocks required to form an output chunk.

Buckets occupied approximately 2.8 TB during early checks; their size changes during execution. Capacity is needed for temporary files and final outputs in addition to originals. Temporary files are progressively deleted during the second phase.

| Check on 28 October, Madrid time | Partitioned rows | Observation |
|---|---:|---|
| 13:01 | 745,020,080 | Starting source=3 |
| 13:49 | 778,520,080 | PARTITION continues |
| 13:54 | 782,120,080 | Similar throughput with other tasks active |
| 15:40 | 856,520,080 | Approximately 59 % of PARTITION |
| 16:13 | 879,130,530 | source=4, chunk=36; process active |

The last check corresponds to approximately 22 h 41 min of execution. Total input was estimated at approximately 1.450 billion rows; the final manifest would provide the definitive count. With that estimate, the last progress reading represented approximately 61% of partitioning, not 61% of total job duration.

Observed throughput was approximately 690,000–703,000 rows per minute. New STAR/Scipion tasks did not produce appreciable slowdown between the compared checks; that does not guarantee absence of later interference. At the review, 146 GiB RAM was available without memory pressure, and disk waits were observed without isolating their cause. At 15:40, 28 TB remained free.

At 16:13, extrapolating the observed rate suggested approximately 13.5–14 hours to finish PARTITION. The second phase had not yet been timed. The discussed estimate of another 15–35 hours for that phase was indicative, not validated. An estimated completion date is not a guarantee; phase percentages must not be added as though both phases had equal costs.

To inspect progress without modifying data:

```bash
tail -n 10 reorder_chunks.log
ps -p 2314483 -o pid,etime,time,%cpu,%mem,stat,args
```

### Steps pending after shuffling

While `data_input_nn_shuffled/INCOMPLETE` exists, the output is not ready for splitting or training. The planned sequence, still pending at this historical update, was:

```bash
python split_data.py --root data_input_nn_shuffled --seed 42
python check_master_split.py --root data_input_nn_shuffled --skip-metadata
python prepare_chunk_metadata.py --root data_input_nn_shuffled
python check_master_split.py --root data_input_nn_shuffled
```

The agreed policy remains a random row split, stratified by label within each chunk, approximately 80/10/10. Groups and proteins may appear in multiple splits. Shuffling does not turn evaluation into a test of generalization to new groups or proteins.

Future training must use the new root, fresh initial weights and a scaler fitted exclusively on the new TRAIN rows. The historical scaler must not be reused as if it belonged to the new split. At the date of this update, no predictive results had been generated for the shuffled dataset.

Sources for this update: `reorder_chunks.py`, `reorder_chunks.log`, the `chunks_200` `run.log`, the workflow documented in the root README, and point checks of processes, memory, disk and GPU. `test_reorder_chunks.py` existed as a synthetic integration test at that time. This documentary update does not claim full validation of real data or a new test execution.

## 15. Historical archive removal on 10 November 2026

At the user's request, the entire `archive/` directory was deleted. Experiment results, configurations and limitations remain documented in sections 1–14. Terms such as “current”, “active” and “in progress” in those sections refer to their historical snapshots and do not certify processes active today.

Two compressed archives and `cleanup_manifest.json` were removed. At that cleanup, no results directory outside `archive/`, embedding or historical scaler retained as `standardizer_legacy_all_train_chunks.npz` was deleted. Checkpoints, full logs and scripts stored only in the compressed archives are no longer available to restore or reproduce those runs exactly. This summary preserves conclusions and metrics; it does not replace weights or per-epoch data. No new results are claimed from that cleanup.

Inventory of removed archives, inspected before deletion:

| Archive | Contained files | Compressed bytes | Contents |
|---|---:|---:|---|
| `legacy_experiments_2026-10-26.tar.gz` | 146 | 674,853,830 | LayerNorm ladders without/with shuffling, full scaler, all-chunk trial, best/last/recovery checkpoints, metrics, logs, plots, documentation and historical scripts (including dataset.py). |
| `auxiliary_tools_and_scaler_analysis.tar.gz` | 12 | 221,126 | Earlier sampling and dual-evaluation tests, compare_scaler_all_chunks.py, documentation and analysis of the 2-chunk versus full scaler. |

File families in the main archive (number of files):

- `EXPERIMENTS.md`: 1.
- `README_allchunks_lowmemory.md`: 1.
- `allchunks_layernorm_cosine_shuffled_allscaler_100epochs_1GPU`: 14.
- `analysis_chunk_ladder_seed42`: 4.
- `analyze_chunk_ladder.py`: 1.
- `chunk_ladder_layernorm_cosine_100epochs_1GPU`: 59.
- `chunk_ladder_layernorm_cosine_shuffled_100epochs_1GPU`: 37.
- `chunk_ladder_layernorm_cosine_shuffled_allscaler_100epochs_1GPU`: 18.
- `chunk_ladder_layernorm_cosine_shuffled_allscaler_launcher.log`: 1.
- `chunk_ladder_layernorm_cosine_shuffled_launcher.log`: 1.
- `mlp_baseline_layernorm.py`: 1.
- `mlp_baseline_layernorm_shuffled.py`: 1.
- `mlp_baseline_layernorm_shuffled_allscaler.py`: 1.
- `mlp_layernorm_shuffled_allchunks_monitor.py`: 1.
- `run_allchunks_shuffled_allscaler_monitor.sh`: 1.
- `run_chunk_ladder_layernorm.sh`: 1.
- `run_chunk_ladder_layernorm_shuffled.sh`: 1.
- `run_chunk_ladder_layernorm_shuffled_allscaler.sh`: 1.
- `dataset.py`: 1.

Auxiliary archive contents:

- `tests/test_ladder100_dualeval.py`.
- `tests/test_ladder100_sampling.py`.
- `compare_scaler_all_chunks.py`.
- `README_ladder100_dualeval.md`.
- `archive/README.md`.
- `analysis_scaler_2_vs_all/progress.npz`.
- `analysis_scaler_2_vs_all/status.json`.
- `analysis_scaler_2_vs_all/standardizer_reference_2chunks.npz`.
- `analysis_scaler_2_vs_all/comparison.json`.
- `analysis_scaler_2_vs_all/chunks.json`.
- `analysis_scaler_2_vs_all/analysis.lock`.
- `analysis_scaler_2_vs_all/run.log`.

Original cleanup-manifest record:

- It inventoried 145 archived entries. The main archive actually contained 146 files; the actual contents were used for this removal.
- It recorded these earlier deletions: `compare_scalers_2_vs_10.py`, `test_allchunks_lowmemory.py`, `test_epoch_finish_resume.py`, `__pycache__`.
- Its `kept_active` field historically identified `chunk_ladder100_layernorm_cosine_shuffled_allscaler_dualeval_100epochs_1GPU`; that directory outside `archive/` was not modified in this cleanup.

SHA-256 values of the archives before removal (identifiers for deleted files, not backups):

- `legacy_experiments_2026-10-26.tar.gz`: `6e6b1dbe259eaf0d1d0f775651583529bbf66134e69b339fab49d1fe2d8ee7df`.
- `auxiliary_tools_and_scaler_analysis.tar.gz`: `2f4bd348806c9d43a03aadefcd030fa2d621619890249d9361bbeb9877e4bd20`.

The main archive checksum matched the value recorded in the original manifest.

## 16. Final documentation and removal of the last earlier experiment (10 November 2026)

At the user's request, `chunk_ladder100_layernorm_cosine_shuffled_allscaler_dualeval_100epochs_1GPU/`, approximately 2.4 GiB, was reviewed and deleted. No active training run was using this directory. Checkpoints, logs, JSONL histories, samples and STAGE/ALL evaluation caches were removed. Results are preserved here; weights and exact per-sample evaluations can no longer be restored from that directory. Neither embeddings nor the new scaler then being calculated in `chunk_ladder100_mixed_shuffled_20261110/` were modified.

This section updates the partial snapshots in sections 10 and 14. The experiment used the 11 original datasets (14,503 chunks) before physical global shuffling: Primary+Secondary, LayerNorm, 50/50 TRAIN batches of 8,192 rows, one GPU, epoch-wise shuffled chunk order and best-checkpoint selection by TEST STAGE loss. STAGE and ALL are fixed balanced samples; ALL is not evaluation on every row. The 200-chunk stage inherits the 100-chunk stage's best weights and resets the optimizer and scheduler according to the ladder policy documented above. These are not two independent training runs. TEST participates in model selection.

### chunks_100: status, best epoch-end record and last epoch-end record

- Completed epochs: **100**. Per-chunk monitor records: 10,000.
- Best epoch-end record by TEST STAGE loss: epoch **100**, loss **0.038097077**.
- Last epoch-end record: epoch 100. Last monitor: epoch 100, chunk 100.
- `completed_100_epochs.ok` marker: present.

| Epoch-end record | Population | N | Loss | Accuracy % | Precision % | Recall % | Specificity % | F1 | F2 | MCC | ROC-AUC | TP | TN | FP | FN |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Best, epoch 100 | train_eval_stage | 58012 | 0.030855553 | 99.043301 | 98.960592 | 99.127767 | 98.958836 | 0.990441088 | 0.990942866 | 0.980867427 | 0.999392773 | 28753 | 28704 | 302 | 253 |
| Best, epoch 100 | test_eval_stage | 57746 | 0.038097077 | 98.715063 | 98.823284 | 98.604232 | 98.825893 | 0.987136368 | 0.986479650 | 0.974303644 | 0.999086448 | 28470 | 28534 | 339 | 403 |
| Best, epoch 100 | train_eval_all | 58012 | 2.616237518 | 52.554644 | 64.012859 | 11.669999 | 93.439288 | 0.197410626 | 0.139516289 | 0.088756119 | 0.585381160 | 3385 | 27103 | 1903 | 25621 |
| Best, epoch 100 | test_eval_all | 58012 | 2.621692819 | 52.520168 | 64.079353 | 11.470041 | 93.570296 | 0.194572782 | 0.137234359 | 0.088283762 | 0.585284694 | 3327 | 27141 | 1865 | 25679 |
| Last, epoch 100 | train_eval_stage | 58012 | 0.030855553 | 99.043301 | 98.960592 | 99.127767 | 98.958836 | 0.990441088 | 0.990942866 | 0.980867427 | 0.999392773 | 28753 | 28704 | 302 | 253 |
| Last, epoch 100 | test_eval_stage | 57746 | 0.038097077 | 98.715063 | 98.823284 | 98.604232 | 98.825893 | 0.987136368 | 0.986479650 | 0.974303644 | 0.999086448 | 28470 | 28534 | 339 | 403 |
| Last, epoch 100 | train_eval_all | 58012 | 2.616237518 | 52.554644 | 64.012859 | 11.669999 | 93.439288 | 0.197410626 | 0.139516289 | 0.088756119 | 0.585381160 | 3385 | 27103 | 1903 | 25621 |
| Last, epoch 100 | test_eval_all | 58012 | 2.621692819 | 52.520168 | 64.079353 | 11.470041 | 93.570296 | 0.194572782 | 0.137234359 | 0.088283762 | 0.585284694 | 3327 | 27141 | 1865 | 25679 |

TEST results for every epoch-end record (STAGE and ALL, using the same weights within each row):

| Epoch | STAGE loss | STAGE acc % | STAGE recall % | STAGE ROC-AUC | ALL loss | ALL acc % | ALL recall % | ALL ROC-AUC |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0.672913923 | 58.263776 | 43.601288 | 0.634661627 | 0.686453207 | 56.314211 | 41.456940 | 0.611052573 |
| 2 | 0.680338583 | 57.579746 | 54.822845 | 0.615357352 | 0.703793639 | 55.014480 | 49.058815 | 0.581337887 |
| 3 | 0.640300871 | 62.925571 | 70.155509 | 0.686571442 | 0.665515994 | 59.665242 | 65.307178 | 0.630719156 |
| 4 | 0.629219229 | 64.028677 | 57.766772 | 0.703366847 | 0.683494786 | 58.744742 | 49.651796 | 0.630869604 |
| 5 | 0.662407749 | 60.478648 | 39.410522 | 0.687994372 | 0.727681447 | 56.269393 | 32.300214 | 0.624770218 |
| 6 | 0.599945484 | 66.311086 | 76.476293 | 0.741893144 | 0.682483854 | 58.660277 | 63.428256 | 0.618695208 |
| 7 | 0.591881807 | 67.047068 | 49.977488 | 0.759115002 | 0.754274506 | 56.269393 | 29.835207 | 0.618741143 |
| 8 | 0.557019779 | 70.202265 | 62.141101 | 0.784363483 | 0.754938784 | 57.436392 | 38.660967 | 0.618751369 |
| 9 | 0.565367277 | 69.869775 | 57.510477 | 0.784392175 | 0.787765344 | 56.078053 | 32.565676 | 0.617399674 |
| 10 | 0.502759360 | 73.882174 | 68.222907 | 0.830353524 | 0.748298552 | 56.215955 | 35.323726 | 0.605302716 |
| 11 | 0.490420720 | 74.373983 | 64.278045 | 0.838227947 | 0.859563541 | 54.383576 | 26.418672 | 0.595233362 |
| 12 | 0.450187057 | 77.293665 | 78.758702 | 0.867715967 | 0.790200591 | 56.988209 | 41.805144 | 0.607791132 |
| 13 | 0.447292643 | 77.944793 | 79.880858 | 0.872212629 | 0.814728938 | 56.652072 | 42.215404 | 0.606637104 |
| 14 | 0.404690629 | 80.426350 | 77.175908 | 0.893291355 | 0.960955110 | 55.814314 | 32.331242 | 0.601549133 |
| 15 | 0.387263670 | 81.380529 | 73.258754 | 0.905269508 | 0.989898541 | 54.073295 | 22.557402 | 0.593665949 |
| 16 | 0.367445242 | 82.535587 | 75.087452 | 0.914876682 | 1.017661042 | 53.850927 | 21.923050 | 0.594334787 |
| 17 | 0.363423144 | 82.854224 | 72.437918 | 0.922223140 | 1.100788600 | 53.423430 | 17.423981 | 0.595570473 |
| 18 | 0.350848901 | 83.617913 | 75.018183 | 0.925496106 | 1.095944058 | 53.645797 | 18.844377 | 0.591461590 |
| 19 | 0.335749448 | 84.741800 | 79.191632 | 0.929549427 | 1.058550971 | 54.293939 | 22.981452 | 0.593601520 |
| 20 | 0.333323029 | 84.833582 | 79.382122 | 0.930582740 | 1.072312360 | 54.276701 | 22.784941 | 0.593038084 |
| 21 | 0.426519558 | 78.756970 | 70.927856 | 0.882531063 | 0.927052675 | 54.316348 | 24.867269 | 0.591507078 |
| 22 | 0.388790154 | 81.875801 | 82.104388 | 0.907266772 | 0.853908066 | 55.991864 | 36.244225 | 0.598497486 |
| 23 | 0.387528279 | 81.889655 | 74.180030 | 0.905098130 | 1.000292474 | 54.502517 | 23.784734 | 0.592663992 |
| 24 | 0.364037979 | 83.349496 | 82.409171 | 0.917153373 | 0.924542412 | 55.364407 | 32.638075 | 0.599975413 |
| 25 | 0.346507927 | 83.929623 | 82.139023 | 0.923873070 | 1.035366590 | 53.681997 | 26.377301 | 0.585139661 |
| 26 | 0.314148536 | 86.170471 | 81.598725 | 0.943633977 | 1.003786287 | 53.266566 | 21.274909 | 0.584872049 |
| 27 | 0.316646104 | 86.075226 | 89.038202 | 0.942608344 | 1.116378031 | 56.091843 | 35.727091 | 0.602241399 |
| 28 | 0.337926780 | 85.375610 | 76.001801 | 0.943817003 | 1.515161077 | 53.076950 | 15.696752 | 0.583349042 |
| 29 | 0.252988992 | 89.036470 | 83.150348 | 0.963503614 | 1.292644953 | 53.351031 | 16.727574 | 0.591296705 |
| 30 | 0.287166976 | 87.384408 | 76.510927 | 0.968336651 | 1.659478025 | 52.146108 | 9.153279 | 0.588012772 |
| 31 | 0.220174577 | 90.839192 | 86.554913 | 0.972297680 | 1.357216692 | 53.240709 | 16.579328 | 0.589176852 |
| 32 | 0.212998288 | 90.887681 | 84.248260 | 0.978794512 | 1.584084854 | 52.527063 | 11.263187 | 0.585916526 |
| 33 | 0.200171701 | 91.640979 | 85.934957 | 0.980176996 | 1.661575253 | 52.770117 | 12.294008 | 0.589514599 |
| 34 | 0.212295277 | 90.811485 | 83.507083 | 0.981954280 | 1.816879804 | 52.383990 | 10.056540 | 0.595358286 |
| 35 | 0.171982286 | 92.858380 | 87.735947 | 0.985952156 | 1.721811643 | 52.459836 | 11.052886 | 0.584839461 |
| 36 | 0.148990848 | 94.250684 | 92.612475 | 0.986846758 | 1.556608679 | 53.351031 | 17.358478 | 0.588327996 |
| 37 | 0.148421984 | 94.068853 | 91.126658 | 0.987674488 | 1.694514174 | 53.125215 | 14.462525 | 0.589306144 |
| 38 | 0.137925806 | 94.678419 | 93.329408 | 0.988737738 | 1.593244889 | 53.395849 | 17.192995 | 0.588411035 |
| 39 | 0.144979509 | 94.224708 | 90.666020 | 0.989096996 | 1.779917725 | 52.739088 | 12.352617 | 0.589155332 |
| 40 | 0.138342595 | 94.602224 | 91.864372 | 0.989420549 | 1.722838800 | 52.973523 | 13.673033 | 0.586735743 |
| 41 | 0.216945727 | 91.299830 | 90.974267 | 0.972612653 | 1.230429777 | 54.209474 | 23.767496 | 0.593127453 |
| 42 | 0.203852719 | 91.481661 | 90.510165 | 0.975519550 | 1.351905910 | 53.859546 | 21.571399 | 0.589215561 |
| 43 | 0.228096083 | 90.591556 | 91.123195 | 0.969517589 | 1.226693898 | 53.068331 | 24.257050 | 0.567912948 |
| 44 | 0.300104108 | 87.323797 | 75.509992 | 0.981512334 | 2.206067321 | 51.485899 | 5.716059 | 0.582219536 |
| 45 | 0.220001614 | 90.518824 | 83.642157 | 0.978697327 | 1.639349875 | 52.687375 | 12.052679 | 0.589556215 |
| 46 | 0.177304296 | 93.047137 | 93.121601 | 0.981913473 | 1.388300092 | 53.957802 | 22.660829 | 0.588219924 |
| 47 | 0.168278836 | 93.258408 | 94.018633 | 0.983782144 | 1.464138342 | 53.976763 | 23.040061 | 0.588325432 |
| 48 | 0.150639606 | 94.046341 | 93.343262 | 0.986517957 | 1.559028460 | 53.230366 | 18.489278 | 0.584252170 |
| 49 | 0.138321732 | 94.453295 | 91.646175 | 0.989651309 | 1.762673161 | 52.578777 | 13.028339 | 0.583144386 |
| 50 | 0.154504198 | 93.623801 | 88.820005 | 0.991054576 | 2.264851967 | 52.297800 | 9.928980 | 0.588668909 |
| 51 | 0.143864848 | 94.191805 | 90.645239 | 0.990018333 | 1.874523202 | 52.237468 | 11.197683 | 0.583104088 |
| 52 | 0.144696163 | 94.061926 | 89.575036 | 0.991407727 | 1.942647680 | 52.315038 | 10.353030 | 0.590901248 |
| 53 | 0.096576591 | 96.524435 | 96.384165 | 0.994457488 | 1.822597396 | 53.502724 | 17.637730 | 0.592971826 |
| 54 | 0.130057182 | 94.597028 | 90.132650 | 0.994882474 | 2.261221881 | 51.965111 | 7.736330 | 0.590258719 |
| 55 | 0.088843986 | 96.875974 | 97.419735 | 0.995713236 | 1.757770079 | 53.599255 | 19.209819 | 0.584441835 |
| 56 | 0.084958436 | 96.917535 | 95.535622 | 0.996237854 | 2.003322275 | 52.792526 | 12.169896 | 0.588746058 |
| 57 | 0.079126314 | 97.163440 | 96.159041 | 0.996617314 | 2.006324053 | 52.701165 | 12.535338 | 0.584517647 |
| 58 | 0.075296192 | 97.341807 | 97.159976 | 0.996633885 | 1.971268859 | 53.321727 | 15.893263 | 0.589899278 |
| 59 | 0.073679176 | 97.411076 | 96.778998 | 0.996816750 | 2.048070029 | 52.908019 | 13.697166 | 0.586898913 |
| 60 | 0.073467276 | 97.364320 | 96.529630 | 0.996935018 | 2.094950896 | 52.770117 | 12.611184 | 0.585457914 |
| 61 | 0.144405733 | 94.430783 | 95.656842 | 0.988632673 | 1.507357827 | 53.430325 | 22.309177 | 0.578771794 |
| 62 | 0.133850565 | 94.861982 | 95.376303 | 0.990039900 | 1.530404632 | 53.728539 | 21.143901 | 0.589349265 |
| 63 | 0.182945354 | 92.279985 | 85.543587 | 0.991181710 | 2.222050290 | 52.028891 | 7.829415 | 0.596629984 |
| 64 | 0.115254503 | 95.672428 | 96.256018 | 0.992266830 | 1.676000245 | 53.778529 | 20.806040 | 0.585959965 |
| 65 | 0.124764440 | 95.384962 | 96.792851 | 0.992160703 | 1.512139561 | 53.640626 | 22.674619 | 0.581662456 |
| 66 | 0.115620566 | 95.483670 | 94.548540 | 0.991990696 | 1.877305964 | 53.504447 | 17.196442 | 0.594264592 |
| 67 | 0.102206564 | 96.190212 | 95.926991 | 0.993660044 | 1.838837623 | 53.968145 | 18.858167 | 0.594827686 |
| 68 | 0.099680420 | 96.134797 | 95.057666 | 0.994064346 | 1.948351188 | 52.885610 | 15.114114 | 0.583171502 |
| 69 | 0.104069962 | 95.823087 | 92.667890 | 0.996119555 | 2.326305899 | 52.159898 | 9.046404 | 0.590313570 |
| 70 | 0.092385578 | 96.332213 | 93.956291 | 0.996252628 | 2.279867873 | 52.349514 | 10.366821 | 0.588818345 |
| 71 | 0.096114032 | 96.586777 | 97.721054 | 0.995294756 | 1.684508017 | 53.404468 | 19.747638 | 0.580837201 |
| 72 | 0.093262840 | 96.335677 | 93.641118 | 0.996827864 | 2.489569814 | 52.104737 | 8.567193 | 0.585920206 |
| 73 | 0.069231438 | 97.485540 | 96.380702 | 0.997405177 | 2.317719653 | 52.689099 | 11.763083 | 0.592616002 |
| 74 | 0.060933386 | 97.987739 | 98.192083 | 0.997934720 | 1.982381392 | 53.123492 | 15.758809 | 0.587405018 |
| 75 | 0.056965499 | 98.015447 | 97.544419 | 0.998123561 | 2.233122485 | 52.597738 | 12.242295 | 0.583831365 |
| 76 | 0.062361676 | 97.708932 | 96.810169 | 0.997928856 | 2.347330428 | 52.527063 | 11.125284 | 0.588467510 |
| 77 | 0.051921599 | 98.183424 | 97.783396 | 0.998388900 | 2.328217737 | 52.673585 | 12.304351 | 0.588074717 |
| 78 | 0.052613744 | 98.057008 | 97.371246 | 0.998446288 | 2.492480884 | 52.465007 | 10.997725 | 0.588224718 |
| 79 | 0.049910840 | 98.256156 | 97.918471 | 0.998513902 | 2.386469117 | 52.558091 | 11.845825 | 0.586613629 |
| 80 | 0.050832281 | 98.185156 | 97.669103 | 0.998507727 | 2.442885802 | 52.461560 | 11.070123 | 0.586328085 |
| 81 | 0.186477426 | 92.434108 | 85.727150 | 0.992158558 | 2.567711404 | 51.728953 | 7.039923 | 0.592582816 |
| 82 | 0.121369924 | 94.979739 | 91.022755 | 0.995232605 | 2.328693200 | 52.132317 | 9.070537 | 0.588543065 |
| 83 | 0.097635613 | 96.226578 | 95.310498 | 0.994114662 | 2.118934739 | 53.182100 | 15.879473 | 0.593278705 |
| 84 | 0.117596960 | 95.216985 | 91.209781 | 0.996371472 | 2.517094511 | 51.889264 | 7.650141 | 0.589433278 |
| 85 | 0.093960962 | 96.295847 | 93.706923 | 0.996718420 | 2.367898383 | 52.115080 | 8.877474 | 0.583598017 |
| 86 | 0.077355474 | 97.142659 | 95.885429 | 0.996768470 | 2.242477336 | 52.675309 | 11.869958 | 0.581982683 |
| 87 | 0.066098235 | 97.580785 | 97.135732 | 0.997312753 | 2.239718798 | 53.089016 | 14.510791 | 0.587151377 |
| 88 | 0.089863419 | 96.430922 | 93.557995 | 0.997895493 | 2.918191301 | 51.709991 | 7.050265 | 0.585414864 |
| 89 | 0.063974669 | 97.757420 | 97.069927 | 0.997680189 | 2.232744074 | 52.337447 | 11.769979 | 0.576899791 |
| 90 | 0.061344274 | 97.771274 | 97.159976 | 0.997694512 | 2.249782934 | 52.639109 | 13.266221 | 0.584372575 |
| 91 | 0.060812570 | 97.942715 | 98.638867 | 0.997959094 | 2.028339362 | 53.373440 | 17.765290 | 0.591568036 |
| 92 | 0.064387275 | 97.695078 | 96.834413 | 0.997825652 | 2.132489276 | 52.335724 | 11.728608 | 0.578196020 |
| 93 | 0.050606042 | 98.133204 | 97.457833 | 0.998581938 | 2.575931093 | 52.370199 | 10.621940 | 0.586115075 |
| 94 | 0.051638966 | 98.096838 | 97.256953 | 0.998582444 | 2.689714701 | 52.382266 | 10.301317 | 0.591557336 |
| 95 | 0.043434498 | 98.451841 | 98.022374 | 0.998896252 | 2.513873759 | 52.427084 | 11.214921 | 0.583561829 |
| 96 | 0.043534695 | 98.479548 | 98.153985 | 0.998853415 | 2.569301870 | 52.478797 | 11.449355 | 0.584768642 |
| 97 | 0.049285368 | 98.173034 | 97.194611 | 0.998919892 | 2.796055333 | 52.123699 | 8.832655 | 0.588156121 |
| 98 | 0.044009252 | 98.387767 | 97.679493 | 0.999017121 | 2.784714106 | 52.090947 | 9.032614 | 0.582642845 |
| 99 | 0.038984515 | 98.676965 | 98.437987 | 0.999074989 | 2.663376354 | 52.409846 | 10.828794 | 0.585021048 |
| 100 | 0.038097077 | 98.715063 | 98.604232 | 0.999086448 | 2.621692819 | 52.520168 | 11.470041 | 0.585284694 |

### chunks_200: status, best epoch-end record and last epoch-end record

- Completed epochs: **29**. Per-chunk monitor records: 5,893.
- Best epoch-end record by TEST STAGE loss: epoch **20**, loss **0.147276608**.
- Last epoch-end record: epoch 29. Last monitor: epoch 30, chunk 93.
- `completed_100_epochs.ok` marker: absent.

Epoch 30 remained incomplete: its monitor is not an epoch-end record and does not guarantee weights were saved at that point. No cause is attributed to the stop without evidence.

| Epoch-end record | Population | N | Loss | Accuracy % | Precision % | Recall % | Specificity % | F1 | F2 | MCC | ROC-AUC | TP | TN | FP | FN |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Best, epoch 20 | train_eval_stage | 58012 | 0.142628564 | 94.785562 | 96.730098 | 92.704958 | 96.866166 | 0.946747645 | 0.934829617 | 0.896487732 | 0.988264313 | 26890 | 28097 | 909 | 2116 |
| Best, epoch 20 | test_eval_stage | 58012 | 0.147276608 | 94.463215 | 96.509196 | 92.263670 | 96.662759 | 0.943386915 | 0.930826273 | 0.890125993 | 0.987537667 | 26762 | 28038 | 968 | 2244 |
| Best, epoch 20 | train_eval_all | 58012 | 1.455925936 | 53.813004 | 64.529690 | 16.934427 | 90.691581 | 0.268283358 | 0.198647643 | 0.112932896 | 0.598550975 | 4912 | 26306 | 2700 | 24094 |
| Best, epoch 20 | test_eval_all | 58012 | 1.455702449 | 53.906088 | 64.990738 | 16.934427 | 90.877749 | 0.268679576 | 0.198734444 | 0.116040251 | 0.599102408 | 4912 | 26360 | 2646 | 24094 |
| Last, epoch 29 | train_eval_stage | 58012 | 0.164566585 | 93.444460 | 97.554625 | 89.122940 | 97.765979 | 0.931483650 | 0.906906254 | 0.872152886 | 0.986987648 | 25851 | 28358 | 648 | 3155 |
| Last, epoch 29 | test_eval_stage | 58012 | 0.170793106 | 93.099704 | 97.456630 | 88.509274 | 97.690133 | 0.927677103 | 0.901648556 | 0.865649993 | 0.986152320 | 25673 | 28336 | 670 | 3333 |
| Last, epoch 29 | train_eval_all | 58012 | 1.675140158 | 53.228642 | 66.022241 | 13.304144 | 93.153141 | 0.221457060 | 0.158325743 | 0.107262419 | 0.595169523 | 3859 | 27020 | 1986 | 25147 |
| Last, epoch 29 | test_eval_all | 58012 | 1.674999638 | 52.983865 | 65.007803 | 12.924912 | 93.042819 | 0.215627067 | 0.153911209 | 0.099724008 | 0.596146259 | 3749 | 26988 | 2018 | 25257 |

TEST results for every epoch-end record (STAGE and ALL, using the same weights within each row):

| Epoch | STAGE loss | STAGE acc % | STAGE recall % | STAGE ROC-AUC | ALL loss | ALL acc % | ALL recall % | ALL ROC-AUC |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0.525415954 | 72.979728 | 63.862649 | 0.814822507 | 0.733674313 | 54.414604 | 31.427980 | 0.596638377 |
| 2 | 0.505695203 | 75.653313 | 67.379163 | 0.839271945 | 0.722445770 | 55.733297 | 31.772737 | 0.620998063 |
| 3 | 0.399144543 | 81.746880 | 69.830380 | 0.913460609 | 1.106050471 | 53.216576 | 16.813763 | 0.594759584 |
| 4 | 0.358148642 | 83.705095 | 72.802179 | 0.930906766 | 0.986710250 | 53.588913 | 17.020616 | 0.613533259 |
| 5 | 0.340934361 | 85.172033 | 81.607254 | 0.930538598 | 0.880825191 | 55.669517 | 28.245880 | 0.608529575 |
| 6 | 0.351012887 | 83.917121 | 75.387851 | 0.930283990 | 1.129231471 | 53.756119 | 19.647659 | 0.596185587 |
| 7 | 0.308175934 | 86.587258 | 82.582914 | 0.943334432 | 0.978191078 | 54.547335 | 24.250155 | 0.599796839 |
| 8 | 0.278077408 | 88.617872 | 84.765221 | 0.957724531 | 0.954806708 | 53.856099 | 21.171482 | 0.594633643 |
| 9 | 0.270254719 | 88.397228 | 82.076122 | 0.959887554 | 1.274582884 | 53.656140 | 17.551541 | 0.599998442 |
| 10 | 0.245277733 | 89.707302 | 82.755292 | 0.970725910 | 1.447474343 | 53.423430 | 14.131559 | 0.602409477 |
| 11 | 0.226747611 | 90.634696 | 88.864373 | 0.969598623 | 1.186459528 | 54.707647 | 23.122802 | 0.604878536 |
| 12 | 0.207533135 | 91.836172 | 88.457561 | 0.975925455 | 1.274165522 | 53.704406 | 17.617045 | 0.597267999 |
| 13 | 0.205092460 | 91.648280 | 86.113218 | 0.979466805 | 1.406381005 | 53.313108 | 13.724747 | 0.600931957 |
| 14 | 0.198196473 | 91.994760 | 86.950976 | 0.980716844 | 1.314161250 | 53.438944 | 14.590085 | 0.599769529 |
| 15 | 0.182457602 | 92.941116 | 88.854030 | 0.983114181 | 1.411268402 | 53.361374 | 14.355651 | 0.600468727 |
| 16 | 0.163014782 | 93.809901 | 91.194925 | 0.985147689 | 1.362016606 | 53.964697 | 17.320554 | 0.602227661 |
| 17 | 0.156796281 | 94.032269 | 91.181135 | 0.986294477 | 1.435490423 | 53.814728 | 16.337999 | 0.600830752 |
| 18 | 0.156239475 | 93.947804 | 90.767427 | 0.986742019 | 1.536338132 | 53.599255 | 14.934841 | 0.599102877 |
| 19 | 0.149421479 | 94.342550 | 92.067159 | 0.987229173 | 1.450428149 | 53.980211 | 16.975798 | 0.601269066 |
| 20 | 0.147276608 | 94.463215 | 92.263670 | 0.987537667 | 1.455702449 | 53.906088 | 16.934427 | 0.599102408 |
| 21 | 0.264762125 | 88.607529 | 82.051989 | 0.964179121 | 1.426404854 | 53.149348 | 15.145142 | 0.586814227 |
| 22 | 0.264034870 | 88.786803 | 79.793836 | 0.974256082 | 1.687105001 | 52.818382 | 10.659863 | 0.587702136 |
| 23 | 0.242240431 | 89.938289 | 87.106116 | 0.965363695 | 1.284110404 | 54.430118 | 21.309384 | 0.599215539 |
| 24 | 0.210088420 | 91.593119 | 90.812246 | 0.973184183 | 1.289729928 | 54.776598 | 24.260498 | 0.602166031 |
| 25 | 0.228918636 | 90.898435 | 87.044060 | 0.971319304 | 1.267220994 | 53.566503 | 17.441219 | 0.595530329 |
| 26 | 0.199574921 | 92.486037 | 91.425912 | 0.978283088 | 1.191005441 | 53.773357 | 20.581949 | 0.588064184 |
| 27 | 0.183888253 | 93.215197 | 91.677584 | 0.982675793 | 1.169227049 | 54.068124 | 20.102737 | 0.599944164 |
| 28 | 0.223850232 | 90.548507 | 83.351720 | 0.980573324 | 1.759556549 | 52.818382 | 11.394194 | 0.589927254 |
| 29 | 0.170793106 | 93.099704 | 88.509274 | 0.986152320 | 1.674999638 | 52.983865 | 12.924912 | 0.596146259 |

Last partial monitor (epoch 30, chunk 93), distinct from the best and last epoch-end records:

| Population | Loss | Accuracy % | Recall % | Specificity % | ROC-AUC |
|---|---:|---:|---:|---:|---:|
| train_eval_stage | 0.163170344 | 93.835758 | 91.401779 | 96.269737 | 0.985309162 |
| test_eval_stage | 0.168706988 | 93.491002 | 90.888092 | 96.093912 | 0.984156097 |
| train_eval_all | 1.445316440 | 53.130387 | 15.996690 | 90.264083 | 0.580772261 |
| test_eval_all | 1.441979811 | 53.190719 | 16.227677 | 90.153761 | 0.583646478 |

### Final interpretation and traceability

The 100-chunk stage completed its target and reached TEST STAGE accuracy 98.7151% and AUC 0.999086 at its best epoch-end record (epoch 100). At the same time, TEST ALL accuracy was 52.5202%, recall 11.4700% and AUC 0.585285. The partial 200-chunk stage also retained a substantial gap between local learning and global performance. This supports investigating chunk heterogeneity but does not independently establish a cause or demonstrate improvement from future global shuffling.

Values were extracted directly from the JSONL files before deletion. Metrics for all 129 epoch-end records and the best/last states are preserved. The 15,893 individual per-chunk entries, their logits and the checkpoints are not retained. SHA-256 values of the removed sources (traceability, not backups):

- `chunks_100/history_mlp_primary_secondary.jsonl`: `7399904b0b00b49f3b99a66e0175ef23b6dc5760deeffd91f5540845045b38a5`.
- `chunks_100/monitor_history.jsonl`: `52a78cb34530049ab8dd3ac57e12de37d2734231d6792919117a91049db88dfb`.
- `chunks_200/history_mlp_primary_secondary.jsonl`: `d2475ee1dc65813e506983942df3e9dcab3c97e45bafc097a8824d26dbd140ca`.
- `chunks_200/monitor_history.jsonl`: `74e64d87768ef6b0f41b62fdf8c1954d143000fbd610d9dcfad16423d9168d9d`.
