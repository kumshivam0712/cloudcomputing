"""Teacher-labelling worker (Task 1).

Reads SHARD_INDEX (from 0) and SHARD_COUNT. It takes the commands of commands_pool.jsonl
whose line number n (from 0) satisfies n % SHARD_COUNT == SHARD_INDEX, sends each one to the
teacher (Ollama phi3.5, temperature 0, seed 42) with prompts/teacher_prompt.txt, and writes one
line per command to its own object:
    {"id": "...", "text": "...", "teacher_raw": "<the teacher's exact reply>"}
default output: s3://datasets/teacher/shard-<SHARD_INDEX>.jsonl

The output object is re-uploaded every CHECKPOINT_EVERY records, and a restarted worker resumes
from it, so a Pod restart never loses or repeats work.
Other settings (env): INPUT_URI, OUTPUT_URI, PROMPT_FILE, OLLAMA_URL, TEACHER_MODEL, LIMIT.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import storage  # noqa: E402
import teacher  # noqa: E402


def read_jsonl_text(text):
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def select_shard(records, shard_index, shard_count, limit=0):
    """Records whose 0-based line number leaves remainder shard_index (first `limit` lines only if > 0)."""
    if shard_count < 1 or not 0 <= shard_index < shard_count:
        raise ValueError(f"need 0 <= SHARD_INDEX < SHARD_COUNT, got {shard_index}/{shard_count}")
    return [
        rec
        for n, rec in enumerate(records)
        if n % shard_count == shard_index and (limit <= 0 or n < limit)
    ]


def to_jsonl(rows):
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)


def main():
    shard_index = int(os.environ["SHARD_INDEX"])
    shard_count = int(os.environ["SHARD_COUNT"])
    input_uri = os.environ.get("INPUT_URI", "s3://datasets/commands_pool.jsonl")
    output_uri = os.environ.get("OUTPUT_URI", "s3://datasets/teacher/shard-{index}.jsonl").format(index=shard_index)
    prompt_file = os.environ.get("PROMPT_FILE", "prompts/teacher_prompt.txt")
    ollama_url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    model = os.environ.get("TEACHER_MODEL", teacher.TEACHER_MODEL)
    limit = int(os.environ.get("LIMIT", "0"))
    every = int(os.environ.get("CHECKPOINT_EVERY", "25"))

    template = teacher.load_prompt(prompt_file)
    mine = select_shard(read_jsonl_text(storage.read_text(input_uri)), shard_index, shard_count, limit)
    print(f"shard {shard_index}/{shard_count}: {len(mine)} commands -> {output_uri}", flush=True)

    done = {}
    if storage.exists(output_uri):
        for row in read_jsonl_text(storage.read_text(output_uri)):
            done[row["id"]] = row
        print(f"resuming: {len(done)} records already in {output_uri}", flush=True)

    teacher.wait_until_ready(ollama_url, model)
    t0 = time.time()
    new = 0
    for rec in mine:
        if rec["id"] in done:
            continue
        raw = teacher.generate(ollama_url, teacher.build_prompt(template, rec["text"]), model=model)
        done[rec["id"]] = {"id": rec["id"], "text": rec["text"], "teacher_raw": raw}
        new += 1
        if new % every == 0:
            storage.write_text(output_uri, to_jsonl(done[r["id"]] for r in mine if r["id"] in done))
            rate = (time.time() - t0) / new
            left = len(mine) - len(done)
            print(f"shard {shard_index}: {len(done)}/{len(mine)} done, {rate:.2f} s/command, "
                  f"eta {left * rate / 60:.1f} min", flush=True)

    storage.write_text(output_uri, to_jsonl(done[r["id"]] for r in mine))
    elapsed = time.time() - t0
    meta = {
        "shard_index": shard_index, "shard_count": shard_count, "records": len(mine),
        "labelled_this_run": new, "seconds_this_run": round(elapsed, 1),
        "model": model, "options": teacher.TEACHER_OPTIONS, "prompt_file": prompt_file,
        "pod": os.environ.get("HOSTNAME", ""),
    }
    storage.write_text(output_uri.replace(".jsonl", ".meta.json"), json.dumps(meta, indent=2) + "\n")
    print(f"shard {shard_index} finished: {len(mine)} records ({new} new) in {elapsed:.0f}s", flush=True)


if __name__ == "__main__":
    main()
