"""Phase 6 human-label tooling for M2 ground truth.

Public interface
----------------
export_for_labeling(candidates, n, stratify_by, out_path, seed) -> Path
    Write a blind CSV (hides model name, gate result, oracle label) for human review.

import_labels(csv_path) -> list[dict]
    Parse an import CSV; validate required columns.

cohen_kappa(a, b, input_keys_a, input_keys_b) -> dict
    Compute Cohen's kappa on overlapping items; 95% cluster-bootstrap CI (cluster = input_key).
    Raises ValueError if fewer than 30 doubly-labeled items.
"""

from __future__ import annotations

import csv
import io
import logging
import math
import statistics
from pathlib import Path
from typing import Any, Sequence

from ml.train_m2.common import set_seed

LOG = logging.getLogger(__name__)

# Columns exported in the blind CSV (NO model, generator, or gate columns)
EXPORT_COLUMNS = [
    "candidate_id",
    "rule_id",
    "resource_type",
    "fields_projected",
    "patch_ops",
]

# Required columns in the import (labeler's return CSV)
IMPORT_COLUMNS = ["candidate_id", "labeler", "correct", "minimal", "would_apply_in_prod", "note"]

MIN_DOUBLY_LABELED = 30
BOOTSTRAP_REPS = 2000
CI_ALPHA = 0.05


def _kappa(a_correct: list[int], b_correct: list[int]) -> float:
    """Cohen's kappa from two binary rating lists (0/1) for the SAME items."""
    n = len(a_correct)
    if n == 0:
        return float("nan")
    po = sum(x == y for x, y in zip(a_correct, b_correct)) / n
    pa = sum(a_correct) / n
    pb = sum(b_correct) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    if pe >= 1.0:
        return 1.0
    return (po - pe) / (1 - pe)


