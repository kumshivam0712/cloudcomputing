# Archived: first deployment run (greedy decoding only)

Workflow run [42521715011](https://github.com/kumshivam0712/cloudcomputing/actions/runs/42521715011),
before the beam-search retry was added to the service. Kept as evidence of what changed.

Every failed request in every load test of this run was an HTTP 500 `invalid_model_output` for the
same validation command, V028 "what is the weather at home" (greedy output
`{"intent": "weather_query", "date": null, "time": "s. null, "place": null}`). There were **no**
connection errors, 502 or 503 answers, i.e. no request was lost to the rolling update, the Pod
deletion or the scaling - but because Locust cycles through the 100 validation commands, ~1 % of all
requests failed by construction:

| Test | Requests | Failures (all HTTP 500 for V028) | Failure % |
|---|---:|---:|---:|
| Standard load test (task7) | 506 | 5 | 0.99 |
| Rolling update v1 -> v2 -> v1 | 1,403 | 12 | 0.86 |
| Recovery (Pod deleted) | 719 | 7 | 0.97 |
| HPA 1 -> 2 -> 1 | 1,167 | 12 | 1.03 |

The final results in `results/task3`, `results/task4`, `results/task7` come from the re-run with the
retry enabled.
