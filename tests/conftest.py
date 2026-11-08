import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for sub in ("worker", "service", "scripts", "tools"):
    sys.path.insert(0, str(ROOT / sub))
os.environ.setdefault("SKIP_MODEL_LOAD", "1")
os.environ.setdefault("SCHEMA_PATH", str(ROOT / "data" / "schema.json"))
