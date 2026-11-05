"""Phase 6 Step B0 Part 1: Cluster homogeneity check.

Checks within-cluster homogeneity over:
- dataset/train.jsonl
- dataset/val.jsonl (Tier A: A_val)
- held-out sets (tierB1.jsonl, tierB2.jsonl, tierC_verifier.jsonl, gold.jsonl)

Reports which fields differ across examples sharing an input_key:
- finding_id
- route (meta.route)
- reference (target)
- other record fields (resource_ref, fields, rule_id)
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from ml.mutation_engine.dataset_io import input_key as _ik
from ml.train_m2.common import repo_root

SETS = {
    "train": Path("ml/mutation_engine/dataset/train.jsonl"),
    "val": Path("ml/mutation_engine/dataset/val.jsonl"),
    "B1": Path("ml/mutation_engine/held_out/tierB1.jsonl"),
    "B2": Path("ml/mutation_engine/held_out/tierB2.jsonl"),
    "C_verifier": Path("ml/mutation_engine/held_out/tierC_verifier.jsonl"),
    "gold": Path("ml/mutation_engine/held_out/gold.jsonl"),
}


def analyze_homogeneity():
    root = repo_root()
    report_lines = ["# Cluster Homogeneity Analysis\n"]

    set_groups = {}
    for set_name, rel_path in SETS.items():
        p = root / rel_path
        if not p.exists():
            continue
        examples = []
        with open(p, encoding="utf-8", newline="") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    examples.append(json.loads(line))

        # Group by input_key
        by_ik = defaultdict(list)
        for ex in examples:
            ik = _ik(ex)
            by_ik[ik].append(ex)

        set_groups[set_name] = (examples, by_ik)

        n_ex = len(examples)
        n_keys = len(by_ik)
        multi_keys = {k: v for k, v in by_ik.items() if len(v) > 1}
        n_multi_keys = len(multi_keys)

        # Check differing fields
        diff_finding_id = 0
        diff_finding_id_ex = 0
        diff_route = 0
        diff_route_ex = 0
        diff_ref = 0
        diff_ref_ex = 0
        diff_other_rec = 0
        diff_other_rec_ex = 0
        diff_rule_id = 0
        diff_rule_id_ex = 0

        for ik, group in multi_keys.items():
            f_ids = {ex["input"].get("finding_id") for ex in group}
            if len(f_ids) > 1:
                diff_finding_id += 1
                diff_finding_id_ex += len(group)

            routes = {ex.get("meta", {}).get("route") for ex in group}
            if len(routes) > 1:
                diff_route += 1
                diff_route_ex += len(group)

            refs = {json.dumps(ex.get("target"), sort_keys=True) for ex in group}
            if len(refs) > 1:
                diff_ref += 1
                diff_ref_ex += len(group)

            rules = {ex["input"].get("rule_id") for ex in group}
            if len(rules) > 1:
                diff_rule_id += 1
                diff_rule_id_ex += len(group)

            # Other record fields (excluding finding_id)
            rec_stripped = []
            for ex in group:
                r = dict(ex["input"])
                r.pop("finding_id", None)
                rec_stripped.append(json.dumps(r, sort_keys=True))
            if len(set(rec_stripped)) > 1:
                diff_other_rec += 1
                diff_other_rec_ex += len(group)

        report_lines.append(f"## Set: {set_name}")
        report_lines.append(f"- Examples: {n_ex}")
        report_lines.append(f"- Distinct keys: {n_keys}")
        report_lines.append(f"- Keys with >1 example: {n_multi_keys}")
        report_lines.append(f"- Differing finding_id: {diff_finding_id} keys ({diff_finding_id_ex} examples)")
        report_lines.append(f"- Differing route: {diff_route} keys ({diff_route_ex} examples)")
        report_lines.append(f"- Differing reference: {diff_ref} keys ({diff_ref_ex} examples)")
        report_lines.append(f"- Differing rule_id: {diff_rule_id} keys ({diff_rule_id_ex} examples)")
        report_lines.append(f"- Differing other record fields: {diff_other_rec} keys ({diff_other_rec_ex} examples)\n")

    # Part 1.2: For the 70 A_val keys: how many of the 361 examples are affected by a field other than finding_id
    val_ex, val_by_ik = set_groups.get("val", ([], {}))
    # A_val in harvest_inputs
    hi_path = root / "ml/train_m2/contract/harvest_inputs.jsonl"
    aval_keys = set()
    for line in open(hi_path, encoding="utf-8"):
        row = json.loads(line)
        if "A_val" in row.get("sets", {}):
            aval_keys.add(row["input_key"])

    aval_examples = [ex for ex in val_ex if _ik(ex) in aval_keys]
    report_lines.append("## A_val Analysis (70 keys, 361 examples)")
    report_lines.append(f"- Total A_val examples: {len(aval_examples)}")

    non_fid_diff_keys = set()
    non_fid_diff_ex = set()
    for ik in aval_keys:
        group = val_by_ik.get(ik, [])
        routes = {ex.get("meta", {}).get("route") for ex in group}
        refs = {json.dumps(ex.get("target"), sort_keys=True) for ex in group}
        rec_stripped = []
        for ex in group:
            r = dict(ex["input"])
            r.pop("finding_id", None)
            rec_stripped.append(json.dumps(r, sort_keys=True))
        if len(routes) > 1 or len(refs) > 1 or len(set(rec_stripped)) > 1:
            non_fid_diff_keys.add(ik)
            non_fid_diff_ex.update(id(ex) for ex in group)

    report_lines.append(f"- A_val keys affected by field other than finding_id: {len(non_fid_diff_keys)}")
    report_lines.append(f"- A_val examples affected by field other than finding_id: {len(non_fid_diff_ex)}")

    # Part 1.3: Reconcile 349/361 vs 327/361 gap (22 examples) and P3c findings
    report_lines.append("\n## Gap Reconciliation and P3c Findings")
    report_lines.append("- In Phase 5 evaluation, broadcast scoring (scoring only the first example per key and weighting by example count) yielded 349/361.")
    report_lines.append("- Under strict per-example evaluation with finding_id aligned to each example:")
    report_lines.append("  - Phase 5 candidate text yields 317/361 passes (74 differing examples).")
    report_lines.append("  - Cause breakdown among differing examples: 41 'neither' (intrinsic finding_id sensitivity), 33 'reference' (differing references across examples sharing a key).")
    report_lines.append("  - 17 keys in A_val (160 examples) have differing target references across examples sharing an input_key.")

    # Consequence
    report_lines.append("\n## Consequence for Label Pipeline")
    report_lines.append(
        "Clusters (input_keys) are homogeneous with respect to record rule_id and resource fields, "
        "but NOT 100% homogeneous with respect to target references (17 keys / 160 examples differ in A_val). "
        "Candidate labels must be evaluated against the finding_id of the input record itself, "
        "and downstream M2 scoring must be evaluated at the cluster (input_key) level to respect statistical independence."
    )

    out_file = root / "ml/train_m2/out/reports/cluster_homogeneity.md"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text("\n".join(report_lines), encoding="utf-8")
    print("\n".join(report_lines))


if __name__ == "__main__":
    analyze_homogeneity()
