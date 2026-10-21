"""
ARGUS Phase 5, Steps 11-13 - the human review sheets (precision, mined pairs, gold sample).

    python -m ml.real_data.review_tools verifier-sheet --n 80        sheet to label real findings (precision of our rules)
    python -m ml.real_data.review_tools precision                    precision per rule from the filled sheet
    python -m ml.real_data.review_tools mined-sheet                  sheet to read every mined pair
    python -m ml.real_data.review_tools finalize-mined               write held_out/tierC_mined.jsonl from the pairs marked y
    python -m ml.real_data.review_tools gold-sheet --n 80            sheet for TWO reviewers (finding real? fix acceptable?)
    python -m ml.real_data.review_tools gold-report                  Cohen's kappa, settled labels -> held_out/gold.jsonl

Sheets are CSV files in ml/real_data/review/ (open them in Excel; keep them as CSV when you save). Labels are the letters y or n.
"""

import argparse
import csv
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

from ml.mutation_engine.dataset_io import read_jsonl, write_jsonl
from ml.real_data.c_common import HELD_OUT_DIR, OUT_DIR, REVIEW_DIR, update_c_hashes
from ml.train_m1.stats import cohen_kappa, fmt_rate

LABELS = ("y", "n")


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, fields, rows):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def clean(value):
    return (value or "").strip().lower()


def stratified_sample(rows, n, seed, key):
    """Round-robin over the groups so every rule appears; deterministic."""
    rng = random.Random(seed)
    groups = defaultdict(list)
    for row in rows:
        groups[key(row)].append(row)
    for g in groups.values():
        rng.shuffle(g)
    order = sorted(groups)
    picked = []
    while len(picked) < n and any(groups[g] for g in order):
        for g in order:
            if groups[g] and len(picked) < n:
                picked.append(groups[g].pop())
    return picked


VERIFIER_FIELDS = ["id", "rule_id", "repo", "permalink", "tf_type", "tf_name", "fields", "reviewer_a_real", "reviewer_b_real", "settled_real", "note"]


def cmd_verifier_sheet(o):
    rows = read_jsonl(Path(o.held_out) / "tierC_verifier.jsonl")
    if not rows:
        print("tierC_verifier.jsonl is empty or missing. Run scan_repos first.")
        return 2
    sample = stratified_sample(rows, o.n, o.seed, lambda r: r["rule_id"])
    out = [{"id": r["id"], "rule_id": r["rule_id"], "repo": r["meta"]["repo"], "permalink": r["meta"]["permalink"], "tf_type": r["meta"]["tf_type"],
            "tf_name": r["meta"]["tf_name"], "fields": json.dumps(r["qa"]["mutated"]["attrs"], sort_keys=True), "reviewer_a_real": "",
            "reviewer_b_real": "", "settled_real": "", "note": ""} for r in sorted(sample, key=lambda r: r["id"])]
    path = Path(o.review_dir) / "verifier_sheet.csv"
    if path.exists() and not o.force:
        print("{} already exists (it may hold your labels). Use --force to overwrite.".format(path))
        return 1
    write_csv(path, VERIFIER_FIELDS, out)
    print("Wrote {} rows to {}. Open each permalink: is the reported violation real? Type y or n in reviewer_a_real.".format(len(out), path))
    return 0


def cmd_precision(o):
    path = Path(o.review_dir) / "verifier_sheet.csv"
    if not path.exists():
        print("Missing {}".format(path))
        return 2
    per, missing = defaultdict(Counter), 0
    for row in read_csv(path):
        label = clean(row.get("settled_real")) or clean(row.get("reviewer_a_real"))
        if label not in LABELS:
            missing += 1
            continue
        per[row["rule_id"]][label] += 1
    lines = ["# Precision of our rules on real code (hand-labelled sample)", "", "| rule | true violations | precision |", "|---|---:|---|"]
    for rule in sorted(per):
        y, n = per[rule]["y"], per[rule]["n"]
        flag = "  <- below 70%: review before citing" if (y + n) and y / (y + n) < 0.7 else ""
        lines.append("| {} | {}/{} | {}{} |".format(rule, y, y + n, fmt_rate(y, y + n), flag))
    total_y = sum(c["y"] for c in per.values())
    total = sum(c["y"] + c["n"] for c in per.values())
    lines += ["", "Overall: {}".format(fmt_rate(total_y, total)), "Rows still unlabelled: {}".format(missing), ""]
    out = Path(o.review_dir) / "precision_report.md"
    out.write_text("\n".join(lines), encoding="ascii", errors="replace")
    print("\n".join(lines))
    return 0


