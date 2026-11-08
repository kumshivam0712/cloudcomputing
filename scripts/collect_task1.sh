#!/usr/bin/env bash
# Save Task 1 evidence (cluster, storage, workers, teacher) into results/task1/.
set -uo pipefail
cd "$(dirname "$0")/.."
out=results/task1
mkdir -p "$out"
PY=${PY:-.venv/bin/python}

{
  echo "\$ k3d cluster list"; k3d cluster list
  echo; echo "\$ kubectl get nodes -o wide"; kubectl get nodes -o wide
  echo; echo "\$ kubectl get ns"; kubectl get ns
} > "$out/cluster.txt" 2>&1

{
  echo "\$ kubectl -n data get deploy,pods,svc,pvc -o wide"; kubectl -n data get deploy,pods,svc,pvc -o wide
  echo; echo "\$ python scripts/s3.py ls"; $PY scripts/s3.py ls
  echo; echo "\$ python scripts/s3.py ls s3://datasets/"; $PY scripts/s3.py ls s3://datasets/
  echo; echo "\$ python scripts/s3.py ls s3://models/"; $PY scripts/s3.py ls s3://models/
} > "$out/storage.txt" 2>&1

{
  echo "\$ kubectl -n pipeline get jobs,pods -o wide"; kubectl -n pipeline get jobs,pods -o wide
  echo; echo "Worker pods: shard index, start and finish times (they overlap => ran at the same time)"
  kubectl -n pipeline get pods -l job-name=teacher-labeler -o custom-columns='POD:.metadata.name,SHARD_INDEX:.metadata.annotations.batch\.kubernetes\.io/job-completion-index,STARTED:.status.startTime,FINISHED:.status.containerStatuses[0].state.terminated.finishedAt,EXIT:.status.containerStatuses[0].state.terminated.exitCode'
  echo; echo "\$ kubectl -n pipeline describe job teacher-labeler"; kubectl -n pipeline describe job teacher-labeler
} > "$out/pipeline.txt" 2>&1

for p in $(kubectl -n pipeline get pods -l job-name=teacher-labeler -o name 2>/dev/null); do
  idx=$(kubectl -n pipeline get "$p" -o jsonpath="{.metadata.annotations['batch\.kubernetes\.io/job-completion-index']}")
  kubectl -n pipeline logs "$p" > "$out/worker-shard-$idx.log" 2>&1
done
kubectl -n pipeline logs job/clean-dataset > "$out/clean.log" 2>&1 || true

{
  echo "\$ ollama list"; kubectl -n pipeline exec deploy/ollama -- ollama list
  echo; echo "\$ ollama show phi3.5"; kubectl -n pipeline exec deploy/ollama -- ollama show phi3.5
  echo; echo "\$ ollama --version"; kubectl -n pipeline exec deploy/ollama -- ollama --version
  echo; echo "teacher options used by worker/teacher.py:"; grep -n "TEACHER_OPTIONS =" worker/teacher.py
  echo; echo "sha256 of prompts/teacher_prompt.txt:"; sha256sum prompts/teacher_prompt.txt
} > "$out/teacher.txt" 2>&1
kubectl -n pipeline logs deploy/ollama --tail=200 > "$out/ollama-tail.log" 2>&1 || true

for f in clean_report.json rejected.jsonl; do
  [[ -f datasets/v1/$f ]] && cp "datasets/v1/$f" "$out/$f"
done
ls -la datasets/teacher datasets/v1 > "$out/files.txt" 2>&1
echo "evidence written to $out"
