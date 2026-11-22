#!/usr/bin/env bash
set -euo pipefail
PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RESULTS="${RESULTS:-$PROJECT/results/logistic_regression_balanced}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-2}" MKL_NUM_THREADS="${MKL_NUM_THREADS:-2}" OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-2}"
mkdir -p "$RESULTS"
"${PYTHON:-python}" -u "$PROJECT/neural_network/logistic_regression/train.py" \
  --root "${DATA_ROOT:-$PROJECT/data/data_input_nn_shuffled_concatenate}" \
  --scaler "${SCALER_PATH:-$PROJECT/neural_network/MLP/standardizer_all_train_chunks.npz}" \
  --output "$RESULTS" --epochs "${EPOCHS:-10}" --batch-size "${BATCH_SIZE:-8192}" \
  --lr "${LR:-0.001}" --l2 "${L2:-0.0001}" --device "${DEVICE:-auto}" --gpus "${GPUS:-1}" \
  --log-every "${LOG_EVERY:-10}" --checkpoint-every "${CHECKPOINT_EVERY:-10}" \
  "$@" 2>&1 | tee -a "$RESULTS/run.log"
