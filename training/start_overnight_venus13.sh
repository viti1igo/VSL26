#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
mkdir -p logs models

if command -v qsub >/dev/null 2>&1; then
  JOB_ID="$(qsub training/run_venus13_layoutlmv3.pbs)"
  echo "Submitted PBS job: $JOB_ID"
  echo "Monitor with:"
  echo "  qstat -u \"\$USER\""
  echo "  tail -f logs/vsl26_layoutlmv3.*.log logs/overnight_layoutlmv3_*.log"
else
  RUN_STAMP="$(date +%Y%m%d_%H%M%S)"
  LOG_FILE="logs/nohup_overnight_layoutlmv3_${RUN_STAMP}.log"
  nohup bash training/run_overnight_venus13.sh > "$LOG_FILE" 2>&1 &
  PID="$!"
  echo "qsub not found; started nohup process: $PID"
  echo "Monitor with:"
  echo "  tail -f $LOG_FILE"
fi
