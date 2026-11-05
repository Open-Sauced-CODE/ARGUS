"""Harvest and Phase 5 comparison helpers (Shaurya-owned).

Contract
--------
length_stats: share of greedy outputs longer than Phase 5's num_predict (400).
compare_common: compare two {input_key: gate_pass} maps ONLY on the keys they share (rates over different
  input sets are not comparable).
per_key_vs_per_example: reconcile Phase 5 scoring (one candidate scored per input_key against the FIRST
  example's record, weighted by example count) with per-example scoring with finding_id aligned. gate(example,
  patch) -> (passed, reasons) is injected so this module never imports the OPA-backed gate.
"""
from __future__ import annotations

import copy
import hashlib
from collections import defaultdict
from typing import Any, Callable, Iterable, Mapping


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


def per_key_vs_per_example(
    examples: Iterable[Mapping[str, Any]],
    patch_by_key: Mapping[str, Mapping[str, Any]],
    key_fn: Callable[[Mapping[str, Any]], str],
    gate: Callable[[Mapping[str, Any], Mapping[str, Any]], tuple[bool, list[str]]],
) -> dict[str, Any]:
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for ex in examples:
        groups[key_fn(ex)].append(ex)
    per_key_total = per_ex_total = n_ex = 0
    diffs: list[dict[str, Any]] = []
    for k, exs in groups.items():
        patch = patch_by_key.get(k)
        if patch is None:
            n_ex += len(exs)
            continue
        first = exs[0]
        pk_pass, pk_reasons = gate(first, patch)
        for ex in exs:
            n_ex += 1
            per_key_total += int(pk_pass)
            aligned = copy.deepcopy(dict(patch))
            aligned["finding_id"] = ex["input"]["finding_id"]
            pe_pass, pe_reasons = gate(ex, aligned)
            per_ex_total += int(pe_pass)
            if pe_pass != pk_pass:
                fields = sorted(
                    f for f in set(ex["input"]) | set(first["input"])
                    if f != "finding_id" and ex["input"].get(f) != first["input"].get(f)
                )
                diffs.append({
                    "key": hashlib.sha1(k.encode("utf-8")).hexdigest()[:8], "rule_id": ex.get("rule_id"), "finding_id": ex["input"]["finding_id"],
                    "first_finding_id": first["input"]["finding_id"], "per_key_pass": pk_pass,
                    "per_example_pass": pe_pass, "per_example_reasons": pe_reasons,
                    "route": (ex.get("meta") or {}).get("route"),
                    "record_fields_differ": fields, "reference_differs": ex.get("target") != first.get("target"),
                })
    return {"n_examples": n_ex, "per_key_weighted_pass": per_key_total, "per_example_aligned_pass": per_ex_total,
            "n_differing_examples": len(diffs), "differing_examples": diffs}
