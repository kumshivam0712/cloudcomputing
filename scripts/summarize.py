"""Summaries of measured results (standard library only).

  python scripts/summarize.py locust PREFIX          Locust PREFIX_stats.csv (+ PREFIX_headers.json)
  python scripts/summarize.py task3 results/task3    peak memory and the 50 sequential requests
  python scripts/summarize.py coldstart DIR          runN-times.jsonl -> per-run and median
  python scripts/summarize.py compare                the three validation score reports side by side
"""
import csv
import glob
import json
import os
import re
import statistics
import sys


def locust(prefix):
    with open(prefix + "_stats.csv", encoding="utf-8") as f:
        agg = next(r for r in csv.DictReader(f) if r["Name"] == "Aggregated")
    req, fail = int(agg["Request Count"]), int(agg["Failure Count"])
    out = {
        "requests": req, "failures": fail, "failure_pct": round(100.0 * fail / req, 3) if req else None,
        "p50_ms": float(agg["50%"]), "p95_ms": float(agg["95%"]), "p99_ms": float(agg["99%"]),
        "avg_ms": round(float(agg["Average Response Time"]), 1), "max_ms": float(agg["Max Response Time"]),
        "requests_per_s": round(float(agg["Requests/s"]), 3),
    }
    hdr = prefix + "_headers.json"
    if not os.path.exists(hdr) and os.path.basename(prefix) == "loadtest":
        hdr = os.path.join(os.path.dirname(prefix), "loadtest_headers.json")
    if os.path.exists(hdr):
        h = json.load(open(hdr, encoding="utf-8"))
        out.update(h)
        ok = sum(h.get("per_replica", {}).values())
        if ok:
            out["per_replica_share_pct"] = {k: round(100.0 * v / ok, 1) for k, v in h["per_replica"].items()}
    return out


def _mib(s):
    m = re.match(r"([\d.]+)\s*([KMG]i?B)", s.strip())
    if not m:
        return None
    unit = {"KiB": 1 / 1024, "MiB": 1, "GiB": 1024, "kB": 1 / 1024, "KB": 1 / 1024, "MB": 1, "GB": 1024}[m.group(2)]
    return float(m.group(1)) * unit


def task3(d):
    out = {}
    try:
        out["cgroup_memory_peak_bytes"] = int(open(os.path.join(d, "memory_peak_bytes.txt")).read().split()[0])
        out["cgroup_memory_peak_mib"] = round(out["cgroup_memory_peak_bytes"] / 2**20, 1)
    except (OSError, ValueError, IndexError):
        out["cgroup_memory_peak_bytes"] = None
    usages = []
    for line in open(os.path.join(d, "docker_stats.csv"), encoding="utf-8"):
        parts = line.strip().split(",")
        if len(parts) >= 3 and "/" in parts[2]:
            v = _mib(parts[2].split("/")[0])
            if v is not None:
                usages.append(v)
    out["docker_stats_samples"] = len(usages)
    out["docker_stats_peak_mib"] = round(max(usages), 1) if usages else None
    out["sequential_50"] = json.load(open(os.path.join(d, "sequential_50_summary.json"), encoding="utf-8"))
    out["oom_check"] = open(os.path.join(d, "oom_check.txt")).read().strip()
    return out


def coldstart(d):
    runs = []
    for path in sorted(glob.glob(os.path.join(d, "run*-times.jsonl"))):
        pods = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
        if pods:
            runs.append({"run": os.path.basename(path).split("-")[0], "pods": pods,
                         "max_seconds": max(p["seconds"] for p in pods),
                         "mean_seconds": round(statistics.mean(p["seconds"] for p in pods), 1)})
    all_pods = [p["seconds"] for r in runs for p in r["pods"]]
    return {"runs": runs,
            "median_of_runs_seconds (slowest pod per run)": statistics.median(r["max_seconds"] for r in runs),
            "median_over_all_pods_seconds": statistics.median(all_pods) if all_pods else None}


def compare():
    names = {"teacher (phi3.5)": "results/teacher_validation.json",
             "Pythia-70M untrained": "results/pythia_base_validation.json",
             "student v1": "results/student_v1_validation.json",
             "student v2": "results/student_v2_validation.json"}
    keys = ["json_validity", "intent_accuracy", "date_accuracy", "time_accuracy", "place_accuracy", "full_frame"]
    lines = ["| Model | " + " | ".join(keys) + " |", "|---|" + "---:|" * len(keys)]
    for name, path in names.items():
        if os.path.exists(path):
            r = json.load(open(path))
            lines.append(f"| {name} | " + " | ".join(f"{r[k]:.1f}" for k in keys) + " |")
    return "\n".join(lines)


def main():
    cmd = sys.argv[1]
    if cmd == "locust":
        print(json.dumps(locust(sys.argv[2]), indent=2))
    elif cmd == "task3":
        print(json.dumps(task3(sys.argv[2]), indent=2))
    elif cmd == "coldstart":
        print(json.dumps(coldstart(sys.argv[2]), indent=2))
    elif cmd == "compare":
        print(compare())
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
