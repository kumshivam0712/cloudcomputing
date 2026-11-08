# Knowledge distillation + deployment of a command parser on a local k3d cloud.
# Prerequisites on the host: docker, k3d (v5), kubectl, python3 (with venv), curl, make.
#   make up      build and deploy the whole system (cluster, SeaweedFS, models, service)
#   make down    delete the cluster
# Run `make help` for every target.

SHELL := /bin/bash
.SHELLFLAGS := -o pipefail -c
.DEFAULT_GOAL := help

CLUSTER       ?= ccmini
GITHUB_REPO   ?= kumshivam0712/cloudcomputing
PYTHON        ?= python3
VENV          ?= .venv
PY            := $(VENV)/bin/python
TRAIN_VENV    ?= .venv-train
TPY           := $(TRAIN_VENV)/bin/python
SHARD_COUNT   ?= 4
LIMIT         ?= 0
LABEL_TIMEOUT ?= 18000
CONFIG        ?= training/config.yaml
SUBSET        ?= 0
IMAGE         ?= ccmini/parser:1.0
WORKER_IMAGE  ?= ccmini/worker:1.0
MODEL_TAGS    ?= v1 v2
export S3_ENDPOINT ?= http://localhost:8333
export GITHUB_REPO

render = sed -e 's/__SHARD_COUNT__/$(SHARD_COUNT)/g' -e 's/__LIMIT__/$(LIMIT)/g'

.PHONY: help up down tools train-env cluster storage seed-data seed-models teacher-up teacher-eval \
        worker-image label clean-data verify-data train evaluate image deploy smoke loadtest \
        test lint nacl subnets cost status

help:
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-14s %s\n", $$1, $$2}'

# ---------------------------------------------------------------- whole system (Task 6)
up: tools cluster storage seed-data seed-models image deploy smoke ## Build + deploy everything from a fresh clone
	@echo "System is up: curl -s -X POST localhost:8080/parse -H 'Content-Type: application/json' -d '{\"text\":\"set an alarm for six am\"}'"

down: ## Delete the k3d cluster (and everything in it)
	k3d cluster delete --config cluster/k3d.yaml

# ---------------------------------------------------------------- python environments
tools: $(VENV)/.stamp ## Host tools venv (boto3, locust, pytest, ruff)
$(VENV)/.stamp: requirements-tools.txt
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install -q -r requirements-tools.txt
	touch $@

train-env: $(TRAIN_VENV)/.stamp ## Training venv (CPU PyTorch + Transformers)
$(TRAIN_VENV)/.stamp: training/requirements.txt
	$(PYTHON) -m venv $(TRAIN_VENV)
	if [ "$$(uname -s)" = Linux ]; then \
	  $(TRAIN_VENV)/bin/pip install -q --index-url https://download.pytorch.org/whl/cpu torch==2.5.1+cpu; fi
	$(TRAIN_VENV)/bin/pip install -q -r training/requirements.txt
	touch $@

# ---------------------------------------------------------------- Task 1: cluster, storage, teacher
cluster: ## Create the k3d cluster from cluster/k3d.yaml
	k3d cluster list $(CLUSTER) >/dev/null 2>&1 || k3d cluster create --config cluster/k3d.yaml
	kubectl config use-context k3d-$(CLUSTER)
	kubectl wait --for=condition=Ready nodes --all --timeout=180s

storage: tools cluster ## SeaweedFS in namespace data, buckets datasets+models, upload commands_pool.jsonl
	scripts/secrets.sh
	kubectl apply -f k8s/data/seaweedfs.yaml
	kubectl -n data rollout status deploy/seaweedfs --timeout=300s
	$(PY) scripts/s3.py wait
	$(PY) scripts/s3.py mb datasets models
	$(PY) scripts/s3.py put data/commands_pool.jsonl s3://datasets/commands_pool.jsonl

seed-data: storage ## Upload the committed teacher shards and train set to the datasets bucket
	if ls datasets/teacher/shard-*.jsonl >/dev/null 2>&1; then $(PY) scripts/s3.py put-dir datasets/teacher s3://datasets/teacher/; fi
	if [ -f datasets/v1/train.jsonl ]; then $(PY) scripts/s3.py put-dir datasets/v1 s3://datasets/v1/; fi

seed-models: storage ## Download models v1/v2 from the GitHub Release, verify sha256, upload to s3://models/<v>/
	scripts/fetch_models.sh $(MODEL_TAGS)

teacher-up: storage ## Run Ollama (phi3.5) in namespace pipeline
	$(render) k8s/pipeline/ollama.yaml | kubectl apply -f -
	kubectl -n pipeline rollout status deploy/ollama --timeout=900s
	kubectl -n pipeline exec deploy/ollama -- ollama pull phi3.5
	kubectl -n pipeline exec deploy/ollama -- ollama list

