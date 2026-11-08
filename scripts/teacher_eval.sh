#!/usr/bin/env bash
# Teacher (in-cluster Ollama) on validation.jsonl through a port-forward, then score it.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p results
kubectl -n pipeline port-forward svc/ollama 11434:11434 > build-port-forward.log 2>&1 &
pf=$!
trap 'kill $pf 2>/dev/null || true; rm -f build-port-forward.log' EXIT
for _ in $(seq 1 30); do curl -sf http://localhost:11434/ >/dev/null && break; sleep 1; done
python3 scripts/teacher_eval.py --url http://localhost:11434 --workers "${WORKERS:-4}"
python3 tools/score.py results/teacher_validation_predictions.jsonl data/validation.jsonl \
  --out results/teacher_validation.json
