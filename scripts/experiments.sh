#!/usr/bin/env bash
# Tasks 3, 4 and 7: measurements against the system started by `make up`.
#   scripts/experiments.sh all            (or: task3 resources coldstart standard rolling recovery hpa)
# Every number in the report comes from the files this script writes under results/.
set -uo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-.venv/bin/python}
LOCUST=${LOCUST:-.venv/bin/locust}
IMAGE=${IMAGE:-ccmini/parser:1.0}
PARSE='{"text": "set an alarm for seven thirty am tomorrow"}'

log() { echo "[$(date -u +%H:%M:%S)] $*"; }
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
ready_replicas() { kubectl -n app get deploy parser -o jsonpath='{.status.readyReplicas}' 2>/dev/null; }
hpa_min() { kubectl -n app patch hpa parser --type merge -p "{\"spec\":{\"minReplicas\":$1}}" >/dev/null; }

wait_ready() {  # wait_ready N TIMEOUT : N Ready replicas and no terminating Pods
  local i
  for ((i = 0; i < $2; i++)); do
    local r; r=$(ready_replicas)
    local term; term=$(kubectl -n app get pods -l app=parser -o jsonpath='{range .items[*]}{.metadata.deletionTimestamp}{"\n"}{end}' | grep -c . || true)
    if [[ "${r:-0}" -eq "$1" && "$term" -eq 0 ]]; then return 0; fi
    sleep 1
  done
  log "WARNING: not $1 ready replicas after $2 s"; return 1
}

watch_pods() {  # background: Pod readiness + Service endpoints every second
  while true; do
    echo "== $(date -u +%H:%M:%S)"
    kubectl -n app get pods -l app=parser --no-headers \
      -o custom-columns='POD:.metadata.name,PHASE:.status.phase,READY:.status.containerStatuses[0].ready,TERMINATING:.metadata.deletionTimestamp'
    echo "ready endpoints: [$(kubectl -n app get endpoints parser -o jsonpath='{.subsets[*].addresses[*].targetRef.name}')]" \
         "not-ready: [$(kubectl -n app get endpoints parser -o jsonpath='{.subsets[*].notReadyAddresses[*].targetRef.name}')]"
    sleep 1
  done
}

probe_ingress() {  # background: one /parse per second through the Ingress, status code only
  while true; do
    echo "$(date -u +%H:%M:%S) $(curl -s -o /dev/null -w '%{http_code}' --max-time 10 -X POST http://localhost:8080/parse \
      -H 'Content-Type: application/json' -d "$PARSE")"
    sleep 1
  done
}

locust_run() {  # locust_run RUNTIME PREFIX  (same settings as the standard command)
  LOADTEST_HEADERS_OUT="$2_headers.json" "$LOCUST" -f tools/locustfile.py --headless --users 4 --spawn-rate 4 \
    --run-time "$1" --host http://localhost:8080 --csv "$2" > "$2_stdout.txt" 2>&1
  $PY scripts/summarize.py locust "$2" > "$2_summary.json"
}

versions_seen() {  # 10 requests, print the X-Model-Version / X-Served-By of each
  for _ in $(seq 1 10); do
    curl -s -D - -o /dev/null -X POST http://localhost:8080/parse -H 'Content-Type: application/json' -d "$PARSE" \
      | tr -d '\r' | grep -iE '^(HTTP|x-model-version|x-served-by)' | tr '\n' ' '; echo
  done
}

