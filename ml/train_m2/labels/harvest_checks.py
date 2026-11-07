"""Harvest and Phase 5 comparison helpers (Shaurya-owned).

Contract
--------
length_stats: share of greedy outputs longer than Phase 5's num_predict (400).
compare_common: compare two {input_key: gate_pass} maps ONLY on the keys they share (rates over different
  input sets are not comparable).
expected_outcome / reference_key: the route guard and the finding_id-insensitive reference comparison used by
  gap22.reconcile (which replaces the earlier per-key helper).
"""
from __future__ import annotations

import copy
import hashlib
import json
from collections import defaultdict
from typing import Any, Callable, Iterable, Mapping

from ml.train_m2.labels.canon import canonical_answer

# meta.route in the dataset is "fix" or "escalate". "T0", "M1" and "ESC" are README labels for the rule table and
# NEVER appear in meta.route; comparing meta.route with "ESC" silently scores every escalate example as a failure.
ROUTE_TO_OUTCOME = {"fix": "fixed", "escalate": "escalated"}


def expected_outcome(route: Any) -> str:
    """Gate outcome a correct answer must have for this meta.route; raises on any other value."""
    if route not in ROUTE_TO_OUTCOME:
        raise ValueError(f"unknown meta.route {route!r}: expected 'fix' or 'escalate' ('ESC'/'T0'/'M1' are README labels)")
    return ROUTE_TO_OUTCOME[route]


def reference_key(target: Any) -> str:
    """Meaning of a reference patch: ops + rationale_ref; finding_id and resource_ref never matter."""
    return canonical_answer(json.dumps(target) if target is not None else None)


def length_stats(rows: Iterable[Mapping[str, Any]], limit: int = 400) -> dict[str, Any]:
    rows = list(rows)
    greedy = [r for r in rows if r.get("sample_idx") == 0]
    n = len(greedy)
    over = sum(1 for r in greedy if (r.get("eval_count") or 0) > limit)
    cut = sum(1 for r in greedy if r.get("done_reason") == "length")
    return {"greedy_rows": n, "greedy_over_limit": over, "greedy_over_limit_share": (over / n) if n else None,
            "greedy_done_length": cut, "limit": limit}


def compare_common(a: Mapping[str, bool], b: Mapping[str, bool]) -> dict[str, Any]:
    common = sorted(set(a) & set(b))
    n = len(common)
    pa = sum(bool(a[k]) for k in common)
    pb = sum(bool(b[k]) for k in common)
    return {"n_a": len(a), "n_b": len(b), "n_common": n, "a_pass": pa, "b_pass": pb,
            "a_rate": (pa / n) if n else None, "b_rate": (pb / n) if n else None,
            "a_only_pass": sum(1 for k in common if a[k] and not b[k]),
            "b_only_pass": sum(1 for k in common if b[k] and not a[k])}
