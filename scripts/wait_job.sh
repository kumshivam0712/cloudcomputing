#!/usr/bin/env bash
# wait_job.sh NAMESPACE JOB TIMEOUT_SECONDS [LOG_EVERY_SECONDS]
# Wait for a Job to complete, printing the latest progress line of each Pod periodically.
set -euo pipefail
ns=$1 job=$2 timeout=$3 every=${4:-120}
start=$(date +%s)
while true; do
  succeeded=$(kubectl -n "$ns" get job "$job" -o jsonpath='{.status.conditions[?(@.type=="Complete")].status}' 2>/dev/null || true)
  failed=$(kubectl -n "$ns" get job "$job" -o jsonpath='{.status.conditions[?(@.type=="Failed")].status}' 2>/dev/null || true)
  now=$(date +%s)
  echo "---- $(date -u +%H:%M:%S) job/$job after $((now - start))s"
  kubectl -n "$ns" get pods -l job-name="$job" -o wide --no-headers 2>/dev/null || true
  for p in $(kubectl -n "$ns" get pods -l job-name="$job" -o name 2>/dev/null); do
    echo "$p: $(kubectl -n "$ns" logs "$p" --tail=1 2>/dev/null || true)"
  done
  if [[ "$succeeded" == "True" ]]; then echo "job/$job complete"; exit 0; fi
  if [[ "$failed" == "True" ]]; then echo "job/$job FAILED"; exit 1; fi
  if (( now - start > timeout )); then echo "job/$job timed out after ${timeout}s"; exit 2; fi
  sleep "$every"
done
