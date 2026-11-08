"""Minimal Ollama client for the teacher model (Python standard library only).

The teacher settings are fixed for the whole project and used by the labelling
workers (Task 1) and by the teacher evaluation on validation.jsonl (Task 2):
    model phi3.5, temperature 0, seed 42.
num_predict only caps the reply length (a correct four-key object needs ~40 tokens);
it does not change the greedy tokens produced before the cap.
"""
import json
import os
import time
import urllib.error
import urllib.request

TEACHER_MODEL = os.environ.get("TEACHER_MODEL", "phi3.5")
TEACHER_OPTIONS = {"temperature": 0, "seed": 42, "num_predict": 128}
PLACEHOLDER = "{command}"


def load_prompt(path):
    with open(path, encoding="utf-8") as f:
        template = f.read()
    if PLACEHOLDER not in template:
        raise ValueError(f"{path} does not contain the placeholder {PLACEHOLDER}")
    return template


def build_prompt(template, command):
    """Insert one command into the prompt template (only the placeholder is replaced)."""
    return template.replace(PLACEHOLDER, command)


def _post_json(url, payload, timeout):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def generate(base_url, prompt, model=TEACHER_MODEL, options=None, timeout=600, retries=5):
    """Return the teacher's reply text exactly as generated (field "response")."""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": "3h",
        "options": dict(TEACHER_OPTIONS if options is None else options),
    }
    url = base_url.rstrip("/") + "/api/generate"
    delay = 2.0
    for attempt in range(1, retries + 1):
        try:
            return _post_json(url, payload, timeout)["response"]
        except (urllib.error.URLError, TimeoutError, ConnectionError, KeyError) as exc:
            if attempt == retries:
                raise
            print(f"teacher call failed ({exc!r}); retry {attempt}/{retries - 1} in {delay:.0f}s", flush=True)
            time.sleep(delay)
            delay *= 2
    raise RuntimeError("unreachable")


def wait_until_ready(base_url, model=TEACHER_MODEL, timeout_s=900):
    """Block until Ollama answers and the model is present."""
    deadline = time.time() + timeout_s
    url = base_url.rstrip("/") + "/api/tags"
    while True:
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                tags = json.loads(resp.read().decode("utf-8"))
            names = {m.get("name", "") for m in tags.get("models", [])}
            if any(n == model or n.startswith(model + ":") for n in names):
                return
            print(f"teacher up, waiting for model {model} (have {sorted(names)})", flush=True)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            print(f"waiting for teacher at {base_url}: {exc!r}", flush=True)
        if time.time() > deadline:
            raise TimeoutError(f"teacher not ready after {timeout_s}s")
        time.sleep(5)
