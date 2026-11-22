"""Score out-of-fold greedy prediction files against the train set using the Phase 5 scorer.

    python -m ml.train_m1.score_oof fold0_preds.jsonl fold1_preds.jsonl
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Sequence

from ml.mutation_engine.build_dataset import DATASET_DIR
from ml.mutation_engine.dataset_io import input_key, read_jsonl
from ml.train_m1.eval.score import score_inputs
from ml.train_m1.stats import fmt_rate


def score_oof_file(pred_path: Path, train_items: dict[str, dict], train_counts: dict[str, int]) -> dict[str, Any]:
    preds = {r["input_key"]: r["content"] for r in read_jsonl(pred_path) if "input_key" in r and "content" in r}
    matched_keys = [k for k in train_items if k in preds]
    if not matched_keys:
        return {"path": str(pred_path), "total": 0, "pass_at_1": 0.0, "valid": 0, "n_keys": 0, "summary": f"{Path(pred_path).name}: no matching train keys"}
    items = [
        {
            "record": train_items[k]["input"],
            "route": train_items[k]["meta"]["route"],
            "reference": train_items[k]["target"],
            "contents": [preds[k]],
        }
        for k in matched_keys
    ]
    res = score_inputs(items)
    weighted = sum(train_counts[k] for k, r in zip(matched_keys, res) if r["pass_at"][1])
    total = sum(train_counts[k] for k in matched_keys)
    unweighted = sum(1 for r in res if r["pass_at"][1])
    valid = sum(1 for r in res if r["candidates"][0]["status"] == "ok")
    pass_at_1 = weighted / total if total > 0 else 0.0
    return {
        "path": str(pred_path),
        "keys_matched": len(matched_keys),
        "total_examples": total,
        "weighted_pass": weighted,
        "pass_at_1": pass_at_1,
        "unweighted_pass": unweighted,
        "valid_schema": valid,
        "summary": f"{Path(pred_path).name}: gate pass@1 {fmt_rate(weighted, total)} ({unweighted}/{len(matched_keys)} distinct keys) schema-valid {valid}/{len(matched_keys)}",
    }


def main(argv: Sequence[str] | None = None) -> int:
    paths = [Path(p) for p in (argv if argv is not None else sys.argv[1:])]
    if not paths:
        print(__doc__)
        return 2
    train_dataset = read_jsonl(Path(DATASET_DIR) / "train.jsonl")
    train_items: dict[str, dict] = {}
    train_counts: dict[str, int] = {}
    for ex in train_dataset:
        k = input_key(ex)
        train_items.setdefault(k, ex)
        train_counts[k] = train_counts.get(k, 0) + 1

    for p in paths:
        if not p.is_file():
            print(f"File not found: {p}")
            continue
        res = score_oof_file(p, train_items, train_counts)
        print(res["summary"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
