import json

import pytest
from fastapi.testclient import TestClient

import app as service
from prompting import KEYS, SchemaValidator, extract_output, format_prompt, format_target


class FakeModel:
    def __init__(self, output):
        self.output = output

    def parse(self, text, is_valid=None):
        self.is_valid = is_valid
        return self.output


GOOD = '{"intent": "weather_query", "date": null, "time": null, "place": "london"}'


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(service, "FAULT_INJECT", False)
    monkeypatch.setitem(service.state, "model", None)
    with TestClient(service.app) as c:
        yield c


def test_health_and_readiness(client):
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code == 503          # model not loaded yet
    service.state["model"] = FakeModel(GOOD)
    assert client.get("/readyz").status_code == 200


def test_parse_returns_only_the_object_and_both_headers(client):
    service.state["model"] = FakeModel(GOOD)
    r = client.post("/parse", json={"text": "what is the weather in london"})
    assert r.status_code == 200
    assert r.json() == {"intent": "weather_query", "date": None, "time": None, "place": "london"}
    assert list(r.json()) == list(KEYS)
    assert r.headers["X-Model-Version"] == service.MODEL_VERSION
    assert r.headers["X-Served-By"] == service.SERVED_BY


@pytest.mark.parametrize("bad", ["not json", '{"intent": "alarm_set"}', '{"intent": "dance", "date": null, '
                                 '"time": null, "place": null}', GOOD[:-1]])
def test_invalid_model_output_is_500_never_200(client, bad):
    service.state["model"] = FakeModel(bad)
    r = client.post("/parse", json={"text": "x"})
    assert r.status_code == 500
    assert r.json() == {"error": "invalid_model_output"}


def test_service_passes_the_schema_check_to_the_model_for_the_retry(client):
    fake = FakeModel(GOOD)
    service.state["model"] = fake
    client.post("/parse", json={"text": "x"})
    assert fake.is_valid(GOOD) is True and fake.is_valid("not json") is False


def test_fault_inject(client, monkeypatch):
    service.state["model"] = FakeModel(GOOD)
    monkeypatch.setattr(service, "FAULT_INJECT", True)
    r = client.post("/parse", json={"text": "what is the weather in london"})
    assert r.status_code == 500
    assert r.content == b'{"error":"invalid_model_output"}'
    assert "X-Model-Version" in r.headers


def test_prompt_format_matches_training_example():
    label = {"intent": "alarm_set", "date": "tomorrow", "time": "six am", "place": None}
    assert format_prompt("  Set an  ALARM ") == "Command: set an alarm\nJSON:"
    assert format_target(label) == ' {"intent": "alarm_set", "date": "tomorrow", "time": "six am", "place": null}'
    assert extract_output(' {"a": 1}\nCommand: next') == '{"a": 1}'


def test_schema_validator_against_kit_schema():
    v = SchemaValidator.from_file(service.SCHEMA_PATH)
    assert v.validate(GOOD) == json.loads(GOOD)
    assert v.validate('{"intent": "alarm_set", "date": 5, "time": null, "place": null}') is None
    assert v.validate('{"intent": "alarm_set", "date": null, "time": null, "place": null, "x": 1}') is None
    assert v.validate("[]") is None
