"""
ARGUS Phase 5, Step 16 - choose the SFT checkpoint on VALIDATION only.

The Colab notebook writes val_preds_epoch<N>.jsonl (one line per distinct validation input: {"input_key","content"}). This script scores each
file with the stub gate and prints gate pass@1 per epoch. Pick the epoch with the best number; never look at B1/B2/C for this.

    python -m ml.train_m1.score_preds path\\to\\val_preds_epoch1.jsonl path\\to\\val_preds_epoch2.jsonl
"""

import json
import sys
from pathlib import Path

from ml.mutation_engine.dataset_io import input_key, read_jsonl
from ml.mutation_engine.build_dataset import DATASET_DIR
from ml.train_m1.eval.score import score_inputs
from ml.train_m1.stats import fmt_rate


def main(argv=None):
    paths = (argv if argv is not None else sys.argv[1:])
    if not paths:
        print(__doc__)
        return 2
    val = read_jsonl(Path(DATASET_DIR) / "val.jsonl")
    by_key, count = {}, {}
    for ex in val:
        k = input_key(ex)
        by_key.setdefault(k, ex)
        count[k] = count.get(k, 0) + 1
    for path in paths:
        preds = {r["input_key"]: r["content"] for r in read_jsonl(path)}
        keys = [k for k in by_key if k in preds]
        items = [{"record": by_key[k]["input"], "route": by_key[k]["meta"]["route"], "reference": by_key[k]["target"], "contents": [preds[k]]} for k in keys]
        res = score_inputs(items)
        weighted = sum(count[k] for k, r in zip(keys, res) if r["pass_at"][1])
        total = sum(count[k] for k in keys)
        valid = sum(1 for r in res if r["candidates"][0]["status"] == "ok")
        print("{}: gate pass@1 (example-weighted) {}   schema-valid {}/{}".format(Path(path).name, fmt_rate(weighted, total), valid, len(res)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
