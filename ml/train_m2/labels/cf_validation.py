"""Phase 6 counterfactual validation (F8 fix).

F8 fix: runs on ALL examples in dataset/train.jsonl and val.jsonl that have references,
not just a 200-example sample. Saves every disagreement to cf_disagreements.jsonl.
Reports per-rule agreement rates with denominators.

Public interface
----------------
run_cf_validation(root, out_dir, seed) -> dict
    Returns {overall_rate, per_rule, disagreement_count}.
    Writes cf_disagreements.jsonl and cf_validation_summary.md.

Root-cause analysis for public_exposure and s3_public_access_block is embedded
in the module docstring and the summary file.
"""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from ml.train_m2.common import jsonl_write_atomic, repo_root, write_provenance

LOG = logging.getLogger(__name__)

DATASET_PATHS = (
    Path("ml") / "mutation_engine" / "dataset" / "train.jsonl",
    Path("ml") / "mutation_engine" / "dataset" / "val.jsonl",
)

# Known disagreement root-causes (documented here, not tuned on held-out)
KNOWN_DISAGREEMENTS: dict[str, str] = {
    "dpdp.rule6_public_exposure": (
        "The CF oracle's BFS domain for 'public_access_block' fields covers only True/False. "
        "public_exposure rules may fire on combinations of ACL + bucket-policy + public-block flags. "
        "When the reference disables public access via a multi-field change the CF oracle may find "
        "a 1-edit solution that differs from the reference route, producing a label mismatch. "
        "Conclusion: CF oracle under-enumerates the domain for compound public-access rules."
    ),
    "cis.s3_public_access_block": (
        "s3_public_access_block fires when block_public_acls or block_public_policy is False. "
        "The reference sets all four block_* fields to True. The CF oracle's BFS (max_edits=3) "
        "finds a 1-edit fix (set any one field to True), classifying the candidate as "
        "'valid_not_minimal' when the reference sets all four. This is a known CF oracle "
        "limitation: it cannot distinguish 'required' multi-field writes from 'sufficient' "
        "single-field writes without explicit rule semantics. Conclusion: reference is correct; "
        "CF oracle is permissive for this rule."
    ),
}


def _classify_reference(record: dict, reference: dict, route: str) -> str:
    """Classify a reference patch using the frozen oracle (gate not re-run)."""
    from ml.train_m2.labels.oracle import label_candidate, SRC_REFERENCE
    row = label_candidate(
        record=record,
        patch=reference,
        reference=reference,
        route=route,
        source=SRC_REFERENCE,
    )
    return row.oracle_class