def export_for_labeling(
    candidates: Sequence[dict[str, Any]],
    n: int,
    stratify_by: str | None = None,
    out_path: str | None = None,
    seed: int = 1337,
) -> str:
    """Write a blind CSV for human labeling; return CSV text (and write to out_path if given).

    The CSV hides model name, generator tag, gate result and oracle label (blind).

    Parameters
    ----------
    candidates  LabelRow-like dicts (from build_labels or a scored log); must have keys
                "input_key", "oracle_class", "gate_pass", "generator" (for stratification).
    n           Target number of rows to export.
    stratify_by Column to stratify over ("rule_id", "oracle_class" ...).  None = random.
    out_path    If given, write the CSV to this path.
    seed        RNG seed for deterministic sampling.
    """
    rng = set_seed(seed)

    if stratify_by and stratify_by in (candidates[0] if candidates else {}):
        # Group by stratum and sample proportionally
        from collections import defaultdict
        groups: dict[str, list] = defaultdict(list)
        for c in candidates:
            groups[str(c.get(stratify_by, "unknown"))].append(c)
        quota = max(1, n // len(groups)) if groups else n
        selected: list[dict] = []
        for g in groups.values():
            idxs = rng.choice(len(g), size=min(quota, len(g)), replace=False)
            selected.extend(g[int(i)] for i in idxs)
        # Top up if under quota
        if len(selected) < n:
            remaining = [c for c in candidates if c not in selected]
            extra = min(n - len(selected), len(remaining))
            idxs = rng.choice(len(remaining), size=extra, replace=False)
            selected.extend(remaining[int(i)] for i in idxs)
    else:
        # Simple random sample
        idx = rng.choice(len(candidates), size=min(n, len(candidates)), replace=False)
        selected = [candidates[int(i)] for i in idx]

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=EXPORT_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for i, cand in enumerate(selected):
        record = cand.get("record") or {}
        fields = record.get("fields") or cand.get("fields") or {}
        # Project only rule-declared fields (already stored in 'fields')
        from privacy.airlock.projection import load_declarations

        rule_id = record.get("rule_id") or cand.get("rule_id") or ""
        declared = load_declarations().get(rule_id, frozenset())
        projected = {k: v for k, v in fields.items() if k in declared}
        import json

        row = {
            "candidate_id": cand.get("candidate_id") or f"cand-{i:06d}",
            "rule_id": rule_id,
            "resource_type": fields.get("resource_type", ""),
            "fields_projected": json.dumps(projected, sort_keys=True, ensure_ascii=True),
            "patch_ops": json.dumps(cand.get("patch_ops") or [], ensure_ascii=True),
        }
        writer.writerow(row)

    text = buf.getvalue()
    if out_path is not None:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_text(text, encoding="utf-8", newline="")
    return text


def import_labels(csv_path: str | Path) -> list[dict[str, Any]]:
    """Parse a human-label import CSV; validate required columns."""
    rows: list[dict[str, Any]] = []
    with open(csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        missing = set(IMPORT_COLUMNS) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Import CSV missing required columns: {sorted(missing)}")
        for row in reader:
            rows.append(dict(row))
    return rows


def cohen_kappa(
    a_labels: Sequence[dict[str, Any]],
    b_labels: Sequence[dict[str, Any]],
    seed: int = 1337,
) -> dict[str, Any]:
    """Compute Cohen's kappa on overlapping items; 95% cluster-bootstrap CI.

    Parameters
    ----------
    a_labels, b_labels
        Lists of label dicts; each must have "candidate_id", "correct", and
        optionally "input_key" (used for cluster bootstrap; falls back to candidate_id).
    seed
        RNG seed for the bootstrap.

    Returns
    -------
    dict with keys: kappa, ci_lower, ci_upper, n_items, n_clusters.
    Raises ValueError if fewer than MIN_DOUBLY_LABELED doubly-labeled items.
    """
    # Index by candidate_id
    a_index = {row["candidate_id"]: row for row in a_labels}
    b_index = {row["candidate_id"]: row for row in b_labels}
    common_ids = sorted(set(a_index) & set(b_index))

    if len(common_ids) < MIN_DOUBLY_LABELED:
        raise ValueError(
            f"cohen_kappa requires at least {MIN_DOUBLY_LABELED} doubly-labeled items "
            f"(got {len(common_ids)})"
        )

    # Cluster by input_key (fall back to candidate_id)
    from collections import defaultdict

    clusters: dict[str, list[int]] = defaultdict(list)
    a_vec: list[int] = []
    b_vec: list[int] = []
    for idx, cid in enumerate(common_ids):
        ra, rb = a_index[cid], b_index[cid]
        a_val = 1 if str(ra.get("correct", "")).strip().lower() in ("1", "yes", "true") else 0
        b_val = 1 if str(rb.get("correct", "")).strip().lower() in ("1", "yes", "true") else 0
        a_vec.append(a_val)
        b_vec.append(b_val)
        cluster_key = ra.get("input_key") or rb.get("input_key") or cid
        clusters[cluster_key].append(idx)

    observed_kappa = _kappa(a_vec, b_vec)

    # Cluster bootstrap CI
    rng = set_seed(seed)
    cluster_list = list(clusters.values())
    n_clusters = len(cluster_list)
    boot_kappas: list[float] = []
    for _ in range(BOOTSTRAP_REPS):
        sample_indices = rng.choice(n_clusters, size=n_clusters, replace=True)
        sample_a: list[int] = []
        sample_b: list[int] = []
        for ci in sample_indices:
            for idx in cluster_list[int(ci)]:
                sample_a.append(a_vec[idx])
                sample_b.append(b_vec[idx])
        k = _kappa(sample_a, sample_b)
        if not math.isnan(k):
            boot_kappas.append(k)

    boot_kappas.sort()
    lo_idx = int(math.floor(CI_ALPHA / 2 * len(boot_kappas)))
    hi_idx = int(math.ceil((1 - CI_ALPHA / 2) * len(boot_kappas))) - 1
    ci_lower = boot_kappas[lo_idx] if boot_kappas else float("nan")
    ci_upper = boot_kappas[hi_idx] if boot_kappas else float("nan")

    return {
        "kappa": observed_kappa,
        "ci_lower": ci_lower,
        "ci_upper": ci_upper,
        "n_items": len(common_ids),
        "n_clusters": n_clusters,
    }
