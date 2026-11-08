# CI runs (ci.yml) used as evidence

Final code (commit 2b30c5b, with the beam-search retry):

| Run | Model | lint | unit tests (21) | evaluate | quality gate | secret scan (gitleaks) |
|---|---|---|---|---|---|---|
| [42524323815](https://github.com/kumshivam0712/cloudcomputing/actions/runs/42524323815) | `model-base` (untrained Pythia-70M, deliberately bad) | success | success | success | **failure** | success (no leaks) |
| [42524310266](https://github.com/kumshivam0712/cloudcomputing/actions/runs/42524310266) | `model-v1` (distilled student) | success | success | success | **success** | success (no leaks) |

The same pair on the earlier code (commit 3d51f4f, greedy decoding only) behaved identically:
[42522194726](https://github.com/kumshivam0712/cloudcomputing/actions/runs/42522194726) (model-base, gate failed) and
[42522190946](https://github.com/kumshivam0712/cloudcomputing/actions/runs/42522190946) (model-v1, gate passed).

Quality-gate step output of a failed run (job 128858301836 of run 42522194726, copied from the run log):

```
$ python3 tools/score.py build/eval/predictions.jsonl data/validation.jsonl --min-validity 95
QUALITY GATE FAILED: json_validity 0.0 < 95.0
{ "json_validity": 0.0, "intent_accuracy": 0.0, "date_accuracy": 0.0, "time_accuracy": 0.0,
  "place_accuracy": 0.0, "full_frame": 0.0, "examples": 100, "missing_predictions": 0 }
##[error]Process completed with exit code 1.
```

Earlier failing CI runs (before 20:50 UTC on 2026-11-08) failed at the *evaluate* stage only because
the model Release did not exist yet, or because of the `predict.py` output-path bug fixed in commit
3d51f4f; they are not quality-gate demonstrations.
