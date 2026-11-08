<h1>Knowledge Distillation and Deployment of a Command-Parsing Model on a Local Cloud</h1>
<div class="meta"><b>Name:</b> ⟨NAME⟩ &nbsp;·&nbsp; <b>Roll number:</b> ⟨ROLL⟩ &nbsp;·&nbsp; CS3081 Cloud Computing mini project &nbsp;·&nbsp;
<b>Repository:</b> <a href="https://github.com/kumshivam0712/cloudcomputing">github.com/kumshivam0712/cloudcomputing</a> (tag <code>final</code>)</div>

<p class="legend"><b>Reading guide.</b> <span class="m">Green</span> = measured (copied from a file in <code>results/</code>, produced by a script or workflow run); <span class="a">amber</span> = assumption or design choice. All runs used GitHub-hosted runners (Ubuntu 24.04, 4 vCPU, 16 GB RAM, no GPU) as the "laptop": every task ran on one such machine inside a k3d cluster created from <code>cluster/k3d.yaml</code>.</p>

## Architecture

⟨ARCH⟩

## 1 · Object storage and parallel teacher labelling

⟨T1⟩

**Sharding (design).** A worker with `SHARD_INDEX=i`, `SHARD_COUNT=K` takes the pool lines *n* with *n* mod *K* = *i* (striping), so the shards are disjoint and together cover every line - no coordination, locks or queue are needed, and each worker writes only its own object `datasets/teacher/shard-i.jsonl`, so there is no write contention in S3 (objects cannot be appended to safely by two writers). Striping (instead of contiguous blocks) spreads the duplicates and intents evenly and gives every worker the same amount of work (750 lines each for K = 4). The workers are one Kubernetes **Indexed Job** (`completions = parallelism = K`), and `SHARD_INDEX` is read from the Pod's completion-index annotation through the downward API, so a Pod that is restarted keeps its index. Each worker re-uploads its object every 25 records and skips ids already present when it starts, so a restart neither loses nor repeats work. K = 4 matches `OLLAMA_NUM_PARALLEL=4` decoding slots in the single CPU-bound teacher: more workers than slots would only queue. `clean.py` checks coverage (no id missing, repeated or unknown) before writing the training set.

## 2 · Training the student (sequence-level distillation)

⟨T2⟩

**Sequence-level vs logit-based distillation.** *(a) Sequence-level KD* (Kim & Rush, 2016) trains the student with ordinary cross-entropy on the teacher's **generated output sequence** - here the teacher's greedy JSON reply - as if it were the gold label; the teacher's knowledge is passed only through which answer it chose. *(b) Logit-based (word-level) KD* (Hinton et al., 2015; TRL `GKDTrainer`/`DistillationTrainer`) trains the student to match the teacher's **full next-token probability distribution** at every position, usually by minimising the KL divergence between temperature-softened teacher and student distributions; it transfers "dark knowledge" (how plausible the teacher found the alternatives). *(c) Why it is not possible here:* the teacher is reached only through Ollama's text API, which returns the generated text, not the full-vocabulary logits at each step; and even with logits, phi3.5 (Llama-style SentencePiece vocabulary of 32,064 tokens) and Pythia-70M (GPT-NeoX BPE, 50,304 entries) tokenise text differently, so the two distributions are over different token sets and positions and cannot be compared term by term without an extra alignment method. *(d) A real limitation of what I did:* the student only ever sees the teacher's single answer, so it inherits the teacher's mistakes as if they were truth (the teacher itself is only ⟨TEACHER_FF⟩ % full-frame correct on validation, and 1,500 examples is small), and it gets no signal about how confident the teacher was.

## 3 · Inference service in a container

⟨T3⟩

## 4 · Kubernetes deployment, scaling and reliability

⟨T4⟩

## 5 · Subnetting and network access control

⟨T5⟩