# ------------------------------------------------------------------ Task 3: container under limits
task3() {
  local out=results/task3; mkdir -p "$out"
  log "Task 3: image size, no weights, pinned versions"
  { docker image ls "$IMAGE"; echo; echo "size_bytes=$(docker image inspect "$IMAGE" --format '{{.Size}}')"
    echo; docker history "$IMAGE" --format '{{.Size}}\t{{.CreatedBy}}' | cut -c1-160; } > "$out/image.txt"
  docker run --rm --entrypoint sh "$IMAGE" -c 'echo "weight files (*.safetensors, pytorch_model*.bin, *.gguf, *.pt) in the image:"; \
    find / -xdev \( -name "*.safetensors" -o -name "pytorch_model*.bin" -o -name "*.gguf" -o -name "*.pt" \) 2>/dev/null | wc -l; \
    echo "contents of /models:"; ls -la /models' > "$out/no_weights_in_image.txt"
  docker run --rm --entrypoint pip "$IMAGE" freeze > "$out/pip_freeze_in_image.txt"

  set -a; source .secrets/s3.env; set +a          # keys passed by name only (-e VAR), never printed
  local common=(--add-host=host.docker.internal:host-gateway -e MODEL_URI=s3://models/v1/ -e MODEL_VERSION=v1
                -e S3_ENDPOINT=http://host.docker.internal:8333 -e MAX_NEW_TOKENS=48
                -e AWS_ACCESS_KEY_ID -e AWS_SECRET_ACCESS_KEY)
  docker rm -f parser-limits parser-fault >/dev/null 2>&1
  log "Task 3: run with --cpus=1 --memory=1g"
  docker run -d --name parser-limits --cpus=1 --memory=1g --memory-swap=1g -p 8001:8000 -e POD_NAME=parser-limits \
    "${common[@]}" "$IMAGE" > /dev/null
  { echo "\$ docker run -d --name parser-limits --cpus=1 --memory=1g --memory-swap=1g -p 8001:8000 ... $IMAGE"
    docker inspect parser-limits --format 'NanoCpus={{.HostConfig.NanoCpus}} Memory={{.HostConfig.Memory}} MemorySwap={{.HostConfig.MemorySwap}}'
  } > "$out/limits.txt"
  ( while [[ "$(docker inspect -f '{{.State.Running}}' parser-limits 2>/dev/null)" == true ]]; do
      echo "$(date -u +%H:%M:%S),$(docker stats --no-stream --format '{{.CPUPerc}},{{.MemUsage}},{{.MemPerc}}' parser-limits)"
    done ) > "$out/docker_stats.csv" 2>/dev/null &
  local sampler=$!
  for _ in $(seq 1 300); do
    local c; c=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8001/readyz)
    echo "$(date -u +%H:%M:%S) GET /readyz -> $c"; [[ "$c" == 200 ]] && break; sleep 0.5
  done > "$out/readyz_until_ready.txt"
  curl -s -i http://localhost:8001/healthz > "$out/healthz.txt"
  curl -s -i http://localhost:8001/readyz > "$out/readyz.txt"
  curl -s -i -X POST http://localhost:8001/parse -H 'Content-Type: application/json' -d "$PARSE" > "$out/parse_example.txt"
  log "Task 3: 50 sequential requests"
  $PY scripts/sequential_requests.py --url http://localhost:8001/parse --n 50 --out "$out/sequential_50.csv" \
    > "$out/sequential_50_stdout.txt"
  docker exec parser-limits cat /sys/fs/cgroup/memory.peak > "$out/memory_peak_bytes.txt" 2>&1
  docker exec parser-limits sh -c 'echo "memory.max=$(cat /sys/fs/cgroup/memory.max) cpu.max=$(cat /sys/fs/cgroup/cpu.max)"; grep -E "^(oom|oom_kill) " /sys/fs/cgroup/memory.events' \
    > "$out/cgroup_limits_and_oom_events.txt" 2>&1
  kill "$sampler" 2>/dev/null
  docker inspect parser-limits --format 'OOMKilled={{.State.OOMKilled}} Running={{.State.Running}} RestartCount={{.RestartCount}}' \
    > "$out/oom_check.txt"
  docker logs parser-limits > "$out/container_limits.log" 2>&1
  docker rm -f parser-limits > /dev/null

  log "Task 3: FAULT_INJECT=1"
  docker run -d --name parser-fault -p 8002:8000 -e FAULT_INJECT=1 -e POD_NAME=parser-fault "${common[@]}" "$IMAGE" > /dev/null
  for _ in $(seq 1 300); do [[ "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8002/readyz)" == 200 ]] && break; sleep 0.5; done
  { echo "\$ curl -i -X POST localhost:8002/parse -d '$PARSE'   # container started with FAULT_INJECT=1"
    curl -s -i -X POST http://localhost:8002/parse -H 'Content-Type: application/json' -d "$PARSE"; echo; } > "$out/fault_inject.txt"
  docker logs parser-fault > "$out/container_fault.log" 2>&1
  docker rm -f parser-fault > /dev/null
  $PY scripts/summarize.py task3 "$out" > "$out/summary.json"
  cat "$out/summary.json"
}

