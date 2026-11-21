"""Generate stratified 5-fold cross-fit assignment for the 230 Phase 5 train input_keys.

Output: docs/phase6_shaurya/crossfit/folds.json
        docs/phase6_shaurya/crossfit/folds.md
        docs/phase6_shaurya/crossfit/folds.json.provenance.json

Each fold lists:
  input_keys      - the fold-f inputs (Prabhav trains on the other 4 folds)
  per_rule        - counts by rule_id in this fold
  heldout_overlap - keys that also appear in B1/B2/C_verifier/gold (OOF drafts labelled but never used for M2 training/cal)
  in_a_val        - keys that are also in A_val

Deterministic: uses hashlib.sha256, never hash(). Seed 1337.
"""
from __future__ import annotations

import hashlib
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from ml.train_m2.common import (
    load_inputs,
    provenance,
    repo_root,
    write_provenance,
)

LOG = logging.getLogger(__name__)
K = 5
SEED = 1337

HELDOUT_SETS = {"B1", "B2", "C_verifier", "gold"}


def _stable_hash(seed: int, key: str) -> int:
    """Deterministic hash using hashlib, not Python's hash()."""
    return int(hashlib.sha256(f"{seed}:{key}".encode("utf-8")).hexdigest(), 16)


def build_folds(seed: int = SEED) -> dict[str, Any]:
    """Build 5-fold stratified (by rule_id) assignment for the 230 train inputs.

    Returns a dict with keys 0..K-1 each containing:
        input_keys, per_rule, heldout_overlap, in_a_val
    Plus metadata: seed, total_train_inputs, counts_per_fold, rule_id_distribution.
    """
    inputs = load_inputs()

    train_inputs = [r for r in inputs if "train" in r.get("sets", {})]
    LOG.info("Train inputs: %d", len(train_inputs))

    # Build per-cluster metadata
    heldout_keys: set[str] = set()
    aval_keys: set[str] = set()
    rule_by_key: dict[str, str] = {}

    for r in train_inputs:
        ik = r["input_key"]
        sets = r.get("sets", {})
        if any(s in HELDOUT_SETS for s in sets):
            heldout_keys.add(ik)
        if "A_val" in sets:
            aval_keys.add(ik)
        # rule_id from the input_key JSON
        try:
            parsed = json.loads(ik)
            rule_id = parsed.get("rule_id", "unknown")
        except (json.JSONDecodeError, TypeError):
            rule_id = "unknown"
        rule_by_key[ik] = rule_id

    # Group train inputs by rule_id for stratification
    by_rule: dict[str, list[str]] = defaultdict(list)
    for ik in rule_by_key:
        by_rule[rule_by_key[ik]].append(ik)

    # Sort each rule group by stable hash for determinism
    for rule_id in by_rule:
        by_rule[rule_id].sort(key=lambda k: _stable_hash(seed, k))

    # Assign each key to a fold by round-robin within each rule group
    fold_keys: dict[int, list[str]] = {f: [] for f in range(K)}
    for rule_id, keys in sorted(by_rule.items()):
        for idx, k in enumerate(keys):
            fold_keys[idx % K].append(k)

    # Build output structure
    folds_out: dict[str, Any] = {
        "seed": seed,
        "K": K,
        "total_train_inputs": len(train_inputs),
        "folds": {},
    }

    total_check = 0
    for f in range(K):
        keys = sorted(fold_keys[f])
        per_rule: dict[str, int] = defaultdict(int)
        for k in keys:
            per_rule[rule_by_key[k]] += 1

        overlap = [k for k in keys if k in heldout_keys]
        in_av = [k for k in keys if k in aval_keys]
        both = [k for k in keys if k in heldout_keys and k in aval_keys]
        clean = [k for k in keys if k not in heldout_keys and k not in aval_keys]

        folds_out["folds"][str(f)] = {
            "input_keys": keys,
            "per_rule": dict(sorted(per_rule.items())),
            "heldout_overlap": overlap,
            "in_a_val": in_av,
            "overlap_of_those_two": both,
            "clean_unseen": clean,
            "note": (
                "OOF drafts for input_keys in heldout_overlap are labelled "
                "heldout_overlap and are NEVER used to train or calibrate M2; "
                "they are test-side only."
            ),
        }
        total_check += len(keys)

    assert total_check == len(train_inputs), f"fold assignment dropped keys: {total_check} != {len(train_inputs)}"

    # Disjointness check
    seen: set[str] = set()
    for f in range(K):
        for k in folds_out["folds"][str(f)]["input_keys"]:
            assert k not in seen, f"key {k!r} in multiple folds"
            seen.add(k)
    assert seen == {r["input_key"] for r in train_inputs}, "fold assignment incomplete"

    # Per-fold counts summary
    folds_out["counts_per_fold"] = {
        str(f): {
            "total": len(folds_out["folds"][str(f)]["input_keys"]),
            "heldout_overlap": len(folds_out["folds"][str(f)]["heldout_overlap"]),
            "in_a_val": len(folds_out["folds"][str(f)]["in_a_val"]),
            "overlap_of_those_two": len(folds_out["folds"][str(f)]["overlap_of_those_two"]),
            "clean_unseen": len(folds_out["folds"][str(f)]["clean_unseen"]),
        }
        for f in range(K)
    }
    folds_out["rule_id_distribution"] = {
        rule: len(keys) for rule, keys in sorted(by_rule.items())
    }

    return folds_out


