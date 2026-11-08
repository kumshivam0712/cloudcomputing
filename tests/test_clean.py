import hashlib
import json

import clean


def rec(i, text, raw):
    return {"id": f"C{i:04d}", "text": text, "teacher_raw": raw}


def obj(intent="alarm_set", date=None, time=None, place=None):
    return json.dumps({"intent": intent, "date": date, "time": time, "place": place})


RECORDS = [
    rec(5, "wake me up at six am tomorrow", obj(date="tomorrow", time="six am")),           # kept
    rec(1, "what is the weather in paris", obj("weather_query", place="paris")),              # kept (id order)
    rec(2, "set an alarm", "```json\n{}\n```"),                                                # (a) invalid json
    rec(3, "set an alarm", json.dumps({"intent": "alarm_set", "date": None})),                 # (b) wrong keys
    rec(4, "set an alarm", json.dumps({"intent": "alarm_set", "date": None, "time": None,
                                       "place": None, "extra": 1})),                           # (b) extra key
    rec(6, "play some music", obj("play_music")),                                             # (c) bad intent
    rec(7, "set an alarm for seven am", obj(time="07:00")),                                    # (d) not in text
    rec(8, "set an alarm for seven am", obj(time=7)),                                          # (d) not a string
    rec(9, "What is the weather in  Paris", obj("weather_query", place="paris")),             # (e) duplicate of C0001
    rec(10, "set an alarm for seven am", obj(time="SEVEN AM")),                                # kept (case-insensitive)
]


def test_rules_and_counts_add_up():
    kept, counts, rejected = clean.clean(RECORDS)
    assert counts == {"input_records": 10, "invalid_json": 1, "wrong_keys": 2, "bad_intent": 1,
                      "bad_slot": 2, "duplicate": 1, "kept": 3}
    assert counts["input_records"] == sum(v for k, v in counts.items() if k != "input_records")
    assert [r["id"] for r in kept] == ["C0001", "C0005", "C0010"]          # id order
    dup = [r for r in rejected if r["reason"] == "duplicate"][0]
    assert dup == {"id": "C0009", "reason": "duplicate", "kept_id": "C0001"}  # smallest id kept


def test_kept_values_are_the_teachers_own():
    kept, _, _ = clean.clean(RECORDS)
    first = kept[0]
    assert (first["intent"], first["place"]) == ("weather_query", "paris")
    assert json.loads(first["teacher_raw"])["place"] == "paris"


def test_output_and_checksum_are_deterministic(tmp_path):
    shards = tmp_path / "teacher"
    shards.mkdir()
    (shards / "shard-0.jsonl").write_text("".join(json.dumps(r) + "\n" for r in RECORDS[::2]))
    (shards / "shard-1.jsonl").write_text("".join(json.dumps(r) + "\n" for r in RECORDS[1::2]))
    digests = []
    for run in ("a", "b"):
        out = tmp_path / run
        assert clean.main(["--shards", str(shards), "--out", str(out)]) == 0
        body = (out / "train.jsonl").read_bytes()
        sha_line = (out / "train.sha256").read_text()
        assert sha_line == f"{hashlib.sha256(body).hexdigest()}  train.jsonl\n"
        digests.append(sha_line)
    assert digests[0] == digests[1]


def test_coverage_detects_gaps_and_repeats():
    pool = [{"id": "C0001"}, {"id": "C0002"}, {"id": "C0003"}]
    cov = clean.coverage([{"id": "C0001"}, {"id": "C0001"}, {"id": "C0003"}], pool)
    assert cov["missing"] == ["C0002"] and cov["repeated"] == ["C0001"]
