"""Generate predictions for score.py with a student (or the untrained base) model.

    python training/predict.py --model build/models/v1 --gold data/validation.jsonl \
        --out results/student_v1_predictions.jsonl
    python training/predict.py --model EleutherAI/pythia-70m --revision a39f36b... --out ...

Writes {"id", "prediction"} lines (the raw text the model produced, up to the first newline)
and, next to it, *_raw.jsonl with the full generated continuation and the time per command.
Uses exactly the same generation code as the service (service/model.py).
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "service"))


def raw_path_for(out):
    """results/x_predictions.jsonl -> results/x_raw.jsonl; any other name -> <stem>.raw.jsonl (never the same file)."""
    out = Path(out)
    if "_predictions" in out.name:
        return out.with_name(out.name.replace("_predictions", "_raw"))
    return out.with_name(out.stem + ".raw" + out.suffix)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="local directory or Hugging Face model id")
    ap.add_argument("--revision", default=None)
    ap.add_argument("--gold", default="data/validation.jsonl")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-new-tokens", type=int, default=48)
    ap.add_argument("--threads", type=int, default=0)
    a = ap.parse_args()

    from model import ParserModel  # imported here so the helpers above need no torch

    model = ParserModel(a.model, max_new_tokens=a.max_new_tokens, num_threads=a.threads or None, revision=a.revision)
    gold = [json.loads(line) for line in open(a.gold, encoding="utf-8") if line.strip()]
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    raw_path = raw_path_for(out)
    t_all = time.time()
    with open(out, "w", encoding="utf-8") as fp, open(raw_path, "w", encoding="utf-8") as fr:
        for g in gold:
            t0 = time.time()
            generated, pred = model.generate_raw(g["text"])
            fp.write(json.dumps({"id": g["id"], "prediction": pred}, ensure_ascii=False) + "\n")
            fr.write(json.dumps({"id": g["id"], "text": g["text"], "generated": generated, "prediction": pred,
                                 "seconds": round(time.time() - t0, 3)}, ensure_ascii=False) + "\n")
    print(f"{len(gold)} predictions -> {out} (raw: {raw_path}) in {time.time() - t_all:.1f}s")


if __name__ == "__main__":
    main()
