"""Phase 6 AUC shortcut diagnostic.

Checks single-feature separability between corruptor hard negatives and natural
minimal_correct candidates on the corruptor seed partition.

Features checked: n_ops (number of patch ops) and patch JSON length.

If either AUC exceeds 0.95, prints a warning that corruptor negatives are trivially
separable and M2 should be evaluated on natural negatives only.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

LOG = logging.getLogger(__name__)


def _ops_count(row: dict) -> int:
    """Number of patch ops in a labeled row."""
    return len(row.get("patch_ops", []))


def _patch_json_len(row: dict) -> int:
    """Length of the patch JSON string (proxy for complexity)."""
    ops = row.get("patch_ops", [])
    try:
        return len(json.dumps(ops, ensure_ascii=True))
    except Exception:  # noqa: BLE001
        return 0


def _roc_auc(labels: list[int], scores: list[float]) -> float:
    """Compute AUC-ROC via trapezoidal rule (no sklearn dependency)."""
    n = len(labels)
    if n == 0:
        return 0.5
    # Sort by score descending
    paired = sorted(zip(scores, labels), key=lambda x: -x[0])
    n_pos = sum(labels)
    n_neg = n - n_pos
    if n_pos == 0 or n_neg == 0:
        return 0.5
    tp = 0
    fp = 0
    prev_tp = 0
    prev_fp = 0
    auc = 0.0
    for _, lbl in paired:
        if lbl == 1:
            tp += 1
        else:
            fp += 1
        auc += (tp + prev_tp) / 2 * (fp - prev_fp)
        prev_tp = tp
        prev_fp = fp
    return auc / (n_pos * n_neg)


def compute_shortcut_diagnostics(
    corruptor_rows: list[dict],
    natural_rows: list[dict],
) -> dict[str, float]:
    """Compute per-feature AUC separating corruptor hard negatives from natural minimal_correct.

    Restricted to the corruptor seed partition (train_only=True for corruptor;
    heldout_sets empty AND not in_a_val for natural rows).

    Parameters
    ----------
    corruptor_rows  Rows with train_only=True and corruption_type present.
    natural_rows    All natural labeled rows (filtered internally).

    Returns
    -------
    dict with keys: auc_n_ops, auc_json_len
    """
    # Hard negatives: gate_pass AND oracle_class == 'wrong'
    hard_negs = [
        r for r in corruptor_rows
        if r.get("gate_pass") and r.get("oracle_class") == "wrong"
        and not r.get("heldout_sets")
    ]
    # Natural minimal_correct (usable)
    nat_minimal = [
        r for r in natural_rows
        if r.get("oracle_class") == "minimal_correct"
        and not r.get("heldout_sets")
        and not r.get("in_a_val")
        and not r.get("train_only")
    ]

    if not hard_negs or not nat_minimal:
        LOG.info("Not enough rows for shortcut diagnostic: %d hard_negs, %d nat_minimal",
                 len(hard_negs), len(nat_minimal))
        return {"auc_n_ops": 0.5, "auc_json_len": 0.5}

    # Combine: label 1 = hard_neg, 0 = nat_minimal
    combined = [(r, 1) for r in hard_negs] + [(r, 0) for r in nat_minimal]
    labels = [lbl for _, lbl in combined]
    rows = [r for r, _ in combined]

    scores_n_ops = [float(_ops_count(r)) for r in rows]
    scores_json_len = [float(_patch_json_len(r)) for r in rows]

    auc_n_ops = _roc_auc(labels, scores_n_ops)
    auc_json_len = _roc_auc(labels, scores_json_len)

    # AUC can be < 0.5 if the feature separates in the other direction; flip for reporting
    auc_n_ops = max(auc_n_ops, 1.0 - auc_n_ops)
    auc_json_len = max(auc_json_len, 1.0 - auc_json_len)

    THRESHOLD = 0.95
    print(f"\n=== SHORTCUT DIAGNOSTIC ===")
    print(f"  Hard negatives (corruptor, usable): {len(hard_negs)}")
    print(f"  Natural minimal_correct (usable):   {len(nat_minimal)}")
    print(f"  AUC n_ops    : {auc_n_ops:.4f}")
    print(f"  AUC json_len : {auc_json_len:.4f}")
    if auc_n_ops > THRESHOLD or auc_json_len > THRESHOLD:
        print(
            "  WARNING: corruptor negatives are trivially separable; "
            "evaluate M2 on natural negatives only"
        )
    else:
        print("  OK: no trivial separability detected")

    return {"auc_n_ops": auc_n_ops, "auc_json_len": auc_json_len}


if __name__ == "__main__":
    from ml.train_m2.common import jsonl_iter, repo_root

    root = repo_root()
    labels_dir = root / "ml" / "train_m2" / "out" / "labels"
    all_corruptor = []
    all_natural = []
    for gen in ("zeroshot", "sft", "rft"):
        p = labels_dir / f"{gen}.jsonl"
        if not p.exists():
            continue
        for row in jsonl_iter(p):
            if row.get("train_only"):
                all_corruptor.append(row)
            else:
                all_natural.append(row)
    compute_shortcut_diagnostics(all_corruptor, all_natural)


