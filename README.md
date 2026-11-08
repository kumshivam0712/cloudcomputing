# Knowledge Distillation and Deployment of a Command-Parsing Language Model on a Local Cloud

Cloud Computing (CS3081) mini project.

**GitHub repository: https://github.com/kumshivam0712/cloudcomputing**
(the assessed commit is the one tagged [`final`](https://github.com/kumshivam0712/cloudcomputing/tree/final);
models: [Releases](https://github.com/kumshivam0712/cloudcomputing/releases))

A teacher LLM (`phi3.5`, 3.8 B, served by Ollama, temperature 0, seed 42) labels 3,000 voice-assistant
commands with a four-key JSON frame (`intent`, `date`, `time`, `place`). The cleaned replies train a
70 M-parameter student (`EleutherAI/pythia-70m`) by **sequence-level knowledge distillation** on CPU.
The student is served by a FastAPI container on a local k3d (k3s) cluster, with the model stored in
SeaweedFS (S3) and pulled at start-up. The report is [`report/report.pdf`](report/report.pdf).

## Repository layout

| Path | What |
|---|---|
| `cluster/k3d.yaml` | k3d cluster (1 node, Traefik on `localhost:8080`, SeaweedFS S3 on `localhost:8333`) |
| `k8s/data/` | SeaweedFS (S3) in namespace `data` |
| `k8s/pipeline/` | Ollama teacher, Indexed Job of labelling workers, clean Job (namespace `pipeline`) |
| `k8s/app/` | Deployment, Service, Ingress, HPA, ConfigMap of the inference service (namespace `app`) |
| `prompts/teacher_prompt.txt` | the teacher prompt |
| `worker/` | `worker.py` (SHARD_INDEX / SHARD_COUNT), `clean.py`, worker Dockerfile |
| `datasets/` | teacher shard outputs (`teacher/shard-*.jsonl`) and `v1/train.jsonl` + `train.sha256` (mirror of the `datasets` bucket) |
| `training/` | `config.yaml` (v1), `config_v2.yaml`, `train.py`, `predict.py`, `loss.csv` |
| `models/v*/model.sha256` | checksums of the model files (the weights themselves are only in object storage and in GitHub Releases) |
| `service/` | FastAPI service, Dockerfile, pinned requirements |
| `network/` | `subnets.md`, `nacl.json`, `packets_sample.jsonl` |
| `tests/` | unit tests (pytest) |
| `.github/workflows/` | `ci.yml` (Task 6), `label.yml` (Task 1), `train.yml` + `evaluate.yml` (Task 2), `deploy.yml` (Tasks 3/4/6/7), `submission.yml` (final packaging), `tag-final.yml` |
| `results/` | every log, score report, Locust output and command output used in the report |
| `report/` | `report.md` (source) and `report.pdf` |
| `data/`, `tools/` | the student kit, unchanged |
| `AI_USE.md` | AI tools used and how their output was checked |

## Prerequisites

Docker, [k3d](https://k3d.io) v5, kubectl, Python 3.10+ with `venv`, `make`, `curl`.
Everything else (Python packages, images, models) is pinned and fetched by the Makefile.
No credentials are stored in Git: `make up` generates random S3 keys into `.secrets/` (git-ignored)
and stores them only as Kubernetes Secrets.

## Build and deploy (from a fresh clone, three commands)

```bash
git clone https://github.com/kumshivam0712/cloudcomputing.git
```
```bash
cd cloudcomputing
```
```bash
make up
```

`make up` creates the cluster from `cluster/k3d.yaml`, deploys SeaweedFS in `data`, creates the buckets
`datasets` and `models`, uploads `commands_pool.jsonl` (and the committed teacher shards / train set),
downloads models v1 and v2 from the GitHub Releases, verifies them against `models/v*/model.sha256`,
uploads them to `s3://models/v1/` and `s3://models/v2/`, builds the service image (no weights inside),
imports it into k3d and deploys namespace `app`. When it finishes:

```bash
curl -i -X POST http://localhost:8080/parse -H 'Content-Type: application/json' -d '{"text": "set an alarm for seven thirty am tomorrow"}'
```

## Test

```bash
make test
```
```bash
make lint
```
```bash
make loadtest
```
```bash
make nacl
```

`make loadtest` is the standard command
`locust -f tools/locustfile.py --headless --users 4 --spawn-rate 4 --run-time 2m --host http://localhost:8080 --csv results/loadtest`.
All Task 3/4/7 experiments (container at 1 CPU / 1 GiB, cold start, rolling update and rollback,
recovery, HPA, load balancing, cost) are scripted:

```bash
scripts/experiments.sh all
```

## Re-run the pipeline stages

| Stage | Command | Notes |
|---|---|---|
| Teacher labelling (Task 1) | `make storage teacher-up label clean-data` | 3,000 commands on CPU take hours; `LIMIT=80` for a smoke test, `SHARD_COUNT=4` workers |
| Teacher on validation | `make teacher-eval` | writes `results/teacher_validation.json` |
| Check the train-set checksum | `make verify-data` | re-runs `worker/clean.py` on `datasets/teacher/` |
| Train the student (Task 2) | `make train` | reads only `training/config.yaml`; `make train SUBSET=50` for a quick check |
| Train v2 | `make train CONFIG=training/config_v2.yaml` | |
| Evaluate a model | `make evaluate MODEL_DIR=build/models/v1 NAME=student_v1` | |
| Use freshly trained models | `make seed-models LOCAL_MODELS=1` | uploads `build/models/v*` instead of the Release assets |

The same stages run on GitHub Actions: `task1-teacher-labelling` → (automatically)
`task2-train-student` → (automatically) `task3-4-7-deploy-and-experiments`, plus
`task2-evaluate-models` and `ci`. Each commits its outputs to `results/` as the repository owner.

| Evidence run | Link |
|---|---|
| Task 1 labelling (4 workers, 3,000 commands) | [42500739339](https://github.com/kumshivam0712/cloudcomputing/actions/runs/42500739339) |
| Task 2 training v1/v2 + Releases | [42518210435](https://github.com/kumshivam0712/cloudcomputing/actions/runs/42518210435) |
| Task 2 evaluation (final code) | [42524318612](https://github.com/kumshivam0712/cloudcomputing/actions/runs/42524318612) |
| Tasks 3/4/6/7 deployment and experiments | [42524321276](https://github.com/kumshivam0712/cloudcomputing/actions/runs/42524321276) |
| CI with the untrained model (quality gate fails) | [42524323815](https://github.com/kumshivam0712/cloudcomputing/actions/runs/42524323815) |
| CI with model-v1 (all stages pass) | [42524310266](https://github.com/kumshivam0712/cloudcomputing/actions/runs/42524310266) |

## Submission package

1. Scan the handwritten reflection and upload it to the repository as `reflection/scan.pdf`.
2. Actions → **submission** → Run workflow with your full name and roll number. It fills in
   `⟨NAME⟩`/`⟨ROLL⟩` in the report, rebuilds `report/report.pdf`, commits, moves the tag `final`
   to that commit and publishes `<roll_number>.zip` (source tree of `final` + `<roll_number>.pdf`)
   as the Release `submission`. Locally: `scripts/package_submission.sh ROLL reflection/scan.pdf final`.

## Shut down

```bash
make down
```

deletes the k3d cluster and everything in it (`k3d cluster delete --config cluster/k3d.yaml`).
