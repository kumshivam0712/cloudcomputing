"""Pod creation -> Ready times from `kubectl get pods -o json` (Task 4 cold start).

    kubectl -n app get pods -l app=parser -o json | python scripts/pod_times.py [--exclude a,b]
Prints one JSON object per pod: name, created, ready, seconds (Ready.lastTransitionTime - creationTimestamp).
"""
import argparse
import json
import sys
from datetime import datetime


def ts(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exclude", default="", help="comma-separated pod names to ignore (the deleted ones)")
    a = ap.parse_args()
    skip = set(filter(None, a.exclude.split(",")))
    for pod in json.load(sys.stdin)["items"]:
        name = pod["metadata"]["name"]
        if name in skip or pod["metadata"].get("deletionTimestamp"):
            continue
        ready = next((c for c in pod["status"].get("conditions", []) if c["type"] == "Ready"), None)
        if not ready or ready["status"] != "True":
            continue
        created = pod["metadata"]["creationTimestamp"]
        print(json.dumps({"pod": name, "created": created, "ready": ready["lastTransitionTime"],
                          "seconds": (ts(ready["lastTransitionTime"]) - ts(created)).total_seconds()}))


if __name__ == "__main__":
    main()
