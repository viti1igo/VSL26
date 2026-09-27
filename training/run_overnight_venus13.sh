#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

mkdir -p logs models results
export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"

if [[ -z "${CUDA_VISIBLE_DEVICES:-}" ]] && command -v nvidia-smi >/dev/null 2>&1; then
  BEST_GPU="$(
    nvidia-smi --query-gpu=index,memory.free --format=csv,noheader,nounits \
      | awk -F, 'BEGIN {best=-1; idx=""} {gsub(/ /, "", $1); gsub(/ /, "", $2); if ($2+0 > best) {best=$2+0; idx=$1}} END {print idx}'
  )"
  if [[ -n "$BEST_GPU" ]]; then
    export CUDA_VISIBLE_DEVICES="$BEST_GPU"
  fi
fi

RUN_STAMP="${RUN_STAMP:-$(date +%Y%m%d_%H%M%S)}"
OUTPUT_DIR="${OUTPUT_DIR:-models/layoutlmv3_vaipe_retrain_${RUN_STAMP}}"
LOG_FILE="${LOG_FILE:-logs/overnight_layoutlmv3_${RUN_STAMP}.log}"
LATEST_FILE="models/latest_layoutlmv3_vaipe_retrain.txt"

exec > >(tee -a "$LOG_FILE") 2>&1

echo "== VSL26 LayoutLMv3 overnight run =="
echo "Started: $(date)"
echo "Host: $(hostname)"
echo "Root: $ROOT_DIR"
echo "Output: $OUTPUT_DIR"
echo "Log: $LOG_FILE"
echo "CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-unset}"
nvidia-smi || true

module purge >/dev/null 2>&1 || true
module load python/3.12 >/dev/null 2>&1 || true
module load python/3.10 >/dev/null 2>&1 || true
module load cuda >/dev/null 2>&1 || true

if [[ ! -d .venv-venus13 ]]; then
  python3 -m venv .venv-venus13
fi

source .venv-venus13/bin/activate
python --version
python -m pip install --upgrade pip wheel
python -m pip install -r training/requirements-venus13.txt

python - <<'PY'
import os
import torch
print("torch", torch.__version__)
cuda_available = torch.cuda.is_available()
print("cuda_available", cuda_available)
if torch.cuda.is_available():
    print("gpu", torch.cuda.get_device_name(0))
elif os.getenv("ALLOW_CPU", "0") != "1":
    raise SystemExit("CUDA is not available. Refusing overnight CPU training. Set ALLOW_CPU=1 to override.")
PY

DATA_ARGS=()
if [[ -n "${VAIPE_DATASET_ROOT:-}" ]]; then
  DATA_ARGS+=(--dataset-root "$VAIPE_DATASET_ROOT")
else
  DATA_ARGS+=(--download-kaggle)
fi

BASE_MODEL="${BASE_MODEL:-microsoft/layoutlmv3-base}"

if [[ "${RUN_SMOKE_FIRST:-1}" == "1" && ! -f models/layoutlmv3_vaipe_smoke/final_metrics.json ]]; then
  echo "== Smoke test =="
  python training/train_layoutlmv3_vaipe.py \
    "${DATA_ARGS[@]}" \
    --base-model "$BASE_MODEL" \
    --smoke \
    --output-dir models/layoutlmv3_vaipe_smoke \
    --overwrite-output-dir
else
  echo "== Smoke test skipped =="
fi

echo "== Full training =="
python training/train_layoutlmv3_vaipe.py \
  "${DATA_ARGS[@]}" \
  --base-model "$BASE_MODEL" \
  --output-dir "$OUTPUT_DIR" \
  --max-length "${MAX_LENGTH:-512}" \
  --per-device-train-batch-size "${TRAIN_BATCH_SIZE:-1}" \
  --per-device-eval-batch-size "${EVAL_BATCH_SIZE:-1}" \
  --gradient-accumulation-steps "${GRAD_ACCUM:-8}" \
  --learning-rate "${LR:-2e-5}" \
  --max-steps "${MAX_STEPS:-1500}" \
  --eval-steps "${EVAL_STEPS:-100}" \
  --save-steps "${SAVE_STEPS:-100}" \
  --logging-steps "${LOGGING_STEPS:-25}" \
  --save-total-limit "${SAVE_TOTAL_LIMIT:-2}"

FINAL_DIR="$OUTPUT_DIR/final"
printf "%s\n" "$FINAL_DIR" > "$LATEST_FILE"

echo "== Final metrics =="
if [[ -f "$OUTPUT_DIR/final_metrics.json" ]]; then
  cat "$OUTPUT_DIR/final_metrics.json"
else
  echo "No final_metrics.json found."
fi

echo
echo "Finished: $(date)"
echo "Final checkpoint: $FINAL_DIR"
echo "Latest pointer: $LATEST_FILE"
echo "Log file: $LOG_FILE"
