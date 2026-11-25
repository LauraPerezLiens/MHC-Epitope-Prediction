# Training on the fragment dataset (per-residue ProtT5)

Models trained on the fragments produced by the rebuilt data pipeline
(`data_pipeline/scripts/data_download/build_fragments.py`), using **per-residue**
ProtT5 embeddings — `(w, 1024)` — instead of the mean-pooled `(1024,)` vectors
the historical pipeline used.

This directory replaces nothing in `../MLP/` or `../logistic_regression/`: those
scripts read `data_input_nn_shuffled_concatenate`, which the new pipeline no
longer produces, and they carry the four protocol defects documented in §0.8 of
`CLAUDE.md` (row-level split, selection on TEST, forced 50/50 evaluation, no
average precision).

## `train_fragments.py`

One pass over the data trains **four models at once**:

| Model | Input | Shape |
|---|---|---|
| `lr_residuo` | flattened per-residue | `w × dim → 1` |
| `mlp_residuo` | flattened per-residue | `w × dim → 512 → 128 → 1` |
| `lr_pooled` | mean over positions | `dim → 1` |
| `mlp_pooled` | mean over positions | `dim → 512 → 128 → 1` |

`dim` is 1024 for `--features primary` and 1027 for `--features
primary_secondary` (three one-hot channels for the Q3 state C/H/E).

Four models in one pass is not a shortcut. **I/O dominates**: one epoch moves
~107 GB of fp16 embeddings off disk, while the MLP forward/backward is a few
seconds of GPU time. Training them together costs almost nothing extra and
guarantees all four see identical batches in identical order, which makes the
comparison tighter than four separate runs would.

### The mean-pooling control is the point

Without it, "better than the historical pipeline" cannot be claimed: the data,
the split and the representation all changed at once. The `*_pooled` models
apply the historical representation to the new data, so the gap between
`*_residuo` and `*_pooled` isolates the effect of not pooling — and nothing
else.

Two caveats, so nobody reads the control as a bit-exact reproduction:

- The mean covers the `w` residues and **excludes the `</s>` token**. The
  historical pipeline *included* it (`prott5_v2.py:121`), which is 3.8 % of a
  25-residue window's vector. The EOS vectors are stored separately
  (`chunk_*_eos.npy`) if an exact reproduction is ever needed.
- In the `primary_secondary` arm, pooling the three one-hot channels yields the
  **fraction of C/H/E in the window** — exactly the feature §0.2 measured with
  logistic regression at 0.592364 ROC-AUC. It is an anchor against a number the
  project has already recorded.

### Protocol

Fixes the four defects §0.8 found in the historical MLP:

1. **Split by protein–fragment connected component**, taken from
   `splits.parquet`, certified with zero fragment and zero protein crossing
   partitions (§0.14.4).
2. **Model selection on VALIDATION**, never on TEST.
3. **Evaluation at natural prevalence**, not a forced 50/50 sample.
4. **Average precision and lift over prevalence**, besides ROC-AUC. Metrics are
   also broken down per MHC family and per species.

`--test` is off by default. Score TEST **once**, with the configuration that won
on VALIDATION; scoring all 16 models of the matrix and keeping the best would be
selecting on TEST through the back door.

### Standardisation

Comes from `compute_scaler.py` (see
`data_pipeline/scripts/embeddings/primary_structure/`), fitted on TRAIN only.
Per channel, shared across the `w` positions; the three secondary-structure
channels are left as 0/1 because they are one-hot. The pooled arm applies the
same transform and then rescales by `std_canal / std_pool`, because averaging
`w` correlated positions shrinks the standard deviation (measured: to 0.31×,
against 0.22× if the positions were independent).

**Each contradiction arm needs its own scaler**: the arm that keeps the
contradictory rows has a different TRAIN set (2,666,904 rows against
2,494,946).

### The run matrix

Four passes, four models each, for window 21:

| Pass | `--features` | `--excluir-contradictorios` | Scaler |
|---|---|---|---|
| 1 | `primary` | yes | `scaler_sin_contradicciones.npz` |
| 2 | `primary_secondary` | yes | `scaler_sin_contradicciones.npz` |
| 3 | `primary` | no | `scaler_con_contradicciones.npz` |
| 4 | `primary_secondary` | no | `scaler_con_contradicciones.npz` |

```bash
P=/home/nap/miniconda3/envs/nap_env/bin/python
CUDA_VISIBLE_DEVICES=2 $P -u neural_network/fragments/train_fragments.py \
    --fragments data/fragments_w21_ss --embeddings data/embeddings_prott5_w21 \
    --splits data/splits_w21/splits.parquet \
    --scaler data/scalers_w21/scaler_sin_contradicciones.npz \
    --features primary --excluir-contradictorios \
    --out results/fragments_w21_primary_limpio
```

Always pin the GPU with `CUDA_VISIBLE_DEVICES`, use at most two, and leave at
least one entirely free (`CLAUDE.md` §0.0.4).

## Outputs

- `history.jsonl` — one `epoch_end` record per epoch with TRAIN loss and the
  full VALIDATION metrics for the four models.
- `best_<model>.pt` — weights of the best epoch per model, chosen by VALIDATION
  average precision.
- `resultado.json` — arguments, git commit, scaler SHA-256, row counts and
  prevalences, parameter counts, best epoch per model, and the TEST metrics if
  `--test` was passed.
