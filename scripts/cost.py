"""Task 7 cost estimate (standard library only).

cost per 1,000 requests = (hourly cost of all running replicas / requests served per hour) * 1000
Each replica is billed for its CPU LIMIT and MEMORY LIMIT for every hour it runs.

    python scripts/cost.py [--stats results/loadtest_stats.csv] [--replicas 2] [--cpu 1] [--mem-gib 1]
"""
import argparse
import csv
import json


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stats", default="results/loadtest_stats.csv")
    ap.add_argument("--rate-card", default="data/rate_card.json")
    ap.add_argument("--replicas", type=int, default=2)
    ap.add_argument("--cpu", type=float, default=1.0, help="CPU limit per replica (vCPU)")
    ap.add_argument("--mem-gib", type=float, default=1.0, help="memory limit per replica (GiB)")
    ap.add_argument("--out", default="results/task7/cost.json")
    a = ap.parse_args()

    rate = json.load(open(a.rate_card, encoding="utf-8"))
    with open(a.stats, encoding="utf-8") as f:
        agg = next(r for r in csv.DictReader(f) if r["Name"] == "Aggregated")
    rps = float(agg["Requests/s"])
    fails = int(agg["Failure Count"])
    reqs = int(agg["Request Count"])
    ok_rps = rps * (reqs - fails) / reqs if reqs else 0.0

    per_replica = a.cpu * rate["vcpu_hour"] + a.mem_gib * rate["gib_memory_hour"]
    hourly = a.replicas * per_replica
    per_hour = rps * 3600
    cost_1000 = hourly / per_hour * 1000
    steps = [
        f"per replica per hour = {a.cpu:g} vCPU x {rate['vcpu_hour']:.2f} + {a.mem_gib:g} GiB x "
        f"{rate['gib_memory_hour']:.2f} = {per_replica:.4f} {rate['currency']}/h",
        f"all replicas per hour = {a.replicas} x {per_replica:.4f} = {hourly:.4f} {rate['currency']}/h",
        f"requests per hour = {rps:.3f} req/s x 3600 = {per_hour:.1f}",
        f"cost per 1,000 requests = {hourly:.4f} / {per_hour:.1f} x 1000 = {cost_1000:.4f} {rate['currency']}",
    ]
    out = {"currency": rate["currency"], "replicas": a.replicas, "cpu_limit_vcpu": a.cpu, "memory_limit_gib": a.mem_gib,
           "requests_per_s": rps, "successful_requests_per_s": round(ok_rps, 3),
           "hourly_cost_per_replica": round(per_replica, 4), "hourly_cost_all_replicas": round(hourly, 4),
           "requests_per_hour": round(per_hour, 1), "cost_per_1000_requests": round(cost_1000, 4), "steps": steps}
    print("\n".join(steps))
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)


if __name__ == "__main__":
    main()
