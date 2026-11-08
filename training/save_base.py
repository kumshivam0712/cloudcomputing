"""Save the UNTRAINED Pythia-70M (+ tokenizer) in the same layout as a trained model, so it can
be published as the deliberately bad model for the CI quality-gate demonstration (Task 6).

    python training/save_base.py --config training/config.yaml --out build/models/base
"""
import argparse
import json
import sys
from pathlib import Path

import yaml
from transformers import AutoModelForCausalLM, AutoTokenizer

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from model_checksum import write_checksums  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="training/config.yaml")
    ap.add_argument("--out", default="build/models/base")
    a = ap.parse_args()
    cfg = yaml.safe_load(open(a.config, encoding="utf-8"))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    tok = AutoTokenizer.from_pretrained(cfg["base_model"], revision=cfg["base_revision"])
    model = AutoModelForCausalLM.from_pretrained(cfg["base_model"], revision=cfg["base_revision"])
    model.save_pretrained(out, safe_serialization=True)
    tok.save_pretrained(out)
    (out / "version.json").write_text(json.dumps({
        "version": "base",
        "description": "untrained EleutherAI/pythia-70m (no distillation) - deliberately bad model",
        "base_model": cfg["base_model"], "base_revision": cfg["base_revision"],
    }, indent=2) + "\n", encoding="utf-8")
    write_checksums(out)
    print(f"saved untrained base model to {out}")


if __name__ == "__main__":
    main()
