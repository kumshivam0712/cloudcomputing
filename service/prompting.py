"""Prompt format, output extraction and schema validation, shared by training (training/*.py)
and the inference service (service/app.py) so both always use exactly the same format.

Training example (sequence-level distillation):
    Command: <the command>
    JSON: <the teacher's JSON reply><|endoftext|>
"""
import json

KEYS = ("intent", "date", "time", "place")


def normalize_command(text):
    """Commands in the kit are lower-case with single spaces; normalise user input the same way."""
    return " ".join(str(text).lower().split())


def format_prompt(text):
    return f"Command: {normalize_command(text)}\nJSON:"


def format_target(label):
    """The teacher's reply (its four values, in schema key order) as one line, with a leading space."""
    return " " + json.dumps({k: label[k] for k in KEYS}, ensure_ascii=False)


def extract_output(generated):
    """The model's raw answer: the generated text up to the first newline, trimmed."""
    return generated.split("\n", 1)[0].strip()


class SchemaValidator:
    """Checks one model output against data/schema.json ("json_schema": object, exactly the
    required keys, intent from the enum, slots string or null). Standard library only."""

    _TYPES = {"string": str, "null": type(None), "object": dict}

    def __init__(self, schema):
        js = schema["json_schema"]
        self.required = list(js["required"])
        self.properties = js["properties"]
        self.additional = js.get("additionalProperties", True)

    @classmethod
    def from_file(cls, path):
        with open(path, encoding="utf-8") as f:
            return cls(json.load(f))

    def validate(self, raw):
        """Return the parsed object (keys in schema order) or None if raw is not valid."""
        try:
            obj = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(obj, dict):
            return None
        if any(k not in obj for k in self.required):
            return None
        if not self.additional and any(k not in self.properties for k in obj):
            return None
        for key, rule in self.properties.items():
            if key not in obj:
                continue
            value = obj[key]
            if "enum" in rule and value not in rule["enum"]:
                return None
            if "type" in rule:
                types = rule["type"] if isinstance(rule["type"], list) else [rule["type"]]
                if not any(isinstance(value, self._TYPES[t]) for t in types):
                    return None
        return {k: obj[k] for k in self.properties if k in obj}
