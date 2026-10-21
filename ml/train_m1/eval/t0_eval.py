"""
ARGUS Phase 5 - row 1 of the grid: T0 templates only (no model). Counts how many examples T0 answers and how many of those pass the gate.

    python -m ml.train_m1.eval.t0_eval --set A_val
"""

import argparse
import json
import sys

from ml.mutation_engine.dataset_io import read_jsonl
from ml.mutation_engine.qa.gate_stub import gate_many
from ml.train_m1.eval.run_eval import SETS
from ml.train_m1.stats import fmt_rate
from remediate.templates import match


def main(argv=None):
    p = argparse.ArgumentParser(description="T0 coverage and gate pass")
    p.add_argument("--set", default="A_val", choices=sorted(SETS))
    o = p.parse_args(argv)
    rows = read_jsonl(SETS[o.set])
    cases, kept = [], []
    for ex in rows:
        patch = match(ex["input"])
        if patch is not None:
            cases.append((ex["input"], patch))
            kept.append(ex)
    results = gate_many(cases) if cases else []
    ok = sum(1 for r in results if r.passed and r.outcome == "fixed")
    print("set {}: T0 answers {}   gate-passing {}".format(o.set, fmt_rate(len(cases), len(rows)), fmt_rate(ok, len(cases))))
    for ex, r in zip(kept, results):
        if not (r.passed and r.outcome == "fixed"):
            print("  FAIL", ex["id"], ex["rule_id"], r.reasons[:2])
            break
    return 0


if __name__ == "__main__":
    sys.exit(main())
