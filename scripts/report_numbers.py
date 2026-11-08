"""Print every measured number used in the report, straight from results/ (standard library only).

    python scripts/report_numbers.py > results/report_numbers.json
"""
import csv
import glob
import json
import os
import re

R = "results"


def load(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def text(path, default=""):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return default


def loss(path):
    try:
        with open(path, encoding="utf-8") as f:
            return [{"epoch": int(r["epoch"]), "loss": float(r["train_loss"]), "seconds": float(r["seconds"])}
                    for r in csv.DictReader(f)]
    except OSError:
        return []


def top_pods(path):
    """Max CPU (m) and memory (Mi) per Pod seen in `kubectl top pods` samples."""
    out = {}
    for line in text(path).splitlines():
        m = re.match(r"(\S+)\s+(\d+)m\s+(\d+)Mi", line)
        if m:
            pod, cpu, mem = m.group(1), int(m.group(2)), int(m.group(3))
            o = out.setdefault(pod, {"cpu_m": [], "mem_mi": []})
            o["cpu_m"].append(cpu)
            o["mem_mi"].append(mem)
    def avg(xs):
        return round(sum(xs) / len(xs))

    return {p: {"samples": len(v["cpu_m"]), "cpu_m_max": max(v["cpu_m"]), "cpu_m_avg": avg(v["cpu_m"]),
                "mem_mi_max": max(v["mem_mi"]), "mem_mi_avg": avg(v["mem_mi"])}
            for p, v in out.items()}


def image_size(path):
    m = re.search(r"size_bytes=(\d+)", text(path))
    return int(m.group(1)) if m else None


def main():
    n = {}
    n["task1_clean"] = load(f"{R}/task1/clean_report.json")
    n["task1_shard_meta"] = [load(p) for p in sorted(glob.glob("datasets/teacher/shard-*.meta.json"))]
    n["teacher_validation"] = load(f"{R}/teacher_validation.json")
    for name in ("pythia_base", "student_v1", "student_v2"):
        n[f"{name}_validation"] = load(f"{R}/{name}_validation.json")
    n["loss_v1"] = loss("training/loss.csv")
    n["loss_v2"] = loss("training/loss_v2.csv")
    n["task3"] = load(f"{R}/task3/summary.json")
    n["task3_image_bytes"] = image_size(f"{R}/task3/image.txt")
    n["task3_fault_inject"] = text(f"{R}/task3/fault_inject.txt").strip().splitlines()[-1:] or None
    n["task4_cold_start"] = load(f"{R}/task4/cold_start_summary.json")
    for step in ("rolling", "recovery", "hpa"):
        n[f"task4_{step}_locust"] = load(f"{R}/task4/{step}/locust_summary.json")
        n[f"task4_{step}_timeline"] = text(f"{R}/task4/{step}/timeline.txt").strip().splitlines()
    n["task4_versions_after_update"] = text(f"{R}/task4/rolling/versions_after_update.txt").strip().splitlines()
    n["task4_versions_after_rollback"] = text(f"{R}/task4/rolling/versions_after_rollback.txt").strip().splitlines()
    n["task7_loadtest"] = load(f"{R}/task7/loadtest_summary.json")
    n["task7_top_pods"] = top_pods(f"{R}/task7/top_pods.txt")
    n["task7_cost"] = load(f"{R}/task7/cost.json")
    n["make_up_seconds"] = (re.findall(r"make up finished in (\d+) s", text(f"{R}/task6/make_up.log")) or [None])[-1]
    print(json.dumps(n, indent=2))


if __name__ == "__main__":
    os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    main()
