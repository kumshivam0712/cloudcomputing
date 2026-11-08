"""Clean the teacher's shard outputs into the training set (Task 1, step 6).

    python worker/clean.py --shards datasets/teacher --out datasets/v1 [--pool data/commands_pool.jsonl]
    python worker/clean.py --shards s3://datasets/teacher/ --out s3://datasets/v1/      (inside the cluster)

Reads every shard-*.jsonl under --shards, removes bad records and writes, in id order,
<out>/train.jsonl and <out>/train.sha256 (sha256sum format). Each record is checked in this
order and counted under the FIRST rule it breaks:
  (a) invalid_json   teacher_raw is not valid JSON
  (b) wrong_keys     not an object whose keys are exactly intent, date, time, place
  (c) bad_intent     intent is not one of the eight intents
  (d) bad_slot       a slot is neither null nor a non-empty string that appears in the command
                     (compared lower-cased with runs of spaces collapsed)
  (e) duplicate      the same command (lower-cased, spaces collapsed) was already kept with a
                     smaller id; duplicates are resolved after (a)-(d), so the smallest-id VALID
                     copy is the one kept
so that   input = a + b + c + d + duplicates + kept.
Each kept line is {"id", "text", "intent", "date", "time", "place", "teacher_raw"}: the four
values are the teacher's own values, unchanged; teacher_raw is the exact reply.
"""
import argparse
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import storage  # noqa: E402

KEYS = ("intent", "date", "time", "place")
SLOTS = ("date", "time", "place")
DEFAULT_INTENTS = (
    "alarm_set", "alarm_query", "calendar_set", "calendar_query",
    "calendar_remove", "weather_query", "datetime_query", "recommendation_events",
)
REASONS = ("invalid_json", "wrong_keys", "bad_intent", "bad_slot")
SHARD_RE = re.compile(r"shard-(\d+)\.jsonl$")


def norm(s):
    return " ".join(str(s).lower().split())


def id_key(record_id):
    digits = re.sub(r"\D", "", record_id)
    return (int(digits) if digits else -1, record_id)


def check(record, intents=DEFAULT_INTENTS):
    """Return (reason, parsed). reason is None for a good record."""
    try:
        obj = json.loads(record["teacher_raw"])
    except (json.JSONDecodeError, TypeError):
        return "invalid_json", None
    if not isinstance(obj, dict) or set(obj) != set(KEYS) or len(obj) != len(KEYS):
        return "wrong_keys", None
    if not isinstance(obj["intent"], str) or obj["intent"] not in intents:
        return "bad_intent", None
    command = norm(record["text"])
    for slot in SLOTS:
        v = obj[slot]
        if v is None:
            continue
        if not isinstance(v, str) or not v.strip() or norm(v) not in command:
            return "bad_slot", None
    return None, obj


def clean(records, intents=DEFAULT_INTENTS):
    """Return (kept_rows, counts, rejected) for records from all shards."""
    records = sorted(records, key=lambda r: id_key(r["id"]))
    counts = {"input_records": len(records), **{r: 0 for r in REASONS}, "duplicate": 0, "kept": 0}
    kept, rejected, seen = [], [], {}
    for rec in records:
        reason, obj = check(rec, intents)
        if reason is None:
            key = norm(rec["text"])
            if key in seen:
                reason = "duplicate"
            else:
                seen[key] = rec["id"]
        if reason is not None:
            counts[reason] += 1
            rejected.append({"id": rec["id"], "reason": reason,
                             **({"kept_id": seen[norm(rec["text"])]} if reason == "duplicate" else {})})
            continue
        counts["kept"] += 1
        kept.append({"id": rec["id"], "text": rec["text"], **{k: obj[k] for k in KEYS},
                     "teacher_raw": rec["teacher_raw"]})
    assert counts["input_records"] == sum(counts[r] for r in REASONS) + counts["duplicate"] + counts["kept"]
    return kept, counts, rejected


def coverage(records, pool_records):
    """Check that every pool id appears in exactly one shard output."""
    pool_ids = [r["id"] for r in pool_records]
    got = {}
    for rec in records:
        got[rec["id"]] = got.get(rec["id"], 0) + 1
    return {
        "pool_ids": len(pool_ids),
        "shard_records": len(records),
        "missing": sorted((i for i in pool_ids if i not in got), key=id_key),
        "repeated": sorted((i for i, c in got.items() if c > 1), key=id_key),
        "unknown": sorted((i for i in got if i not in set(pool_ids)), key=id_key),
    }


def to_jsonl(rows):
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)


def read_shards(shards_prefix):
    uris = [u for u in storage.list_uris(shards_prefix) if SHARD_RE.search(u)]
    if not uris:
        sys.exit(f"no shard-*.jsonl found under {shards_prefix}")
    records, per_shard = [], {}
    for uri in sorted(uris, key=lambda u: int(SHARD_RE.search(u).group(1))):
        rows = [json.loads(line) for line in storage.read_text(uri).splitlines() if line.strip()]
        per_shard[uri.rsplit("/", 1)[-1]] = len(rows)
        records += rows
    return records, per_shard


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--shards", default="s3://datasets/teacher/", help="directory or s3:// prefix with shard-*.jsonl")
    ap.add_argument("--out", default="s3://datasets/v1/", help="directory or s3:// prefix for train.jsonl/.sha256")
    ap.add_argument("--schema", default=None, help="schema.json (intents list); default: the eight intents")
    ap.add_argument("--pool", default=None, help="commands_pool.jsonl, to check shard coverage")
    ap.add_argument("--pool-limit", type=int, default=0,
                    help="coverage check on the first N pool lines only (smoke runs); 0 = all")
    ap.add_argument("--report", default=None, help="also write counts as JSON to this path/URI")
    ap.add_argument("--rejected", default=None, help="also write the rejected ids and reasons (JSONL)")
    a = ap.parse_args(argv)

    intents = DEFAULT_INTENTS
    if a.schema:
        intents = tuple(json.loads(storage.read_text(a.schema))["intents"])

    records, per_shard = read_shards(a.shards)
    kept, counts, rejected = clean(records, intents)
    body = to_jsonl(kept)
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    storage.write_text(storage.join(a.out, "train.jsonl"), body)
    storage.write_text(storage.join(a.out, "train.sha256"), f"{digest}  train.jsonl\n")

    report = {"shards": per_shard, "counts": counts, "train_sha256": digest}
    if a.pool:
        pool = [json.loads(line) for line in storage.read_text(a.pool).splitlines() if line.strip()]
        if a.pool_limit > 0:
            pool = pool[: a.pool_limit]
        report["coverage"] = coverage(records, pool)
    text = json.dumps(report, indent=2)
    print(text)
    if a.report:
        storage.write_text(a.report, text + "\n")
    if a.rejected:
        storage.write_text(a.rejected, to_jsonl(rejected))
    cov = report.get("coverage")
    if cov and (cov["missing"] or cov["repeated"] or cov["unknown"]):
        print("COVERAGE CHECK FAILED: every pool id must appear in exactly one shard", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
