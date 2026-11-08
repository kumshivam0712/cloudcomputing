"""Run the teacher (same prompt and settings as Task 1) on validation.jsonl.

  python scripts/teacher_eval.py --url http://localhost:11434 \
      --gold data/validation.jsonl --raw results/teacher_validation_raw.jsonl \
      --pred results/teacher_validation_predictions.jsonl [--workers 4]

Then score with: python tools/score.py results/teacher_validation_predictions.jsonl \
      data/validation.jsonl --out results/teacher_validation.json
"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "worker"))
import teacher  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:11434")
    ap.add_argument("--gold", default="data/validation.jsonl")
    ap.add_argument("--prompt", default="prompts/teacher_prompt.txt")
    ap.add_argument("--raw", default="results/teacher_validation_raw.jsonl")
    ap.add_argument("--pred", default="results/teacher_validation_predictions.jsonl")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()

    template = teacher.load_prompt(a.prompt)
    gold = [json.loads(line) for line in open(a.gold, encoding="utf-8") if line.strip()]
    teacher.wait_until_ready(a.url)
    t0 = time.time()

    def run(g):
        return teacher.generate(a.url, teacher.build_prompt(template, g["text"]))

    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        replies = list(pool.map(run, gold))
    elapsed = time.time() - t0
    os.makedirs(os.path.dirname(a.raw) or ".", exist_ok=True)
    with open(a.raw, "w", encoding="utf-8") as f:
        for g, r in zip(gold, replies):
            f.write(json.dumps({"id": g["id"], "text": g["text"], "teacher_raw": r}, ensure_ascii=False) + "\n")
    with open(a.pred, "w", encoding="utf-8") as f:
        for g, r in zip(gold, replies):
            f.write(json.dumps({"id": g["id"], "prediction": r}, ensure_ascii=False) + "\n")
    print(f"teacher labelled {len(gold)} validation commands in {elapsed:.1f}s "
          f"({elapsed / len(gold):.2f} s/command with {a.workers} concurrent requests)")


if __name__ == "__main__":
    main()
