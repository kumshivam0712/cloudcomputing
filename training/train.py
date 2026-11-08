"""Fine-tune Pythia-70M on the teacher's replies (sequence-level distillation), CPU only.

    python training/train.py --config training/config.yaml [--subset 50]

Every setting comes from the YAML file. Each training example is
    Command: <the command>\nJSON: <the teacher's JSON reply><|endoftext|>
and the loss is computed on the reply tokens only. Writes the model + tokenizer +
version.json + model.sha256 to output_dir, and one training-loss row per epoch to loss_csv.
"""
import argparse
import csv
import hashlib
import json
import math
import os
import platform
import random
import sys
import time
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

import numpy as np
import torch
import yaml
from transformers import AutoModelForCausalLM, AutoTokenizer, get_linear_schedule_with_warmup

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "service"))
from prompting import format_prompt, format_target  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))
from model_checksum import write_checksums  # noqa: E402

REQUIRED = ("seed", "learning_rate", "batch_size", "epochs", "max_seq_length", "libraries")


def set_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    torch.use_deterministic_algorithms(True, warn_only=True)


def check_libraries(wanted):
    found = {"python": platform.python_version()}
    for name in wanted:
        if name != "python":
            found[name] = metadata.version(name).split("+")[0]
    for name, version in wanted.items():
        if not found[name].startswith(str(version)):
            print(f"WARNING: {name} {found[name]} installed, config.yaml pins {version}", flush=True)
    return found


def load_records(path, limit):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
                if len(rows) == limit:
                    break
    return rows


def encode(tokenizer, rec, max_len):
    prompt = tokenizer(format_prompt(rec["text"]))["input_ids"]
    target = tokenizer(format_target(rec))["input_ids"] + [tokenizer.eos_token_id]
    ids = (prompt + target)[:max_len]
    labels = ([-100] * len(prompt) + target)[:max_len]
    return ids, labels


