# AI use

## Tools used

| Tool | Used for |
|---|---|
| **Claude Code** (Anthropic's coding agent, run as a cloud session connected to this GitHub repository) | Reading the assignment PDF and the student kit; designing the architecture; writing the code (worker, clean.py, training, service, Kubernetes manifests, Makefile, GitHub Actions workflows, unit tests); computing the subnet table; drafting `report/report.md` and the README; generating the report PDF. |

No AI model was used *inside* the system except the two the assignment prescribes: the teacher
(`phi3.5` served by Ollama, temperature 0, seed 42) and the student (`EleutherAI/pythia-70m`).
No paid API and no other model's outputs were used as training data; the student was trained only
on the teacher's replies in `datasets/v1/train.jsonl`.

## How the AI output was checked

The rule followed was: **nothing in the report is typed by hand or by the AI - every number is read
from a file that a script or a workflow run produced**, and each such file is in `results/`.

1. **Code is executed, not just read.** Every component ran end to end on GitHub Actions
   (`.github/workflows/`): labelling (`label.yml`), training (`train.yml`), deployment and
   experiments (`deploy.yml`) and CI (`ci.yml`). The workflow logs and the files they committed are
   the evidence. Failures during development (a YAML quoting error in a workflow, a missing
   `accelerate` dependency for `low_cpu_mem_usage`, a line too long for ruff, a smoke test that
   failed with the deliberately bad model, and an AI-written `predict.py` that wrote its raw output
   into the predictions file when that file was not named `*_predictions.jsonl` - caught by the CI
   evaluation stage, fixed, and covered by a new unit test) were found by running the code.
2. **Unit tests** (`tests/`, 21 tests) pin down the behaviour the assignment specifies: clean.py rules
   (a)-(e) and the count identity, shard partitioning without gaps or repeats, the exact
   `{"error": "invalid_model_output"}` body and HTTP 500 for invalid output and for `FAULT_INJECT=1`,
   both response headers, the subnet table and the NACL decisions.
3. **The kit's own tools are the judges**: `tools/score.py` for every model, `tools/nacl_sim.py`
   for the NACL, `tools/locustfile.py` for every load test. Kit files are used unchanged.
4. **Independent re-computation**: the training-set checksum is recomputed by running `clean.py`
   again on the downloaded shard files (`make verify-data`); model checksums are verified after
   downloading the GitHub Release assets (`sha256sum -c`); the subnet table was derived by hand
   (working in `network/subnets.md`) and checked by `scripts/subnets.py` and a unit test.
5. **AI suggestions that were wrong or rejected**: an AI-written test expectation claimed outbound
   TCP 8000 to a non-app host should be denied; the simulator showed it is allowed, and the
   analysis confirmed that this is unavoidable for a stateless NACL whose reply rule must open the
   whole ephemeral range 1024-65535 (documented in `network/subnets.md`). The teacher prompt's
   examples were checked so that none of them comes from `validation.jsonl`.
6. **Limits of the check**: the AI cannot judge the student model's quality; the reported accuracies
   are whatever `score.py` measured, including the student's errors.