**Why separate reply rules, and why order matters.** A NACL is **stateless**: it does not remember that a packet belongs to a connection it already allowed, so every packet - including a reply - is checked on its own against the rules for its direction. A client's request to the load balancer arrives on port 80/443, but the response leaves towards the client's *ephemeral* port (1024-65535); likewise the app's answer to the load balancer's request to port 8000 comes back to the load balancer's ephemeral port. Without outbound rule 110 and inbound rule 130 these replies would hit the implicit deny and every connection would hang. Rules are evaluated from the lowest number up and the first match decides, so the deny for 198.51.100.0/24 must have a **lower number (90)** than the allow-anywhere rules for 80/443 (100, 110). If it were numbered, say, 200, a packet from 198.51.100.9 to port 443 would match rule 110 first and be allowed, and the deny would never be reached (sample packet S04 checks exactly this).

## 6 · Reproducibility, testing and CI/CD

**Architecture.** Everything is in Git: code, tests, prompts, configs, manifests, network files, workflows, and the *outputs* that are small (teacher shards, `train.jsonl`, checksums, every result file). Model weights are kept out of Git (`.gitignore`) and live in object storage and GitHub Releases. Four GitHub Actions workflows reproduce the project on clean `ubuntu-24.04` runners and commit their evidence back as the repository owner: `label.yml` (Task 1), `train.yml` (Task 2), `deploy.yml` (Tasks 3/4/7: fresh clone → `make up` → experiments → `make down`) and **`ci.yml`** (Task 6).

**`make up` / `make down`.** From a fresh clone: `git clone …`, `cd cloudcomputing`, `make up` (three commands). `make up` = tools venv → k3d cluster → SeaweedFS + buckets + kit upload → models from the Release (checksum-verified) to `s3://models/v1|v2/` → image build + `k3d image import` → `kubectl apply -f k8s/app/` → wait for `/readyz` through the Ingress. ⟨MAKEUP⟩ `make down` runs `k3d cluster delete --config cluster/k3d.yaml` (log: `results/task6/make_down.log`, `k3d cluster list` empty afterwards).

**CI pipeline (`ci.yml`, on every push and on demand)** - stages run in this order, each `needs` the previous one: (1) **lint** - ruff (pinned 0.8.4, rules E/F/W/B/I), `bash -n` on scripts, JSON/YAML syntax of NACL, manifests and workflows; (2) **unit tests** - 19 pytest tests (clean.py rules and counts, shard partitioning, service endpoints/headers/500 body/FAULT_INJECT, schema validator, prompt format, subnets, NACL); (3) **model evaluation** - downloads the model from the GitHub Release (`gh release download model-v1`), verifies `sha256sum -c model.sha256`, runs `predict.py` + `score.py` on `validation.jsonl`; (4) **quality gate** - `score.py --min-validity 95`. A parallel **secret-scan** job runs gitleaks 8.21.2 over the whole Git history. ⟨CIRUNS⟩

**AI use** is documented in `AI_USE.md` (tool, purpose, how every output was verified).

**Limitations / improvements.** CI evaluates on the 100 public validation commands only; a held-out "canary" set would protect against over-fitting the gate. The workflows use the runner as the "laptop", so `make up` was never run on a Windows/macOS host; a devcontainer would pin the host tools (k3d, kubectl) as well.

## 7 · Performance, cost and review

⟨T7⟩

## References

1. Y. Kim, A. M. Rush. *Sequence-Level Knowledge Distillation.* EMNLP 2016. 2. G. Hinton, O. Vinyals, J. Dean. *Distilling the Knowledge in a Neural Network.* 2015. 3. Y.-C. Chen et al. *Distilling Knowledge Learned in BERT for Text Generation.* ACL 2020. 4. E. Bastianelli et al. *SLURP: A Spoken Language Understanding Resource Package.* EMNLP 2020. 5. S. Biderman et al. *Pythia* (EleutherAI/pythia-70m model card). 6. Hugging Face Transformers and TRL documentation. 7. k3d, k3s, SeaweedFS, Ollama, Locust, gitleaks and Kubernetes documentation (Deployments, Services, Probes, HPA, Secrets, resource metrics pipeline). 8. AWS VPC User Guide, *Network ACLs*. 9. Google SRE Book, *Service Level Objectives*.