MINED_FIELDS = ["id", "rule_id", "repo", "permalink_before", "permalink_after", "ops", "reviewer_a_keep", "reviewer_b_keep", "settled_keep", "note"]


def cmd_mined_sheet(o):
    rows = read_jsonl(o.candidates)
    if not rows:
        print("No candidates in {}. Run mine_history first.".format(o.candidates))
        return 2
    path = Path(o.review_dir) / "mined_sheet.csv"
    if path.exists() and not o.force:
        print("{} already exists (it may hold your labels). Use --force to overwrite.".format(path))
        return 1
    out = [{"id": r["id"], "rule_id": r["rule_id"], "repo": r["meta"]["repo"], "permalink_before": r["meta"]["permalink_before"],
            "permalink_after": r["meta"]["permalink_after"], "ops": json.dumps(r["target"]["ops"], sort_keys=True), "reviewer_a_keep": "",
            "reviewer_b_keep": "", "settled_keep": "", "note": ""} for r in rows]
    write_csv(path, MINED_FIELDS, out)
    print("Wrote {} rows to {}. For each: open both links; type y in reviewer_a_keep only if the human fix is a reasonable answer.".format(len(out), path))
    return 0


def cmd_finalize_mined(o):
    sheet = read_csv(Path(o.review_dir) / "mined_sheet.csv")
    keep = {r["id"] for r in sheet if (clean(r.get("settled_keep")) or clean(r.get("reviewer_a_keep"))) == "y"}
    undecided = [r["id"] for r in sheet if (clean(r.get("settled_keep")) or clean(r.get("reviewer_a_keep"))) not in LABELS]
    if undecided:
        print("{} rows have no y/n yet (first: {}). Label every row first.".format(len(undecided), undecided[:5]))
        return 1
    rows = [r for r in read_jsonl(o.candidates) if r["id"] in keep]
    write_jsonl(Path(o.held_out) / "tierC_mined.jsonl", rows)
    n = update_c_hashes(o.held_out)
    print("Kept {} of {} mined pairs -> tierC_mined.jsonl ({} base hashes in total).".format(len(rows), len(sheet), n))
    return 0


GOLD_FIELDS = ["id", "source", "rule_id", "repo", "link", "ops", "a_finding_real", "a_fix_ok", "b_finding_real", "b_fix_ok",
               "settled_finding_real", "settled_fix_ok", "note"]