# ------------------------------------------------------------------ Task 4
resources() {
  local out=results/task4; mkdir -p "$out"
  log "Task 4: deployed resources"
  kubectl get ns > "$out/namespaces.txt"
  kubectl -n app get deploy,rs,pods,svc,endpoints,ingress,hpa -o wide > "$out/resources.txt"
  kubectl -n app describe deploy parser > "$out/describe_deployment.txt"
  kubectl -n app describe ingress parser > "$out/describe_ingress.txt"
  kubectl -n app get deploy parser -o jsonpath='{.spec.template.spec.containers[0].resources}' > "$out/requests_limits.json"
  { echo "\$ curl -i -X POST http://localhost:8080/parse -d '$PARSE'"
    curl -s -i -X POST http://localhost:8080/parse -H 'Content-Type: application/json' -d "$PARSE"; echo; } > "$out/parse_through_ingress.txt"
  kubectl -n app logs -l app=parser --prefix --tail=40 > "$out/initial_pod_logs.txt"
  $PY scripts/s3.py ls s3://models/ > "$out/models_bucket.txt"
  $PY scripts/s3.py ls s3://datasets/ > "$out/datasets_bucket.txt"
}

coldstart() {
  local out=results/task4/coldstart; mkdir -p "$out"
  hpa_min 2; wait_ready 2 600
  for run in 1 2 3; do
    log "Task 4: cold start run $run"
    local old; old=$(kubectl -n app get pods -l app=parser -o jsonpath='{.items[*].metadata.name}' | tr ' ' ',')
    watch_pods > "$out/run$run-watch.txt" 2>&1 & local w=$!
    probe_ingress > "$out/run$run-ingress-codes.txt" 2>&1 & local p=$!
    echo "$(now) deleting all parser Pods: $old" > "$out/run$run-timeline.txt"
    kubectl -n app delete pods -l app=parser --wait=false >> "$out/run$run-timeline.txt"
    for _ in $(seq 1 600); do
      [[ $(kubectl -n app get pods -l app=parser -o json | $PY scripts/pod_times.py --exclude "$old" | wc -l) -ge 2 ]] && break
      sleep 1
    done
    echo "$(now) two new Pods Ready" >> "$out/run$run-timeline.txt"
    sleep 2; kill "$w" "$p" 2>/dev/null
    kubectl -n app get pods -l app=parser -o json | $PY scripts/pod_times.py --exclude "$old" > "$out/run$run-times.jsonl"
    for pod in $(kubectl -n app get pods -l app=parser -o jsonpath='{.items[*].metadata.name}'); do
      kubectl -n app logs "$pod" > "$out/run$run-$pod.log" 2>&1
    done
    wait_ready 2 600
  done
  $PY scripts/summarize.py coldstart "$out" > results/task4/cold_start_summary.json
  cat results/task4/cold_start_summary.json
}

rolling() {
  local out=results/task4/rolling; mkdir -p "$out"
  hpa_min 2; wait_ready 2 600
  log "Task 4: rolling update v1 -> v2 under load, then rollback"
  watch_pods > "$out/watch.txt" 2>&1 & local w=$!
  locust_run 6m "$out/locust" & local l=$!
  sleep 40
  { echo "$(now) kubectl set env deployment/parser MODEL_VERSION=v2 MODEL_URI=s3://models/v2/"
    kubectl -n app set env deployment/parser MODEL_VERSION=v2 MODEL_URI=s3://models/v2/
    kubectl -n app rollout status deployment/parser --timeout=600s
    echo "$(now) rollout to v2 complete"; } >> "$out/timeline.txt" 2>&1
  sleep 40
  versions_seen > "$out/versions_after_update.txt"
  { echo "$(now) kubectl rollout undo deployment/parser"
    kubectl -n app rollout undo deployment/parser
    kubectl -n app rollout status deployment/parser --timeout=600s
    echo "$(now) rollback complete"; } >> "$out/timeline.txt" 2>&1
  sleep 20
  versions_seen > "$out/versions_after_rollback.txt"
  kubectl -n app rollout history deployment/parser > "$out/rollout_history.txt"
  wait "$l"; kill "$w" 2>/dev/null
  cat "$out/locust_summary.json"
}

recovery() {
  local out=results/task4/recovery; mkdir -p "$out"
  hpa_min 2; wait_ready 2 600
  log "Task 4: delete one Pod under load"
  watch_pods > "$out/watch.txt" 2>&1 & local w=$!
  locust_run 3m "$out/locust" & local l=$!
  sleep 40
  local victim; victim=$(kubectl -n app get pods -l app=parser -o jsonpath='{.items[0].metadata.name}')
  { echo "$(now) deleting pod $victim"; kubectl -n app delete pod "$victim" --wait=false
    kubectl -n app get deploy parser; } >> "$out/timeline.txt" 2>&1
  for _ in $(seq 1 600); do
    if [[ "$(ready_replicas)" -eq 2 ]] && ! kubectl -n app get pod "$victim" >/dev/null 2>&1; then break; fi
    sleep 1
  done
  { echo "$(now) replica count restored"; kubectl -n app get deploy parser; kubectl -n app get pods -l app=parser -o wide; } \
    >> "$out/timeline.txt" 2>&1
  wait "$l"; kill "$w" 2>/dev/null
  cat "$out/locust_summary.json"
}

hpa() {
  local out=results/task4/hpa; mkdir -p "$out"
  log "Task 4: HPA (min 1, max 2, 70 % CPU) - idle -> 1, load -> 2, idle -> 1"
  hpa_min 1
  ( while true; do
      echo "$(date -u +%H:%M:%S) hpa: $(kubectl -n app get hpa parser --no-headers 2>/dev/null | awk '{print "targets="$3,"min="$4,"max="$5,"replicas="$6}') ready=$(ready_replicas)"
      sleep 5
    done ) > "$out/hpa_watch.txt" 2>&1 & local w=$!
  local t0; t0=$(date +%s)
  until [[ "$(kubectl -n app get deploy parser -o jsonpath='{.spec.replicas}')" -eq 1 ]] || (( $(date +%s) - t0 > 600 )); do sleep 5; done
  echo "$(now) scaled down to 1 replica while idle" >> "$out/timeline.txt"
  wait_ready 1 300
  locust_run 5m "$out/locust" & local l=$!
  echo "$(now) load started (4 users)" >> "$out/timeline.txt"
  t0=$(date +%s)
  until [[ "$(kubectl -n app get deploy parser -o jsonpath='{.spec.replicas}')" -eq 2 ]] || (( $(date +%s) - t0 > 290 )); do sleep 5; done
  echo "$(now) HPA set replicas=$(kubectl -n app get deploy parser -o jsonpath='{.spec.replicas}') under load" >> "$out/timeline.txt"
  wait "$l"
  echo "$(now) load finished" >> "$out/timeline.txt"
  t0=$(date +%s)
  until [[ "$(kubectl -n app get deploy parser -o jsonpath='{.spec.replicas}')" -eq 1 ]] || (( $(date +%s) - t0 > 600 )); do sleep 5; done
  echo "$(now) replicas=$(kubectl -n app get deploy parser -o jsonpath='{.spec.replicas}') after load" >> "$out/timeline.txt"
  sleep 10; kill "$w" 2>/dev/null
  kubectl -n app describe hpa parser > "$out/describe_hpa.txt"
  kubectl -n app get hpa parser -o yaml > "$out/hpa.yaml"
  kubectl get events -n app --sort-by=.lastTimestamp > "$out/events.txt"
  cat "$out/timeline.txt"
}

# ------------------------------------------------------------------ Task 7 (+ Task 4 load balancing)
standard() {
  local out=results/task7; mkdir -p "$out" results/task4
  hpa_min 2; wait_ready 2 600; sleep 5
  log "Task 7: standard load test with exactly two Ready replicas"
  kubectl -n app get pods -l app=parser -o wide > "$out/pods_before.txt"
  ( for _ in $(seq 1 14); do echo "== $(date -u +%H:%M:%S)"; kubectl top pods -n app --no-headers; sleep 10; done ) \
    > "$out/top_pods.txt" 2>&1 & local t=$!
  { echo "\$ locust -f tools/locustfile.py --headless --users 4 --spawn-rate 4 --run-time 2m --host http://localhost:8080 --csv results/loadtest"
    "$LOCUST" -f tools/locustfile.py --headless --users 4 --spawn-rate 4 --run-time 2m --host http://localhost:8080 --csv results/loadtest
  } > "$out/locust_stdout.txt" 2>&1
  wait "$t"
  kubectl top pods -n app > "$out/top_pods_after.txt" 2>&1
  kubectl top nodes > "$out/top_nodes.txt" 2>&1
  $PY scripts/summarize.py locust results/loadtest > "$out/loadtest_summary.json"
  cp results/loadtest_headers.json results/task4/loadbalance_headers.json
  python3 scripts/cost.py --out "$out/cost.json" > "$out/cost.txt"
  cat "$out/loadtest_summary.json" "$out/cost.txt"
}

all() { task3; resources; coldstart; standard; rolling; recovery; hpa; }

for step in "${@:-all}"; do "$step"; done
