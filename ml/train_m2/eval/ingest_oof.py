"""Ingest OOF (out-of-fold) SFT harvest rows and report unseen-clean cluster counts (stub).

This module reads sft_oof harvest rows, verifies fold disjointness against folds.json,
labels them via the existing P3 pipeline's scoring path, and writes a report of
unseen-clean cluster counts for SFT.

RULES:
  - Does NOT train or score M2.
  - Does NOT open any held-out test set.
  - Only reads harvest rows from ml/train_m2/harvest_out/sft_oof/.
  - Labelling uses the same oracle pipeline as P3 (harvest_checks / gate / scoring) but on OOF rows only.
  - Statistical unit is the CLUSTER (input_key).

Definitions:
  unseen   = the input was in the fold's excluded set (i.e. the adapter never saw it during training)
  clean    = not in any held-out set (B1, B2, C_verifier, gold) AND not in A_val
  unseen-clean = both unseen AND clean
"""
from __future__ import annotations

import json
import logging
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from ml.train_m2.common import (
    jsonl_iter,
    jsonl_write_atomic,
    load_inputs,
    provenance,
    repo_root,
    write_provenance,
)

LOG = logging.getLogger(__name__)

HELDOUT_SETS = {"B1", "B2", "C_verifier", "gold"}


def _load_folds(folds_path: Path) -> dict[str, Any]:
    """Load folds.json and return the parsed object."""
    with open(folds_path, encoding="utf-8") as fh:
        return json.load(fh)


def _build_fold_membership(folds: dict[str, Any]) -> dict[str, int]:
    """Return {input_key: fold_index} for all 230 train inputs."""
    membership: dict[str, int] = {}
    for f_str, fold_data in folds["folds"].items():
        f = int(f_str)
        for ik in fold_data["input_keys"]:
            assert ik not in membership, f"input_key {ik!r} in multiple folds"
            membership[ik] = f
    return membership


def _build_key_flags(inputs: list[dict[str, Any]]) -> dict[str, dict[str, bool]]:
    """Return {input_key: {in_heldout, in_a_val, in_train}} for all harvest inputs."""
    flags: dict[str, dict[str, bool]] = {}
    for r in inputs:
        ik = r["input_key"]
        sets = r.get("sets", {})
        flags[ik] = {
            "in_heldout": any(s in HELDOUT_SETS for s in sets),
            "in_a_val": "A_val" in sets,
            "in_train": "train" in sets,
        }
    return flags


def _extract_fold(row: dict[str, Any]) -> int | None:
    """Extract fold index from explicit row field crossfit_fold or infer from model name."""
    cf = row.get("crossfit_fold")
    if cf is not None:
        try:
            return int(cf)
        except (ValueError, TypeError):
            pass
    model = row.get("model")
    if model:
        m = re.search(r"fold_?([0-4])", str(model))
        if m:
            return int(m.group(1))
    return None


def assert_fold_disjointness(rows: list[dict[str, Any]], fold_membership: dict[str, int]) -> None:
    """Assert that each row's input_key was assigned to fold crossfit_fold (not another).

    Also asserts no input_key appears in more than one fold's rows.

    Raises AssertionError on violation.
    """
    seen_folds: dict[str, set[int]] = defaultdict(set)
    for row in rows:
        ik = row.get("input_key")
        cf = _extract_fold(row)
        if ik is None or cf is None:
            continue
        expected = fold_membership.get(ik)
        if expected is not None and expected != cf:
            raise AssertionError(
                f"input_key {ik!r}: crossfit_fold={cf} but assigned to fold {expected}"
            )
        seen_folds[ik].add(cf)

    for ik, folds_seen in seen_folds.items():
        if len(folds_seen) > 1:
            raise AssertionError(
                f"input_key {ik!r} appears in multiple crossfit_fold values: {folds_seen}"
            )


def compute_unseen_clean_counts(
    rows: list[dict[str, Any]],
    fold_membership: dict[str, int],
    key_flags: dict[str, dict[str, bool]],
) -> dict[str, Any]:
    """Compute per-cluster unseen-clean counts for SFT OOF rows.

    For each input_key:
      - unseen: the input was in the fold that this adapter excluded
      - clean: not in any held-out set AND not in A_val

    Returns a summary dict with counts and per-cluster details.
    """
    # Group rows by input_key
    by_ik: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        ik = row.get("input_key")
        if ik:
            by_ik[ik].append(row)

    unseen_clean_clusters: list[str] = []
    unseen_heldout_clusters: list[str] = []
    unseen_aval_clusters: list[str] = []
    seen_clusters: list[str] = []
    unknown_clusters: list[str] = []

    for ik, cluster_rows in by_ik.items():
        flags = key_flags.get(ik, {})
        in_heldout = flags.get("in_heldout", False)
        in_a_val = flags.get("in_a_val", False)

        # Determine fold assigned for this input_key
        assigned_fold = fold_membership.get(ik)

        # Determine the crossfit_fold from rows (should be consistent)
        cf_values = {_extract_fold(r) for r in cluster_rows}
        cf_values.discard(None)
        if not cf_values:
            unknown_clusters.append(ik)
            continue

        actual_fold = int(list(cf_values)[0])

        # unseen = the adapter for this fold excluded this input
        unseen = assigned_fold == actual_fold

        if unseen:
            if in_heldout:
                unseen_heldout_clusters.append(ik)
            elif in_a_val:
                unseen_aval_clusters.append(ik)
            else:
                unseen_clean_clusters.append(ik)
        else:
            seen_clusters.append(ik)

    return {
        "total_clusters": len(by_ik),
        "unseen_clean_count": len(unseen_clean_clusters),
        "unseen_heldout_count": len(unseen_heldout_clusters),
        "unseen_aval_count": len(unseen_aval_clusters),
        "seen_count": len(seen_clusters),
        "unknown_count": len(unknown_clusters),
        "unseen_clean_clusters": sorted(unseen_clean_clusters),
        "unseen_heldout_clusters": sorted(unseen_heldout_clusters),
        "note": (
            "unseen_clean clusters count toward the SFT gate-only certificate. "
            "unseen_heldout clusters are labelled heldout_overlap and are NEVER used to "
            "train or calibrate M2."
        ),
    }