def cmd_gold_sheet(o):
    ver = read_jsonl(Path(o.held_out) / "tierC_verifier.jsonl")
    mined = read_jsonl(Path(o.held_out) / "tierC_mined.jsonl")
    n_mined = min(len(mined), o.n * 2 // 5)
    pick = stratified_sample(mined, n_mined, o.seed, lambda r: r["rule_id"]) + stratified_sample(ver, o.n - n_mined, o.seed, lambda r: r["rule_id"])
    rows = []
    for r in sorted(pick, key=lambda r: r["id"]):
        is_mined = r["tier"] == "C-mined"
        rows.append({"id": r["id"], "source": "mined" if is_mined else "verifier", "rule_id": r["rule_id"], "repo": r["meta"]["repo"],
                     "link": r["meta"]["permalink_after"] if is_mined else r["meta"]["permalink"],
                     "ops": json.dumps(r["target"]["ops"], sort_keys=True) if is_mined else "",
                     "a_finding_real": "", "a_fix_ok": "" if is_mined else "na", "b_finding_real": "", "b_fix_ok": "" if is_mined else "na",
                     "settled_finding_real": "", "settled_fix_ok": "" if is_mined else "na", "note": ""})
    path = Path(o.review_dir) / "gold_sheet.csv"
    if path.exists() and not o.force:
        print("{} already exists (it may hold labels). Use --force to overwrite.".format(path))
        return 1
    write_csv(path, GOLD_FIELDS, rows)
    print("Wrote {} rows to {}. Make TWO copies, one per reviewer; each fills only their own columns, WITHOUT looking at the other.".format(len(rows), path))
    print("Then merge both people's a_/b_ columns into gold_sheet.csv, discuss differences and fill the settled_ columns.")
    return 0


def cmd_gold_report(o):
    sheet = read_csv(Path(o.review_dir) / "gold_sheet.csv")
    problems = []
    for r in sheet:
        for col in ("a_finding_real", "b_finding_real", "settled_finding_real"):
            if clean(r.get(col)) not in LABELS:
                problems.append("{}: {} must be y or n".format(r["id"], col))
        if r["source"] == "mined":
            for col in ("a_fix_ok", "b_fix_ok", "settled_fix_ok"):
                if clean(r.get(col)) not in LABELS:
                    problems.append("{}: {} must be y or n".format(r["id"], col))
    if problems:
        print("The sheet is not complete ({} problems). First ones:".format(len(problems)))
        for t in problems[:10]:
            print("  " + t)
        return 1
    k1, agree1 = cohen_kappa([clean(r["a_finding_real"]) for r in sheet], [clean(r["b_finding_real"]) for r in sheet])
    mined = [r for r in sheet if r["source"] == "mined"]
    k2, agree2 = cohen_kappa([clean(r["a_fix_ok"]) for r in mined], [clean(r["b_fix_ok"]) for r in mined]) if mined else (None, None)

    def show(k):
        return "undefined (one label only)" if k is None else "{:.2f}".format(k)

    lines = ["# Gold sample agreement", "", "Items: {} ({} mined, {} verifier)".format(len(sheet), len(mined), len(sheet) - len(mined)), "",
             "- finding real? kappa {} (raw agreement {})".format(show(k1), "n/a" if agree1 is None else "{:.0%}".format(agree1)),
             "- fix acceptable? (mined only) kappa {} (raw agreement {})".format(show(k2), "n/a" if agree2 is None else "{:.0%}".format(agree2)), ""]
    index = {r["id"]: r for r in read_jsonl(Path(o.held_out) / "tierC_verifier.jsonl") + read_jsonl(Path(o.held_out) / "tierC_mined.jsonl")}
    gold = []
    for r in sheet:
        row = dict(index[r["id"]])
        row["tier"] = "gold"
        row["meta"] = dict(row["meta"], split="gold", source_tier=index[r["id"]]["tier"],
                           finding_real=clean(r["settled_finding_real"]) == "y",
                           fix_ok=None if r["source"] != "mined" else clean(r["settled_fix_ok"]) == "y")
        gold.append(row)
    write_jsonl(Path(o.held_out) / "gold.jsonl", gold)
    lines.append("Settled labels stored in held_out/gold.jsonl ({} items, {} marked as real findings).".format(
        len(gold), sum(1 for g in gold if g["meta"]["finding_real"])))
    out = Path(o.review_dir) / "gold_report.md"
    out.write_text("\n".join(lines) + "\n", encoding="ascii", errors="replace")
    print("\n".join(lines))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description="Human review sheets for Tier C")
    p.add_argument("command", choices=["verifier-sheet", "precision", "mined-sheet", "finalize-mined", "gold-sheet", "gold-report"])
    p.add_argument("--n", type=int, default=80)
    p.add_argument("--seed", type=int, default=11)
    p.add_argument("--force", action="store_true")
    p.add_argument("--held-out", default=str(HELD_OUT_DIR))
    p.add_argument("--review-dir", default=str(REVIEW_DIR))
    p.add_argument("--candidates", default=str(OUT_DIR / "tierC_mined_candidates.jsonl"))
    o = p.parse_args(argv)
    return {"verifier-sheet": cmd_verifier_sheet, "precision": cmd_precision, "mined-sheet": cmd_mined_sheet,
            "finalize-mined": cmd_finalize_mined, "gold-sheet": cmd_gold_sheet, "gold-report": cmd_gold_report}[o.command](o)


if __name__ == "__main__":
    sys.exit(main())
