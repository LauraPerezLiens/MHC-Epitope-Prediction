#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python}"
DATA_ROOT="${DATA_ROOT:-${BASE_DIR}/../../data/data_input_nn_shuffled_concatenate}"
RESULTS="${RESULTS:-${BASE_DIR}/../../results/mlp_shuffled_concatenated_10chunks_200epochs_20261116}"
SCALER_PATH="${SCALER_PATH:-${BASE_DIR}/standardizer_all_train_chunks.npz}"
[[ -s "$DATA_ROOT/feature_layout.json" ]] || { echo 'Completed concatenated dataset required.' >&2; exit 1; }
[[ ! -e "$DATA_ROOT/INCOMPLETE" ]] || { echo 'Dataset reordering incomplete.' >&2; exit 1; }
SCRIPT="${BASE_DIR}/mlp_layernorm_shuffled_ladder100_dualeval.py"
FEATURES=primary_secondary
EPOCHS="${EPOCHS:-200}"
STEP="${STEP:-10}"
FINAL_CHUNKS="${FINAL_CHUNKS:-10}"
EVAL_EVERY="${EVAL_EVERY:-epoch}"
"$PYTHON" -c 'import json,sys; layout=json.load(open(sys.argv[1])); assert layout.get("complete"), "Incomplete dataset"; assert 0 < int(sys.argv[2]) <= layout["chunks"], "FINAL_CHUNKS exceeds available chunks"' "$DATA_ROOT/feature_layout.json" "$FINAL_CHUNKS"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-2}"
export WORLD_SIZE=1 RANK=0 LOCAL_RANK=0
export OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MALLOC_ARENA_MAX=2

mkdir -p "$RESULTS"
# Prevent two launchers from writing to the same stage.
exec 9>"${RESULTS}/ladder.lock"
flock -n 9 || { echo 'Another LayerNorm ladder is already running.' >&2; exit 1; }

# Start the first stage with random weights. Optional later stages use this run's best.
PREVIOUS_BEST=""
[[ "$EPOCHS" =~ ^[1-9][0-9]*$ && "$STEP" =~ ^[1-9][0-9]*$ && "$FINAL_CHUNKS" =~ ^[1-9][0-9]*$ ]] && (( FINAL_CHUNKS >= STEP )) || {
    echo 'EPOCHS and STEP must be positive integers; FINAL_CHUNKS must be an integer >= STEP.' >&2; exit 1;
}

run_stage() {
    local n="$1"
    local out="${RESULTS}/chunks_${n}"
    local best="${out}/best_mlp_${FEATURES}.pt"
    local last="${out}/last_mlp_${FEATURES}.pt"
    local recovery="${out}/recovery_mlp_${FEATURES}.pt"
    local done="${out}/completed_${EPOCHS}_epochs.ok"
    mkdir -p "$out"
    if [[ -f "$done" ]]; then
        [[ -s "$best" && -s "$last" ]] || { echo "Missing checkpoints: $out" >&2; exit 1; }
        PREVIOUS_BEST="$best"
        echo "Skipping completed stage: $n chunks"
        return
    fi
    local -a cmd=("$PYTHON" -u "$SCRIPT"
        --root "$DATA_ROOT" --scaler-path "$SCALER_PATH"
        --features "$FEATURES" --epochs "$EPOCHS" --seed 42
        --eval-every "$EVAL_EVERY"
        --learning-rate 0.001 --weight-decay 0.0001
        --scheduler-t0 20 --scheduler-tmult 1 --scheduler-min-lr 0.00001
        --max-chunks "$n" --report-every-chunks 1 --secondary-cache-size 1 --eval-batch-size 1024
        --eval-target-per-class 29006 --shared-eval-dir "$RESULTS/shared_global_eval" --output-dir "$out")
    # A completed stage may have finished before its marker was written.
    local resume_path=""
    if [[ -s "$recovery" ]]; then
        resume_path="$recovery"
    elif [[ -s "$last" ]]; then
        resume_path="$last"
    fi
    if [[ -n "$resume_path" ]]; then
        local completed
        completed="$("$PYTHON" -c 'import sys,torch; print(torch.load(sys.argv[1],map_location="cpu",weights_only=False).get("completed_epochs",0))' "$resume_path")"
        if (( completed >= EPOCHS )); then
            [[ -s "$best" && -s "$last" ]] || { echo "Missing completed checkpoints: $out" >&2; exit 1; }
            touch "$done"
            PREVIOUS_BEST="$best"
            return
        fi
        cmd+=(--resume "$resume_path")
    elif [[ -n "$PREVIOUS_BEST" ]]; then
        [[ -s "$PREVIOUS_BEST" ]] || { echo "Missing previous checkpoint: $PREVIOUS_BEST" >&2; exit 1; }
        cmd+=(--init-checkpoint "$PREVIOUS_BEST")
    fi
    echo "========== LAYERNORM SHUFFLED STAGE $n chunks / $EPOCHS epochs / GPU $CUDA_VISIBLE_DEVICES =========="
    printf 'Command: '; printf '%q ' "${cmd[@]}"; printf '\n'
    "${cmd[@]}" 2>&1 | tee -a "${out}/run.log"
    [[ -s "$best" && -s "$last" ]] || { echo "Missing checkpoints: $out" >&2; exit 1; }
    touch "$done"
    PREVIOUS_BEST="$best"
}

for ((n=STEP; n<=FINAL_CHUNKS; n+=STEP)); do
    run_stage "$n"
done
if (( FINAL_CHUNKS % STEP != 0 )); then
    run_stage "$FINAL_CHUNKS"
fi
echo "LAYERNORM LADDER COMPLETE. FINAL BEST: $PREVIOUS_BEST"
