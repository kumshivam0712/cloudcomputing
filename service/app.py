"""Command-parser inference service (Task 3).

Endpoints (port 8000):
  POST /parse    {"text": "..."} -> 200 + the four-key JSON object, or
                 500 {"error": "invalid_model_output"} when the output fails schema.json.
                 Headers on every /parse answer: X-Model-Version, X-Served-By.
  GET  /healthz  200 while the process is alive.
  GET  /readyz   503 until the model is loaded, then 200.

Configuration (environment):
  MODEL_URI       s3://models/v1/   where the model + tokenizer are stored
  MODEL_VERSION   v1                returned in X-Model-Version
  S3_ENDPOINT     http://seaweedfs-s3.data.svc.cluster.local:8333
  MAX_NEW_TOKENS  48                generation budget
  FAULT_INJECT    1 = replace the model output with "not json" before validation (test hook)
  AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY  from a Kubernetes Secret
  POD_NAME        from the downward API (X-Served-By); falls back to the hostname
"""
import hashlib
import logging
import os
import socket
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from prompting import SchemaValidator

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("parser")

MODEL_URI = os.environ.get("MODEL_URI", "")
MODEL_VERSION = os.environ.get("MODEL_VERSION", "unknown")
S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "")
MAX_NEW_TOKENS = int(os.environ.get("MAX_NEW_TOKENS", "48"))
FAULT_INJECT = os.environ.get("FAULT_INJECT", "0") == "1"
SERVED_BY = os.environ.get("POD_NAME") or socket.gethostname()
CACHE_DIR = Path(os.environ.get("MODEL_CACHE_DIR", "/models"))
SCHEMA_PATH = os.environ.get("SCHEMA_PATH", str(Path(__file__).with_name("schema.json")))

validator = SchemaValidator.from_file(SCHEMA_PATH)
state = {"model": None, "loaded_at": None}
_generate_lock = threading.Lock()  # one generation at a time per Pod (CPU limit is 1 core)


def _headers():
    return {"X-Model-Version": MODEL_VERSION, "X-Served-By": SERVED_BY}


def download_model(model_uri, endpoint, dest_root):
    """Copy every object under model_uri (s3://bucket/prefix/) to a local directory."""
    import boto3
    from botocore.config import Config

    bucket, _, prefix = model_uri[len("s3://"):].partition("/")
    prefix = prefix.rstrip("/") + "/"
    dest = Path(dest_root) / prefix.strip("/").replace("/", "_")
    dest.mkdir(parents=True, exist_ok=True)
    s3 = boto3.client("s3", endpoint_url=endpoint, region_name="us-east-1",
                      config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 5}))
    t0, total, files = time.time(), 0, 0
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            name = obj["Key"][len(prefix):]
            if not name or "/" in name:
                continue
            log.info("downloading s3://%s/%s (%.1f MB)", bucket, obj["Key"], obj["Size"] / 1e6)
            s3.download_file(bucket, obj["Key"], str(dest / name))
            total += obj["Size"]
            files += 1
    if files == 0:
        raise FileNotFoundError(f"no objects under {model_uri}")
    log.info("downloaded %d files (%.1f MB) from %s in %.1fs", files, total / 1e6, model_uri, time.time() - t0)
    _verify(dest)
    return dest


def _verify(model_dir):
    sums = model_dir / "model.sha256"
    if not sums.exists():
        log.warning("no model.sha256 next to the model; skipping checksum verification")
        return
    for line in sums.read_text().splitlines():
        if not line.strip():
            continue
        digest, name = line.split(maxsplit=1)
        name = name.lstrip("*")
        h = hashlib.sha256()
        with open(model_dir / name, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        if h.hexdigest() != digest:
            raise ValueError(f"checksum mismatch for {name}")
    log.info("sha256 verified for every file in model.sha256")


def load_model_forever():
    """Background start-up: download from object storage, then load. Retries until it works;
    /readyz stays 503 meanwhile, /healthz stays 200."""
    from model import ParserModel

    delay = 2
    while state["model"] is None:
        t0 = time.time()
        try:
            local = download_model(MODEL_URI, S3_ENDPOINT, CACHE_DIR)
            state["model"] = ParserModel(local, max_new_tokens=MAX_NEW_TOKENS)
            state["loaded_at"] = time.time()
            log.info("model %s loaded from %s in %.1fs; ready", MODEL_VERSION, MODEL_URI, time.time() - t0)
        except Exception as exc:  # noqa: BLE001 - keep retrying, never crash-loop
            log.error("model load failed: %r; retrying in %ss", exc, delay)
            time.sleep(delay)
            delay = min(delay * 2, 30)


@asynccontextmanager
async def lifespan(_app):
    log.info("starting: MODEL_URI=%s MODEL_VERSION=%s S3_ENDPOINT=%s MAX_NEW_TOKENS=%d FAULT_INJECT=%s pod=%s",
             MODEL_URI, MODEL_VERSION, S3_ENDPOINT, MAX_NEW_TOKENS, FAULT_INJECT, SERVED_BY)
    if os.environ.get("SKIP_MODEL_LOAD") != "1":
        threading.Thread(target=load_model_forever, daemon=True).start()
    yield


app = FastAPI(title="command-parser", lifespan=lifespan)


class ParseRequest(BaseModel):
    text: str


@app.get("/healthz")
async def healthz():
    return {"status": "alive"}


@app.get("/readyz")
async def readyz():
    if state["model"] is None:
        return JSONResponse({"status": "loading"}, status_code=503)
    return {"status": "ready", "model_version": MODEL_VERSION}


@app.post("/parse")
def parse(req: ParseRequest):
    model = state["model"]
    if model is None:
        return JSONResponse({"error": "model_not_ready"}, status_code=503, headers=_headers())
    with _generate_lock:
        raw = model.parse(req.text)
    if FAULT_INJECT:
        raw = "not json"
    obj = validator.validate(raw)
    if obj is None:
        log.warning("invalid model output for %r: %r", req.text, raw)
        return JSONResponse({"error": "invalid_model_output"}, status_code=500, headers=_headers())
    return JSONResponse(obj, headers=_headers())
