"""
ARGUS Phase 5, Step 17 - rejection-sampling filter.

Input: rft_candidates.jsonl written by notebook 02 part A, one line per distinct TRAIN input: {"input_key","contents":[8 replies]}.
Keeps, for every input, the first reply that clears the gate with the right outcome. The hidden checks are NEVER used here.
Output: ml/train_m1/data/rft_train.jsonl (Colab lines; reference answers are added for inputs where no sample passed, so no rule disappears).

    python -m ml.train_m1.rft_filter path\\to\\rft_candidates.jsonl
"""

import sys
from collections import Counter
from pathlib import Path

from ml.mutation_engine.dataset_io import input_key, read_jsonl, write_jsonl
from ml.mutation_engine.build_dataset import DATASET_DIR
from ml.train_m1.eval.score import score_inputs
from ml.train_m1.prepare_sft import DATA_DIR
from ml.train_m1.prompt import SYSTEM_PROMPT, user_message


def main(argv=None):
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print(__doc__)
        return 2
    train = read_jsonl(Path(DATASET_DIR) / "train.jsonl")
    by_key = {}
    for ex in train:
        by_key.setdefault(input_key(ex), []).append(ex)
    cands = read_jsonl(args[0])
    items = [{"record": by_key[c["input_key"]][0]["input"], "route": by_key[c["input_key"]][0]["meta"]["route"],
              "reference": by_key[c["input_key"]][0]["target"], "contents": c["contents"]} for c in cands if c["input_key"] in by_key]
    results = score_inputs(items)
    rows, stats, solved = [], Counter(), set()
    for c, res in zip([c for c in cands if c["input_key"] in by_key], results):
        idx = next((j for j, cand in enumerate(res["candidates"]) if cand["correct"]), None)
        ex0 = by_key[c["input_key"]][0]
        stats["inputs"] += 1
        stats["rule:" + ex0["rule_id"] + (":solved" if idx is not None else ":unsolved")] += 1
        if idx is None:
            continue
        solved.add(c["input_key"])
        for ex in by_key[c["input_key"]]:
            rows.append({"id": ex["id"], "system": SYSTEM_PROMPT, "user": user_message(ex["input"]), "assistant": c["contents"][idx],
                         "full_hash": ex["meta"]["full_hash"], "input_hash": ex["meta"]["input_hash"], "input_key": input_key(ex)})
    from ml.train_m1.prepare_sft import sft_row
    for k, exs in by_key.items():
        if k not in solved:
            rows.extend(sft_row(ex) for ex in exs)
            stats["filled_with_reference"] += len(exs)
    write_jsonl(DATA_DIR / "rft_train.jsonl", rows)
    print("inputs scored {}  solved {}  rows written {}  filled with reference {}".format(stats["inputs"], len(solved), len(rows), stats["filled_with_reference"]))
    for k in sorted(s for s in stats if s.startswith("rule:")):
        print("  {} {}".format(k, stats[k]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
