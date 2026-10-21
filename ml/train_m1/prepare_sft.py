"""
ARGUS Phase 5, Step 14 - write the training files for Colab (ml/train_m1/data/) and run the leakage guard.

    python -m ml.train_m1.prepare_sft

Writes: sft_train.jsonl, sft_val.jsonl, sft_train_ablation.jsonl, overfit50.jsonl, train_sample300.jsonl (examples, for the train/held-out gap),
val_distinct.jsonl (one example per distinct validation input, for checkpoint selection) and heldout_hashes.txt (for the notebook guard).
Each Colab line: {"id","system","user","assistant","full_hash","input_hash"}.
Refuses to write anything if a training example shares a full hash with val/B1/B2 or a base hash with Tier C.
"""

import argparse
import json
import random
import sys
from pathlib import Path

from ml.mutation_engine.dataset_io import input_key, read_jsonl, write_jsonl
from ml.mutation_engine.build_dataset import DATASET_DIR, HELD_OUT_DIR
from ml.train_m1.prompt import SYSTEM_PROMPT, patch_json, user_message

DATA_DIR = Path(__file__).resolve().parent / "data"


def sft_row(ex):
    return {"id": ex["id"], "system": SYSTEM_PROMPT, "user": user_message(ex["input"]), "assistant": patch_json(ex["target"]),
            "full_hash": ex["meta"]["full_hash"], "input_hash": ex["meta"]["input_hash"], "input_key": input_key(ex)}


def held_out_hashes(held_dir):
    full, base = set(), set()
    for name in ("held_out_hashes.txt",):
        p = Path(held_dir) / name
        if p.exists():
            full |= set(p.read_text().split())
    p = Path(held_dir) / "tierC_base_hashes.txt"
    if p.exists():
        base |= set(p.read_text().split())
    return full, base


def guard(train_rows, held_dir):
    full, base = held_out_hashes(held_dir)
    bad = [ex["id"] for ex in train_rows if ex["meta"]["full_hash"] in full]
    base_ids = {"b-" + h[:12] for h in base}
    bad += [ex["id"] for ex in train_rows if ex["meta"].get("base_id") in base_ids]
    return sorted(set(bad))


def main(argv=None):
    p = argparse.ArgumentParser(description="Prepare SFT files")
    p.add_argument("--dataset-dir", default=str(DATASET_DIR))
    p.add_argument("--held-out", default=str(HELD_OUT_DIR))
    p.add_argument("--out", default=str(DATA_DIR))
    o = p.parse_args(argv)
    train = read_jsonl(Path(o.dataset_dir) / "train.jsonl")
    val = read_jsonl(Path(o.dataset_dir) / "val.jsonl")
    abl = read_jsonl(Path(o.dataset_dir) / "train_ablation_no_encryption.jsonl")
    if not train or not val:
        print("Dataset missing. Run build_dataset first.")
        return 2
    bad = guard(train + abl, o.held_out)
    if bad:
        print("LEAKAGE GUARD FAILED for {} training examples (first: {}). Nothing written.".format(len(bad), bad[:5]))
        return 1
    out = Path(o.out)
    write_jsonl(out / "sft_train.jsonl", [sft_row(e) for e in train])
    write_jsonl(out / "sft_val.jsonl", [sft_row(e) for e in val])
    write_jsonl(out / "sft_train_ablation.jsonl", [sft_row(e) for e in abl])
    rng = random.Random(50)
    write_jsonl(out / "overfit50.jsonl", [sft_row(e) for e in rng.sample(train, min(50, len(train)))])
    sample = rng.sample(train, min(300, len(train)))
    write_jsonl(out / "train_sample300.jsonl", sample)
    seen, distinct = set(), []
    for e in val:
        k = input_key(e)
        if k not in seen:
            seen.add(k)
            distinct.append(e)
    write_jsonl(out / "val_distinct.jsonl", [sft_row(e) for e in distinct])
    full, base = held_out_hashes(o.held_out)
    (out / "heldout_hashes.txt").write_text("\n".join(sorted(full)) + "\n", encoding="ascii")
    lens = sorted(len(r["system"]) + len(r["user"]) + len(r["assistant"]) for r in map(sft_row, train))
    print("train {} / val {} / ablation {} / val distinct {}".format(len(train), len(val), len(abl), len(distinct)))
    print("approx tokens (chars/3) p50 {} p99 {} max {}".format(lens[len(lens) // 2] // 3, lens[int(len(lens) * .99)] // 3, lens[-1] // 3))
    print("Guard passed. Upload ml/train_m1/data/* to Google Drive (see guide).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