def collate(batch, pad_id):
    width = max(len(ids) for ids, _ in batch)
    input_ids = torch.full((len(batch), width), pad_id, dtype=torch.long)
    labels = torch.full((len(batch), width), -100, dtype=torch.long)
    mask = torch.zeros((len(batch), width), dtype=torch.long)
    for i, (ids, lab) in enumerate(batch):
        input_ids[i, : len(ids)] = torch.tensor(ids)
        labels[i, : len(lab)] = torch.tensor(lab)
        mask[i, : len(ids)] = 1
    return input_ids, mask, labels


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="training/config.yaml")
    ap.add_argument("--subset", type=int, default=0, help="train on the first N records only (quick check)")
    a = ap.parse_args()

    cfg = yaml.safe_load(open(a.config, encoding="utf-8"))
    missing = [k for k in REQUIRED if k not in cfg]
    if missing:
        sys.exit(f"{a.config} is missing {missing}")
    libs = check_libraries(cfg["libraries"])
    seed = int(cfg["seed"])
    set_seed(seed)
    if cfg.get("num_threads"):
        torch.set_num_threads(int(cfg["num_threads"]))

    n_records = int(cfg.get("max_train_records", 1500))
    out_dir = Path(cfg["output_dir"])
    loss_csv = Path(cfg["loss_csv"])
    if a.subset:
        n_records = min(n_records, a.subset)
        out_dir = out_dir.with_name(out_dir.name + f"-subset{a.subset}")
        loss_csv = out_dir.parent / f"loss-subset{a.subset}.csv"
    train_file = ROOT / cfg["train_file"] if not os.path.isabs(cfg["train_file"]) else Path(cfg["train_file"])
    records = load_records(train_file, n_records)
    print(f"config {a.config}: {len(records)} records from {train_file}, seed {seed}, "
          f"lr {cfg['learning_rate']}, batch {cfg['batch_size']}, epochs {cfg['epochs']}, "
          f"max_seq_length {cfg['max_seq_length']}, threads {torch.get_num_threads()}", flush=True)

    tokenizer = AutoTokenizer.from_pretrained(cfg["base_model"], revision=cfg.get("base_revision"))
    tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        cfg["base_model"], revision=cfg.get("base_revision"), torch_dtype=torch.float32
    )
    model.config.pad_token_id = tokenizer.eos_token_id
    model.train()

    data = [encode(tokenizer, r, int(cfg["max_seq_length"])) for r in records]
    truncated = sum(1 for r, (ids, _) in zip(records, data, strict=False) if ids[-1] != tokenizer.eos_token_id)
    print(f"{len(data)} examples, {sum(len(i) for i, _ in data)} tokens, {truncated} truncated", flush=True)

    bs, epochs = int(cfg["batch_size"]), int(cfg["epochs"])
    steps_per_epoch = math.ceil(len(data) / bs)
    total = steps_per_epoch * epochs
    decay = [p for n, p in model.named_parameters() if p.ndim >= 2]
    no_decay = [p for n, p in model.named_parameters() if p.ndim < 2]
    optim = torch.optim.AdamW(
        [{"params": decay, "weight_decay": float(cfg.get("weight_decay", 0.0))},
         {"params": no_decay, "weight_decay": 0.0}],
        lr=float(cfg["learning_rate"]),
    )
    sched = get_linear_schedule_with_warmup(optim, int(total * float(cfg.get("warmup_ratio", 0.0))), total)
    gen = torch.Generator().manual_seed(seed)
    clip = float(cfg.get("grad_clip_norm", 0) or 0)

    loss_csv.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    t_start = time.time()
    for epoch in range(1, epochs + 1):
        t0 = time.time()
        order = torch.randperm(len(data), generator=gen).tolist()
        loss_sum, tok_sum = 0.0, 0
        for step in range(steps_per_epoch):
            batch = [data[i] for i in order[step * bs:(step + 1) * bs]]
            input_ids, mask, labels = collate(batch, tokenizer.pad_token_id)
            out = model(input_ids=input_ids, attention_mask=mask, labels=labels)
            out.loss.backward()
            if clip:
                torch.nn.utils.clip_grad_norm_(model.parameters(), clip)
            optim.step()
            sched.step()
            optim.zero_grad(set_to_none=True)
            n_tok = int((labels[:, 1:] != -100).sum())
            loss_sum += out.loss.item() * n_tok
            tok_sum += n_tok
        epoch_loss = loss_sum / tok_sum
        secs = time.time() - t0
        rows.append({"epoch": epoch, "train_loss": round(epoch_loss, 6),
                     "learning_rate_end": f"{sched.get_last_lr()[0]:.3e}", "seconds": round(secs, 1)})
        print(f"epoch {epoch}/{epochs}  train_loss {epoch_loss:.4f}  ({secs:.0f}s)", flush=True)
        with open(loss_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)

    model.eval()
    model.generation_config.pad_token_id = tokenizer.eos_token_id
    model.generation_config.eos_token_id = tokenizer.eos_token_id
    out_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(out_dir, safe_serialization=True)
    tokenizer.save_pretrained(out_dir)
    version = {
        "version": cfg.get("version", "v1") + (f"-subset{a.subset}" if a.subset else ""),
        "base_model": cfg["base_model"],
        "base_revision": cfg.get("base_revision"),
        "method": "sequence-level knowledge distillation (fine-tune on teacher phi3.5 replies)",
        "train_file": cfg["train_file"],
        "train_file_sha256": sha256_file(train_file),
        "records": len(records),
        "config": {k: cfg[k] for k in cfg if k != "libraries"},
        "libraries": libs,
        "final_train_loss": rows[-1]["train_loss"],
        "training_seconds": round(time.time() - t_start, 1),
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    (out_dir / "version.json").write_text(json.dumps(version, indent=2) + "\n", encoding="utf-8")
    write_checksums(out_dir)
    print(f"saved model + tokenizer to {out_dir}; loss per epoch in {loss_csv}", flush=True)


if __name__ == "__main__":
    main()
