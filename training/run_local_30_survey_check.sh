#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VENV="${VENV:-.venv-local-eval}"
CHECKPOINT="${1:-}"
PYTHON_BIN="${PYTHON_BIN:-}"

if [[ -z "$PYTHON_BIN" ]]; then
  for candidate in python3.11 python3.12 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PYTHON_BIN="$(command -v "$candidate")"
      break
    fi
  done
fi

if [[ -z "$PYTHON_BIN" ]]; then
  echo "Could not find a local Python interpreter."
  exit 1
fi

if [[ -z "$CHECKPOINT" ]]; then
  if [[ -f models/latest_layoutlmv3_vaipe_retrain.txt ]]; then
    CHECKPOINT="$(cat models/latest_layoutlmv3_vaipe_retrain.txt)"
  else
    CHECKPOINT="$(find models -path '*/layoutlmv3_vaipe_retrain_*/final' -type d | sort | tail -1)"
  fi
fi

if [[ -z "$CHECKPOINT" || ! -d "$CHECKPOINT" ]]; then
  echo "Could not find retrained checkpoint under models/."
  echo "Expected something like: models/layoutlmv3_vaipe_retrain_20260611_085133/final"
  exit 1
fi

if [[ -x "$VENV/bin/python" ]]; then
  VENV_VERSION="$("$VENV/bin/python" - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)"
else
  VENV_VERSION=""
fi

PYTHON_VERSION="$("$PYTHON_BIN" - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)"

if [[ "$VENV_VERSION" != "$PYTHON_VERSION" ]]; then
  rm -rf "$VENV"
fi

if [[ ! -d "$VENV" ]]; then
  "$PYTHON_BIN" -m venv "$VENV"
fi

echo "Using Python: $("$VENV/bin/python" --version)"

"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install \
  "setuptools==70.3.0" \
  "numpy>=1.24,<2.0" \
  "torch>=2.3,<2.8" \
  "torchvision>=0.18,<0.23" \
  "transformers>=4.41,<4.58" \
  "pillow>=10.0" \
  "safetensors>=0.4" \
  "easyocr==1.7.2" \
  "vietocr==0.3.13" \
  "opencv-python-headless<4.10" \
  "rapidfuzz>=3.0"

mkdir -p results logs

"$VENV/bin/python" training/functional_extraction_check.py \
  --checkpoint "$CHECKPOINT" \
  --image-path expert_survey/images \
  --output-json results/retrained_layoutlmv3_30_survey_check_local.json \
  --output-csv results/retrained_layoutlmv3_30_survey_check_local.csv \
  | tee "logs/retrained_layoutlmv3_30_survey_check_local_$(date +%Y%m%d_%H%M%S).log"
