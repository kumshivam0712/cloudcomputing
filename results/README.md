# Evidence index

Every number in `report/report.pdf` is read from a file in this folder. Files are written by
scripts or by the GitHub Actions workflows (which commit them back to the repository).

| Task | Files | Produced by |
|---|---|---|
| 1 Cluster + storage | `task1/cluster.txt`, `task1/storage.txt` | `scripts/collect_task1.sh` (label workflow) |
| 1 Parallel workers | `task1/pipeline.txt` (Pod start/finish times per SHARD_INDEX), `task1/worker-shard-*.log` | label workflow |
| 1 Teacher | `task1/teacher.txt` (model digest, options, prompt sha256), `task1/teacher_eval.log` | label workflow |
| 1 Cleaning | `task1/clean_report.json` (counts, coverage, sha256), `task1/rejected.jsonl`, `task1/verify_checksum.txt`, `task1/clean.log` | `worker/clean.py`, `make verify-data` |
| 2 Teacher on validation | `teacher_validation_raw.jsonl`, `teacher_validation_predictions.jsonl`, `teacher_validation.json` | `scripts/teacher_eval.py`, `tools/score.py` |
| 2 Untrained Pythia-70M | `pythia_base_raw.jsonl`, `pythia_base_predictions.jsonl`, `pythia_base_validation.json` | `training/predict.py`, `tools/score.py` |
| 2 Student v1 / v2 | `student_v1_*`, `student_v2_*` (raw, predictions, score) | train workflow |
| 2 Training logs | `task2/train_v1.log`, `task2/train_v2.log`, `task2/train_subset50.log`, `task2/loss_subset50.csv`, `task2/comparison.md`, `task2/release_checksum_check.txt` | train workflow (`../training/loss.csv`, `../training/loss_v2.csv`) |
| 3 Container | `task3/image.txt`, `task3/no_weights_in_image.txt`, `task3/pip_freeze_in_image.txt`, `task3/limits.txt`, `task3/sequential_50.csv`, `task3/memory_peak_bytes.txt`, `task3/docker_stats.csv`, `task3/oom_check.txt`, `task3/fault_inject.txt`, `task3/summary.json` | `scripts/experiments.sh task3` |
| 4 Kubernetes | `task4/resources.txt`, `task4/describe_deployment.txt`, `task4/parse_through_ingress.txt`, `task4/models_bucket.txt`, `task4/coldstart/`, `task4/cold_start_summary.json`, `task4/rolling/`, `task4/recovery/`, `task4/hpa/`, `task4/loadbalance_headers.json`, `task4/final_state.txt` | `scripts/experiments.sh` |
| 5 Network | `task5/subnets_table.md`, `task5/subnets.json`, `task5/nacl_check.txt` | `scripts/subnets.py`, `tools/nacl_sim.py` |
| 6 Make / CI | `task6/make_up.log`, `task6/make_down.log`, CI run links in the report | deploy workflow, `ci.yml` |
| 7 Load test | `loadtest_stats.csv`, `loadtest_stats_history.csv`, `loadtest_failures.csv`, `loadtest_headers.json` (standard command), `task7/locust_stdout.txt`, `task7/top_pods.txt`, `task7/loadtest_summary.json`, `task7/cost.json`, `task7/cost.txt` | `scripts/experiments.sh standard`, `scripts/cost.py` |