def render_markdown(folds_out: dict[str, Any]) -> str:
    """Render a one-page counts-only markdown summary."""
    lines = [
        "# Cross-fit folds (counts only, no content)",
        "",
        f"Seed: {folds_out['seed']}  K: {folds_out['K']}  "
        f"Total train inputs: {folds_out['total_train_inputs']}",
        "",
        "## Per-fold summary",
        "",
        "| Fold | Inputs | Heldout overlap | In A_val | Overlap of those two | Clean unseen clusters |",
        "|---|---|---|---|---|---|",
    ]
    tot_inputs = 0
    tot_heldout = 0
    tot_aval = 0
    tot_both = 0
    tot_clean = 0

    fallback_inputs = 0
    fallback_heldout = 0
    fallback_aval = 0
    fallback_both = 0
    fallback_clean = 0

    for f in range(folds_out["K"]):
        c = folds_out["counts_per_fold"][str(f)]
        inputs_cnt = c["total"]
        heldout_cnt = c["heldout_overlap"]
        aval_cnt = c["in_a_val"]
        both_cnt = c.get("overlap_of_those_two", 0)
        clean_cnt = c.get("clean_unseen", 0)

        tot_inputs += inputs_cnt
        tot_heldout += heldout_cnt
        tot_aval += aval_cnt
        tot_both += both_cnt
        tot_clean += clean_cnt

        if f in (0, 1, 2):
            fallback_inputs += inputs_cnt
            fallback_heldout += heldout_cnt
            fallback_aval += aval_cnt
            fallback_both += both_cnt
            fallback_clean += clean_cnt

        lines.append(
            f"| {f} | {inputs_cnt} | {heldout_cnt} | {aval_cnt} | {both_cnt} | {clean_cnt} |"
        )

    lines.append(
        f"| Total (5 folds) | {tot_inputs} | {tot_heldout} | {tot_aval} | {tot_both} | {tot_clean} |"
    )
    lines.append(
        f"| 3-fold fallback (0, 1, 2) | {fallback_inputs} | {fallback_heldout} | {fallback_aval} | {fallback_both} | {fallback_clean} |"
    )

    lines += [
        "",
        "## Clean unseen cluster totals vs S4 requirement (59 needed)",
        "",
        "- CLEAN unseen clusters = inputs not in any held-out set and not in A_val.",
        "- Existing clean unseen clusters in production: 15.",
        "- Required clean unseen clusters to certify stop rule S4: 59.",
        "",
        "### 5-fold totals:",
        f"- OOF clean unseen clusters: {tot_clean}",
        f"- Plus existing 15: {tot_clean} + 15 = {tot_clean + 15} clean unseen clusters",
        f"- Target comparison: {tot_clean + 15} vs 59 needed (margin: +{tot_clean + 15 - 59})",
        "",
        "### 3-fold fallback totals (folds 0, 1, 2):",
        f"- OOF clean unseen clusters: {fallback_clean}",
        f"- Plus existing 15: {fallback_clean} + 15 = {fallback_clean + 15} clean unseen clusters",
        f"- Target comparison: {fallback_clean + 15} vs 59 needed (margin: +{fallback_clean + 15 - 59})",
        "",
        "## Rule-id distribution across all folds",
        "",
        "| rule_id | total | fold 0 | fold 1 | fold 2 | fold 3 | fold 4 |",
        "|---|---|---|---|---|---|---|",
    ]
    for rule, total in sorted(folds_out["rule_id_distribution"].items()):
        per_fold = [
            str(folds_out["folds"][str(f)]["per_rule"].get(rule, 0))
            for f in range(folds_out["K"])
        ]
        lines.append(f"| {rule} | {total} | {' | '.join(per_fold)} |")

    lines += [
        "",
        "## Heldout-overlap rule",
        "",
        "OOF drafts for inputs in the heldout_overlap list are labelled `heldout_overlap=true`.",
        "They are NEVER used to train or calibrate M2; they are test-side only.",
        "",
        "## OOF drafts that count toward SFT certificate",
        "",
        "Only OOF drafts where `heldout_overlap=false` AND the input is NOT in A_val",
        "contribute to the unseen-clean cluster count for the SFT gate-only certificate.",
        "Per S4: 44 more clean unseen clusters needed beyond the current 15.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    root = repo_root()
    out_dir = root / "docs" / "phase6_shaurya" / "crossfit"
    out_dir.mkdir(parents=True, exist_ok=True)

    folds_out = build_folds(SEED)

    folds_path = out_dir / "folds.json"
    folds_path.write_text(
        json.dumps(folds_out, indent=2, sort_keys=False, ensure_ascii=True),
        encoding="utf-8",
    )
    write_provenance(folds_path, seed=SEED)

    md_path = out_dir / "folds.md"
    md_path.write_text(render_markdown(folds_out), encoding="utf-8")

    LOG.info("Written: %s", folds_path)
    LOG.info("Written: %s", md_path)
    print(render_markdown(folds_out))


if __name__ == "__main__":
    main()
