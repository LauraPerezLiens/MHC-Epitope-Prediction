#!/usr/bin/env bash
set -euo pipefail
BASE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python}"
PROJECT_ROOT="$(cd -- "$BASE_DIR/../.." && pwd)"
MLP_DIR="$BASE_DIR"
SPLIT_DIR="$PROJECT_ROOT/data_pipeline/scripts/data_splitting"
export DATA_ROOT="${DATA_ROOT:-$PROJECT_ROOT/data/data_input_nn_shuffled}"
export SCALER_PATH="${SCALER_PATH:-$MLP_DIR/standardizer_all_train_chunks.npz}"
export OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
exec 8<"${BASH_SOURCE[0]}"
flock -n 8 || { echo 'Shuffled pipeline already running.' >&2; exit 1; }
trap 'echo "FAILED phase=$PHASE line=$LINENO at $(date -Is)"' ERR
PHASE=split
if [[ ! -s "$SCALER_PATH" ]]; then
    echo "START split $(date -Is)"
    "$PYTHON" -u "$SPLIT_DIR/split_data.py" --root "$DATA_ROOT" --seed 42
fi
PHASE=metadata
if [[ ! -s "$SCALER_PATH" ]]; then
    echo "START metadata $(date -Is)"
    "$PYTHON" -u "$SPLIT_DIR/prepare_chunk_metadata.py" --root "$DATA_ROOT" --force
fi
PHASE=validation
if [[ ! -s "$SCALER_PATH" ]]; then
    echo "START validation $(date -Is)"
    "$PYTHON" -u "$SPLIT_DIR/check_master_split.py" --root "$DATA_ROOT"
fi
PHASE=scaler
if [[ ! -s "$SCALER_PATH" ]]; then
    echo "START scaler $(date -Is)"
    "$PYTHON" -u "$MLP_DIR/fit_shuffled_scaler.py" --root "$DATA_ROOT" --output "$SCALER_PATH"
fi
echo "PREPARATION COMPLETE: split, metadata, validation and scaler. $(date -Is)"
