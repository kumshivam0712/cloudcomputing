"""Write / check DIR/model.sha256 (sha256sum format) for every model file in DIR.

    python scripts/model_checksum.py DIR            write DIR/model.sha256
    python scripts/model_checksum.py --check DIR    verify the files against it
"""
import hashlib
import sys
from pathlib import Path

NAME = "model.sha256"


def _digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_checksums(model_dir):
    model_dir = Path(model_dir)
    files = sorted(p for p in model_dir.iterdir() if p.is_file() and p.name != NAME)
    # model.safetensors first: it is "the" model file; the rest are config + tokenizer
    files.sort(key=lambda p: (p.name != "model.safetensors", p.name))
    text = "".join(f"{_digest(p)}  {p.name}\n" for p in files)
    (model_dir / NAME).write_text(text, encoding="utf-8")
    return text


def check_checksums(model_dir):
    model_dir = Path(model_dir)
    bad = []
    for line in (model_dir / NAME).read_text(encoding="utf-8").splitlines():
        if line.strip():
            digest, name = line.split(maxsplit=1)
            ok = (model_dir / name).exists() and _digest(model_dir / name) == digest
            print(f"{name}: {'OK' if ok else 'FAILED'}")
            bad += [] if ok else [name]
    return not bad


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--check":
        sys.exit(0 if check_checksums(sys.argv[2]) else 1)
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    print(write_checksums(sys.argv[1]), end="")