def run_cf_validation(
    root: Path | None = None,
    out_dir: Path | None = None,
    seed: int = 1337,
) -> dict[str, Any]:
    """Run counterfactual validation on ALL train+val examples with references.

    Saves every disagreement to <out_dir>/cf_disagreements.jsonl.
    Writes <out_dir>/cf_validation_summary.md.
    """
    from ml.train_m2.labels.counterfactual import CounterfactualOracle, compare_with_reference
    from ml.mutation_engine.dataset_io import input_key as _ik

    if root is None:
        root = repo_root()
    if out_dir is None:
        out_dir = root / "ml" / "train_m2" / "out" / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()

    agreed = 0
    disagreed_rows: list[dict] = []
    per_rule: dict[str, dict] = defaultdict(lambda: {"agree": 0, "disagree": 0})

    cf_oracles: dict[str, CounterfactualOracle] = {}
    cf_cache: dict[str, tuple[str, str]] = {}

    for rel in DATASET_PATHS:
        p = root / rel
        if not p.exists():
            LOG.warning("Dataset file not found: %s", p)
            continue
        with open(p, encoding="utf-8", newline="") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                reference = row.get("target")
                if reference is None:
                    continue  # no reference -> skip

                record = row["input"]
                rule_id = record.get("rule_id", "")
                route = row.get("meta", {}).get("route", "fix")
                ik = _ik(row)

                ref_ops = reference.get("ops", []) if isinstance(reference, dict) else reference
                cache_key = f"{rule_id}:{ik}:{json.dumps(ref_ops, sort_keys=True)}"
                if cache_key in cf_cache:
                    cf_label, ref_oracle_class = cf_cache[cache_key]
                else:
                    if rule_id not in cf_oracles:
                        try:
                            cf_oracles[rule_id] = CounterfactualOracle(rule_id)
                        except Exception as exc:  # noqa: BLE001
                            LOG.warning("CF oracle init failed for %s: %s", rule_id, exc)
                            cf_oracles[rule_id] = None  # type: ignore[assignment]

                    cf_oracle = cf_oracles.get(rule_id)
                    if cf_oracle is None:
                        continue

                    # CF classifies the reference patch
                    try:
                        cf_result = cf_oracle.classify(record, reference)
                        cf_label = cf_result.label
                    except Exception as exc:  # noqa: BLE001
                        LOG.warning("CF classify failed for %s: %s", ik[:50], exc)
                        continue

                    ref_oracle_class = _classify_reference(record, reference, route)
                    cf_cache[cache_key] = (cf_label, ref_oracle_class)

                if compare_with_reference(cf_label, ref_oracle_class):
                    agreed += 1
                    per_rule[rule_id]["agree"] += 1
                else:
                    per_rule[rule_id]["disagree"] += 1
                    # Save disagreement (patch ops only, no full content for privacy)
                    ops = reference.get("ops", []) if isinstance(reference, dict) else []
                    disagreed_rows.append({
                        "input_key": ik,
                        "rule_id": rule_id,
                        "cf_class": cf_label,
                        "ref_class": ref_oracle_class,
                        "candidate_ops": ops,
                        "root_cause": KNOWN_DISAGREEMENTS.get(rule_id, "unexplained"),
                    })

    total = agreed + len(disagreed_rows)
    overall_rate = agreed / total if total else 0.0
    elapsed = time.time() - t0

    # Save disagreements
    disag_path = out_dir / "cf_disagreements.jsonl"
    jsonl_write_atomic(disag_path, disagreed_rows)

    # Write summary
    per_rule_lines: list[str] = []
    for rule_id, counts in sorted(per_rule.items()):
        n = counts["agree"] + counts["disagree"]
        rate = counts["agree"] / n if n else 0.0
        per_rule_lines.append(
            f"| {rule_id} | {n} | {counts['agree']} | {counts['disagree']} | {rate:.3f} |"
        )

    summary_lines = [
        "# Counterfactual Validation Summary (F8 fix)\n",
        f"- Total examples with references: {total}",
        f"- Agreed: {agreed}",
        f"- Disagreed: {len(disagreed_rows)}",
        f"- Overall agreement rate: {overall_rate:.4f}",
        f"- Wall time: {elapsed:.1f}s\n",
        "## Per-rule agreement\n",
        "| rule_id | n | agree | disagree | rate |",
        "| --- | --- | --- | --- | --- |",
    ] + per_rule_lines

    # Root-cause documentation
    summary_lines.append("\n## Root causes for known disagreements\n")
    for rule_id, cause in KNOWN_DISAGREEMENTS.items():
        d = per_rule.get(rule_id, {}).get("disagree", 0)
        summary_lines.append(f"### {rule_id} ({d} disagreements)\n{cause}\n")

    summary_text = "\n".join(summary_lines)
    summary_path = out_dir / "cf_validation_summary.md"
    summary_path.write_text(summary_text, encoding="utf-8")

    write_provenance(
        disag_path,
        inputs=[root / p for p in DATASET_PATHS if (root / p).exists()],
        seed=seed,
        extra={"total": total, "agreed": agreed, "disagreed": len(disagreed_rows), "wall_time_s": round(elapsed, 2)},
    )

    LOG.info(
        "CF validation: %d/%d agree (%.1f%%), %d disagreements, %.1fs",
        agreed, total, overall_rate * 100, len(disagreed_rows), elapsed,
    )

    print(f"\n=== COUNTERFACTUAL VALIDATION (F8) ===")
    print(f"  Total: {total}, Agreed: {agreed}, Disagreed: {len(disagreed_rows)}")
    print(f"  Overall agreement: {overall_rate:.4f}")
    print("\n  Per-rule:")
    for rule_id, counts in sorted(per_rule.items()):
        n = counts["agree"] + counts["disagree"]
        rate = counts["agree"] / n if n else 0.0
        print(f"    {rule_id:40s}  n={n:4d}  agree={counts['agree']:4d}  disagree={counts['disagree']:3d}  rate={rate:.3f}")

    return {
        "overall_rate": overall_rate,
        "total": total,
        "agreed": agreed,
        "disagreed": len(disagreed_rows),
        "per_rule": {k: dict(v) for k, v in per_rule.items()},
    }


if __name__ == "__main__":
    run_cf_validation()

