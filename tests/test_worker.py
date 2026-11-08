import sys
from pathlib import Path

import pytest

import teacher
import worker

ROOT = Path(__file__).resolve().parent.parent


def test_shards_partition_the_pool_without_gaps_or_repeats():
    records = [{"id": f"C{i:04d}"} for i in range(1, 3001)]
    seen = []
    for k in range(4):
        part = worker.select_shard(records, k, 4)
        assert all(int(r["id"][1:]) - 1 == n for n, r in zip(range(k, 3000, 4), part, strict=False))
        seen += [r["id"] for r in part]
    assert sorted(seen) == [r["id"] for r in records]
    assert len(seen) == len(set(seen))


def test_shard_limit_and_bad_index():
    records = [{"id": str(i)} for i in range(10)]
    assert [r["id"] for r in worker.select_shard(records, 1, 2, limit=6)] == ["1", "3", "5"]
    with pytest.raises(ValueError):
        worker.select_shard(records, 2, 2)


def test_teacher_prompt_file_asks_for_the_four_key_json():
    template = teacher.load_prompt(ROOT / "prompts" / "teacher_prompt.txt")
    for word in ('"intent"', '"date"', '"time"', '"place"', "alarm_set", "recommendation_events", "null"):
        assert word in template
    prompt = teacher.build_prompt(template, "what time is it in rome")
    assert prompt.endswith("Command: what time is it in rome\nJSON:")
    assert teacher.TEACHER_OPTIONS["temperature"] == 0 and teacher.TEACHER_OPTIONS["seed"] == 42



def test_prediction_raw_file_never_overwrites_predictions():
    sys.path.insert(0, str(ROOT / "training"))
    import predict

    assert predict.raw_path_for("results/student_v1_predictions.jsonl").name == "student_v1_raw.jsonl"
    assert predict.raw_path_for("build/eval/predictions.jsonl").name == "predictions.raw.jsonl"