def render_report(counts: dict[str, Any], current_unseen: int = 15, needed: int = 44) -> str:
    """Render a markdown summary of OOF unseen-clean counts."""
    new_unseen = counts["unseen_clean_count"]
    total_unseen = current_unseen + new_unseen
    still_needed = max(0, needed - new_unseen)

    lines = [
        "# OOF ingest report - SFT unseen-clean cluster counts",
        "",
        f"- OOF rows ingested: total_clusters={counts['total_clusters']}",
        f"- Unseen-clean clusters (count toward certificate): **{new_unseen}**",
        f"- Unseen-heldout (labelled, test-side only): {counts['unseen_heldout_count']}",
        f"- Unseen-A_val: {counts['unseen_aval_count']}",
        f"- Seen by adapter (not OOF): {counts['seen_count']}",
        f"- Unknown fold assignment: {counts['unknown_count']}",
        "",
        "## Certificate status (SFT gate-only)",
        "",
        f"- Pre-OOF unseen-clean clusters: {current_unseen}",
        f"- OOF new unseen-clean clusters: {new_unseen}",
        f"- Total unseen-clean: {total_unseen}",
        f"- Needed for certificate (rule_of_n(0.05, 0.05) = 59): 59",
        f"- Still needed after OOF: {still_needed}",
        "",
        "S4 status: " + (
            "**CLOSED** - 59+ clean unseen clusters available." if total_unseen >= 59
            else f"**OPEN** - {still_needed} more clean unseen clusters needed."
        ),
    ]
    return "\n".join(lines) + "\n"


def ingest_oof(
    harvest_root: Path,
    folds_path: Path,
    out_dir: Path,
    current_unseen: int = 15,
    needed: int = 44,
) -> dict[str, Any]:
    """Read OOF harvest rows, verify disjointness, compute unseen-clean counts, write report.

    Args:
        harvest_root: Path to ml/train_m2/harvest_out/sft_oof/ (or any dir with part-*.jsonl)
        folds_path: Path to docs/phase6_shaurya/crossfit/folds.json
        out_dir: Output directory for the report
        current_unseen: Current pre-OOF unseen-clean cluster count (default: 15 from P6d)
        needed: Additional unseen-clean clusters needed (default: 44 from EXPERIMENT_PLAN_M2.md S4)

    Returns:
        Summary dict with counts.
    """
    if not folds_path.exists():
        raise FileNotFoundError(f"folds.json not found: {folds_path}")

    folds = _load_folds(folds_path)
    fold_membership = _build_fold_membership(folds)
    inputs = load_inputs()
    key_flags = _build_key_flags(inputs)

    # Read all OOF rows
    rows: list[dict[str, Any]] = []
    if harvest_root.exists():
        for part in sorted(harvest_root.rglob("part-*.jsonl")):
            for row in jsonl_iter(part):
                rows.append(row)
    else:
        LOG.warning("harvest_root does not exist yet: %s (stub mode)", harvest_root)

    LOG.info("Read %d OOF rows from %s", len(rows), harvest_root)

    # Verify fold disjointness
    if rows:
        assert_fold_disjointness(rows, fold_membership)
        LOG.info("Fold disjointness check passed.")

    # Compute counts
    counts = compute_unseen_clean_counts(rows, fold_membership, key_flags)

    # Write report
    out_dir.mkdir(parents=True, exist_ok=True)
    report_md = out_dir / "oof_unseen_clean.md"
    report_json = out_dir / "oof_unseen_clean.json"

    report_md.write_text(render_report(counts, current_unseen, needed), encoding="utf-8")
    jsonl_write_atomic(report_json, [counts])
    write_provenance(report_json, seed=1337)

    LOG.info("Report written: %s", report_md)
    return counts


def main() -> None:
    import argparse

    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    p = argparse.ArgumentParser(description="Ingest OOF SFT harvest rows")
    p.add_argument("--harvest-root", default="ml/train_m2/harvest_out/sft_oof",
                   help="Root dir of sft_oof harvest (default: ml/train_m2/harvest_out/sft_oof)")
    p.add_argument("--folds", default="docs/phase6_shaurya/crossfit/folds.json",
                   help="Path to folds.json")
    p.add_argument("--out-dir", default="ml/train_m2/out/reports",
                   help="Output directory for the report")
    p.add_argument("--current-unseen", type=int, default=15,
                   help="Current pre-OOF unseen-clean cluster count")
    p.add_argument("--needed", type=int, default=44,
                   help="Additional unseen-clean clusters needed")
    args = p.parse_args()

    root = repo_root()
    counts = ingest_oof(
        harvest_root=root / args.harvest_root,
        folds_path=root / args.folds,
        out_dir=root / args.out_dir,
        current_unseen=args.current_unseen,
        needed=args.needed,
    )
    print(render_report(counts, args.current_unseen, args.needed))


if __name__ == "__main__":
    main()
