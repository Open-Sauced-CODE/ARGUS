"""
ARGUS Phase 5, Step 8 - re-run the QA checks on the files on disk, write the readable report, and write the
50-example sheet for the hand inspection.

    python -m ml.mutation_engine.qa.run_all
    python -m ml.mutation_engine.qa.run_all --skip-airlock-recheck      (faster)

Writes ml/mutation_engine/qa/report.md and qa/inspect_50.md. Creates qa/inspection_log.md once (you fill it in by hand).
Exit code 0 = all eight checks passed, 1 = at least one failure, 2 = dataset files missing.
"""

import argparse
import json
import random
import sys
from pathlib import Path

from ml.mutation_engine.dataset_io import read_jsonl
from ml.mutation_engine.qa.checks import CHECK_LABELS, run_checks

ME_DIR = Path(__file__).resolve().parents[1]
FILES = (("train", "dataset/train.jsonl"), ("val", "dataset/val.jsonl"),
         ("B1", "held_out/tierB1.jsonl"), ("B2", "held_out/tierB2.jsonl"))


def load_splits(root=None):
    root = Path(root or ME_DIR)
    return {name: read_jsonl(root / rel) for name, rel in FILES}


def write_report(path, report, splits):
    lines = ["# QA report (Phase 5, Step 8)", "", "Examples checked: {}".format(report["counts"].get("examples", 0)), "",
             "| check | what | failures |", "|---|---|---:|"]
    per = {c: 0 for c in CHECK_LABELS}
    for f in report["failures"]:
        per[f["check"]] += 1
    for c, label in CHECK_LABELS.items():
        lines.append("| {} | {} | {} |".format(c, label, per[c]))
    lines += ["", "RESULT: {}".format("ALL CHECKS PASSED" if not report["failures"] else "FAILURES FOUND"), ""]
    if report["failures"]:
        lines.append("## First 50 failures")
        for f in report["failures"][:50]:
            lines.append("- check {} [{}] {}: {}".format(f["check"], f["split"], f["id"], f["detail"]))
        lines.append("")
    s = report["stats"]
    for name, st in s["splits"].items():
        lines += ["## Split {}".format(name), "- examples: {}, distinct inputs: {}, ambiguous inputs: {}".format(
            st["examples"], st["distinct_inputs"], st["ambiguous_inputs"]),
            "- routes: {}".format(st["by_route"]), "- ops per patch: {}".format(st["ops_per_patch"]),
            "- violations per resource: {}".format(st["violations_per_resource"]),
            "- approx tokens (chars/3) p50 / p99 / max: {}".format(st["approx_tokens_p50_p99_max"]),
            "", "| rule | examples | distinct inputs |", "|---|---:|---:|"]
        for rule, k in st["by_rule"].items():
            lines.append("| {} | {} | {} |".format(rule, k, st["distinct_inputs_by_rule"].get(rule, 0)))
        lines.append("")
    Path(path).write_text("\n".join(lines) + "\n", encoding="ascii", errors="replace")


def write_inspection_sheet(path, splits, seed=2026, n=50):
    rng = random.Random(seed)
    pool = [(name, ex) for name in splits for ex in splits[name]]
    pick = rng.sample(pool, min(n, len(pool)))
    lines = ["# 50 examples for the hand inspection (Step 8)", "",
             "Read each one. Ask: (1) does the fix fix what the input shows? (2) is it the smallest fix? (3) would a careful engineer agree?",
             "Write your verdicts in qa/inspection_log.md.", ""]
    for i, (name, ex) in enumerate(pick, 1):
        lines += ["## {}. {} ({}) rule {}".format(i, ex["id"], name, ex["rule_id"]),
                  "mutators: {}  variants: {}".format(ex["meta"]["mutators"], ex["meta"]["variants"]),
                  "INPUT : " + json.dumps(ex["input"], sort_keys=True),
                  "TARGET: " + json.dumps(ex["target"], sort_keys=True), ""]
    Path(path).write_text("\n".join(lines) + "\n", encoding="ascii", errors="replace")


def main(argv=None):
    p = argparse.ArgumentParser(description="Re-run the Phase 5 QA checks on the dataset files")
    p.add_argument("--root", default=str(ME_DIR))
    p.add_argument("--skip-airlock-recheck", action="store_true")
    o = p.parse_args(argv)
    splits = load_splits(o.root)
    if not splits["train"]:
        print("No dataset found under {}. Run build_dataset first.".format(o.root))
        return 2
    report = run_checks(splits, recheck_airlock=not o.skip_airlock_recheck, log=lambda m: print("  " + m))
    qa = Path(o.root) / "qa"
    qa.mkdir(parents=True, exist_ok=True)
    write_report(qa / "report.md", report, splits)
    write_inspection_sheet(qa / "inspect_50.md", splits)
    log = qa / "inspection_log.md"
    if not log.exists():
        log.write_text("# Hand inspection log\n\nDate:\nReviewer:\n\n| # | example id | verdict (ok / wrong / unclear) | note |\n|---|---|---|---|\n", encoding="ascii")
    for c, label in CHECK_LABELS.items():
        k = sum(1 for f in report["failures"] if f["check"] == c)
        print("check {} {:<55} {}".format(c, label, "PASS" if k == 0 else "FAIL ({})".format(k)))
    for f in report["failures"][:10]:
        print("  {} {}: {}".format(f["check"], f["id"], f["detail"]))
    print("RESULT: {}".format("ALL CHECKS PASSED" if not report["failures"] else "FAILURES FOUND"))
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    sys.exit(main())