teacher-eval: tools ## Teacher on validation.jsonl -> results/teacher_validation.json
	scripts/teacher_eval.sh

worker-image: cluster ## Build the worker image and import it into k3d
	docker build -q -f worker/Dockerfile -t $(WORKER_IMAGE) .
	k3d image import $(WORKER_IMAGE) -c $(CLUSTER)

label: worker-image ## Parallel labelling: SHARD_COUNT worker Pods (Indexed Job) in namespace pipeline
	kubectl -n pipeline delete job teacher-labeler --ignore-not-found
	$(render) k8s/pipeline/worker-job.yaml | kubectl apply -f -
	scripts/wait_job.sh pipeline teacher-labeler $(LABEL_TIMEOUT) 300

clean-data: tools worker-image ## Run worker/clean.py in the cluster; download shards + train set to datasets/
	kubectl -n pipeline delete job clean-dataset --ignore-not-found
	$(render) k8s/pipeline/clean-job.yaml | kubectl apply -f -
	scripts/wait_job.sh pipeline clean-dataset 600 5
	kubectl -n pipeline logs job/clean-dataset
	$(PY) scripts/s3.py get-dir s3://datasets/teacher/ datasets/teacher
	$(PY) scripts/s3.py get-dir s3://datasets/v1/ datasets/v1

verify-data: ## Re-run clean.py locally on the shard files and compare with datasets/v1/train.sha256
	mkdir -p build
	$(PYTHON) worker/clean.py --shards datasets/teacher --out build/clean-check --schema data/schema.json \
	  --pool data/commands_pool.jsonl --pool-limit $(LIMIT) > build/clean-check.log
	diff <(cut -d' ' -f1 datasets/v1/train.sha256) <(cut -d' ' -f1 build/clean-check/train.sha256)
	@echo "OK: clean.py reproduces $$(cut -d' ' -f1 datasets/v1/train.sha256)"

# ---------------------------------------------------------------- Task 2: training
train: train-env ## Fine-tune Pythia-70M (CONFIG=training/config.yaml, SUBSET=50 for a quick check)
	$(TPY) training/train.py --config $(CONFIG) --subset $(SUBSET)

evaluate: train-env ## Score a trained model on validation.jsonl (MODEL_DIR=build/models/v1 NAME=student_v1)
	$(TPY) training/predict.py --model $(MODEL_DIR) --gold data/validation.jsonl --out results/$(NAME)_predictions.jsonl
	$(PYTHON) tools/score.py results/$(NAME)_predictions.jsonl data/validation.jsonl --out results/$(NAME)_validation.json

# ---------------------------------------------------------------- Tasks 3/4: service
image: cluster ## Build the inference image (no weights) and import it into k3d
	docker build -f service/Dockerfile -t $(IMAGE) .
	k3d image import $(IMAGE) -c $(CLUSTER)

deploy: ## Deployment, Service, Ingress, HPA in namespace app
	kubectl apply -f k8s/app/
	kubectl -n app rollout status deploy/parser --timeout=900s

smoke: ## One request through the Ingress
	for i in $$(seq 1 30); do \
	  curl -sf -i -X POST http://localhost:8080/parse -H 'Content-Type: application/json' \
	    -d '{"text": "set an alarm for seven thirty am tomorrow"}' && exit 0; sleep 3; done; exit 1

loadtest: tools ## Standard Locust run (4 users, 2 min) through the Ingress
	$(VENV)/bin/locust -f tools/locustfile.py --headless --users 4 --spawn-rate 4 --run-time 2m \
	  --host http://localhost:8080 --csv results/loadtest

status: ## Show what is running
	kubectl get nodes -o wide
	kubectl get all,ingress,hpa,pvc -n data -n app 2>/dev/null || true
	kubectl get all,ingress,hpa -A | grep -E 'NAMESPACE|data|pipeline|app' || true

# ---------------------------------------------------------------- Tasks 5/6/7
test: tools ## Unit tests
	$(PY) -m pytest -q tests

lint: tools ## Lint
	$(VENV)/bin/ruff check .

nacl: ## Check network/nacl.json with the kit simulator
	$(PYTHON) tools/nacl_sim.py network/nacl.json network/packets_sample.jsonl --check

subnets: ## Recompute the subnet table
	$(PYTHON) scripts/subnets.py

cost: ## Cost per 1,000 requests from results/loadtest_stats.csv and data/rate_card.json
	$(PYTHON) scripts/cost.py
