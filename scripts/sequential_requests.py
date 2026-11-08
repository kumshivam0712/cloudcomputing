"""Send N POST /parse requests one after another (Task 3) and record status, latency, headers.

    python scripts/sequential_requests.py --url http://localhost:8001/parse --n 50 --out results/task3/sequential_50.csv
Standard library only.
"""
import argparse
import csv
import itertools
import json
import statistics
import time
import urllib.error
import urllib.request


def post(url, text, timeout=30):
    req = urllib.request.Request(url, data=json.dumps({"text": text}).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body, code, headers = r.read().decode(), r.status, r.headers
    except urllib.error.HTTPError as e:
        body, code, headers = e.read().decode(), e.code, e.headers
    return code, (time.perf_counter() - t0) * 1000, headers, body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8001/parse")
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--texts", default="data/validation.jsonl")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    texts = itertools.cycle(json.loads(line)["text"] for line in open(a.texts, encoding="utf-8") if line.strip())
    rows = []
    for i in range(1, a.n + 1):
        text = next(texts)
        code, ms, headers, body = post(a.url, text)
        rows.append({"n": i, "status": code, "latency_ms": round(ms, 1),
                     "x_model_version": headers.get("X-Model-Version"), "x_served_by": headers.get("X-Served-By"),
                     "text": text, "body": body})
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    lat = sorted(r["latency_ms"] for r in rows)
    ok = sum(r["status"] == 200 for r in rows)
    summary = {"requests": len(rows), "http_200": ok, "http_500": sum(r["status"] == 500 for r in rows),
               "other": len(rows) - ok - sum(r["status"] == 500 for r in rows),
               "latency_ms_mean": round(statistics.mean(lat), 1), "latency_ms_p50": lat[len(lat) // 2],
               "latency_ms_p95": lat[min(len(lat) - 1, int(0.95 * len(lat)))], "latency_ms_max": lat[-1]}
    print(json.dumps(summary, indent=2))
    with open(a.out.replace(".csv", "_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)


if __name__ == "__main__":
    main()
