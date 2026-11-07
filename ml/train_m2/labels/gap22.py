"""Reconcile Phase 5 per-key scoring with per-example scoring on A_val (Shaurya-owned, read-only, no Ollama).

Contract
--------
Phase 5 (ml/train_m1/eval/run_eval.py) groups examples by input_key, generates once from the FIRST example of each
key, scores that candidate with the frozen scorer against the first example, and weights the result by the number
of examples in the key. This module recomputes four numbers with ONE scoring function (the frozen scorer, so the
route semantics are exactly Phase 5's) and reports where they differ:

  A  recorded   Phase 5's own logged per-key result x group size            (expected to be Phase 5's headline)
  B  per-key    re-scored: first example record + the emitted patch, x group size   (MUST equal A, else the
                scoring wrapper is wrong and nothing below may be trusted)
  C  aligned    per example, patch finding_id replaced by the example's finding_id
  D  raw        per example, patch exactly as emitted

score_fn(example, patch) -> (correct: bool, reasons: list[str]) is injected so tests need no OPA.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from ml.train_m2.labels.harvest_checks import expected_outcome, reference_key

ScoreFn = Callable[[Mapping[str, Any], Mapping[str, Any]], "tuple[bool, list[str]]"]


def _short(key: str) -> str:
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:8]


def reconcile(
    examples: Iterable[Mapping[str, Any]],
    patch_by_key: Mapping[str, Mapping[str, Any]],
    recorded_correct_by_key: Mapping[str, bool] | None,
    key_fn: Callable[[Mapping[str, Any]], str],
    score_fn: ScoreFn,
) -> dict[str, Any]:
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for ex in examples:
        groups[key_fn(ex)].append(ex)
    routes = Counter(expected_outcome((ex.get("meta") or {}).get("route")) for exs in groups.values() for ex in exs)
    a = b = c = d = n = 0
    diffs: list[dict[str, Any]] = []
    b_vs_a_mismatch_keys: list[str] = []
    for k, exs in sorted(groups.items()):
        patch = patch_by_key.get(k)
        n += len(exs)
        if patch is None:
            continue
        first = exs[0]
        if recorded_correct_by_key is not None and k in recorded_correct_by_key:
            a += len(exs) * int(bool(recorded_correct_by_key[k]))
        pk_ok, pk_reasons = score_fn(first, patch)
        b += len(exs) * int(pk_ok)
        if recorded_correct_by_key is not None and k in recorded_correct_by_key and bool(recorded_correct_by_key[k]) != pk_ok:
            b_vs_a_mismatch_keys.append(_short(k))
        for ex in exs:
            raw_ok, _ = score_fn(ex, patch)
            aligned = copy.deepcopy(dict(patch))
            aligned["finding_id"] = ex["input"]["finding_id"]
            al_ok, al_reasons = score_fn(ex, aligned)
            c += int(al_ok)
            d += int(raw_ok)
            if al_ok != pk_ok:
                fields = sorted(f for f in set(ex["input"]) | set(first["input"])
                                if f != "finding_id" and ex["input"].get(f) != first["input"].get(f))
                route_diff = (ex.get("meta") or {}).get("route") != (first.get("meta") or {}).get("route")
                ref_diff = reference_key(ex.get("target")) != reference_key(first.get("target"))
                cause = ("route" if route_diff else "record_fields" if fields else "reference" if ref_diff
                         else "unexplained")
                diffs.append({"key": _short(k), "rule_id": ex.get("rule_id"), "finding_id": ex["input"]["finding_id"],
                              "first_finding_id": first["input"]["finding_id"], "per_key_correct": pk_ok,
                              "aligned_correct": al_ok, "aligned_reasons": al_reasons,
                              "route": (ex.get("meta") or {}).get("route"), "record_fields_differ": fields,
                              "reference_differs": ref_diff, "cause": cause})
    return {"n_examples": n, "n_keys": len(groups), "examples_by_expected_outcome": dict(routes),
            "A_recorded_weighted": a if recorded_correct_by_key is not None else None, "B_per_key_rescored_weighted": b,
            "C_per_example_aligned": c, "D_per_example_raw": d,
            "B_equals_A": (a == b) if recorded_correct_by_key is not None else None,
            "keys_where_B_differs_from_A": b_vs_a_mismatch_keys, "n_differing_B_vs_C": len(diffs),
            "cause_counts": dict(Counter(x["cause"] for x in diffs)), "differing_examples": diffs}


def _frozen_score_fn() -> ScoreFn:  # pragma: no cover - needs OPA
    from ml.train_m1.eval.score import score_inputs

    def fn(ex: Mapping[str, Any], patch: Mapping[str, Any]) -> tuple[bool, list[str]]:
        item = {"record": ex["input"], "route": ex["meta"]["route"], "reference": ex.get("target"),
                "contents": [json.dumps(patch)]}
        cand = score_inputs([item])[0]["candidates"][0]
        return bool(cand["correct"]), list(cand.get("reasons") or [])
    return fn


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin CLI over real data
    import glob

    from ml.mutation_engine.dataset_io import input_key as example_key
    from ml.train_m2 import common

    ap = argparse.ArgumentParser()
    ap.add_argument("--gen", default="sft")
    ap.add_argument("--out", default="ml/train_m2/out/reports/gap22")
    a = ap.parse_args(argv)
    root = common.repo_root()
    val = list(common.jsonl_iter(root / "ml" / "mutation_engine" / "dataset" / "val.jsonl"))
    score_fn = _frozen_score_fn()
    out: dict[str, Any] = {}
    # Phase 5 candidates and Phase 5's own recorded per-key result
    p5_log = root / "ml" / "train_m1" / "eval" / "runs" / a.gen / "A_val.candidates.jsonl"
    if p5_log.exists():
        patches: dict[str, dict] = {}
        recorded: dict[str, bool] = {}
        for row in common.jsonl_iter(p5_log):
            try:
                patch = json.loads(row["contents"][0])
            except (TypeError, ValueError):
                continue
            if isinstance(patch, dict):
                patches[row["input_key"]] = patch
            cands = (row.get("scored") or {}).get("candidates") or []
            if cands:
                recorded[row["input_key"]] = bool(cands[0].get("correct"))
        out["phase5"] = reconcile(val, patches, recorded, example_key, score_fn)
    # Harvest candidates (generated from the harvest input record, not from val's first example)
    hpatches: dict[str, dict] = {}
    for f in sorted(glob.glob(str(root / "ml" / "train_m2" / "harvest_out" / a.gen / "A" / "part-*.jsonl"))):
        for r in common.jsonl_iter(f):
            if r.get("sample_idx") == 0:
                try:
                    p = json.loads(r["content"])
                except (TypeError, ValueError):
                    continue
                if isinstance(p, dict):
                    hpatches[r["input_key"]] = p
    out["harvest"] = reconcile(val, hpatches, None, example_key, score_fn)
    L = [f"# A_val reconciliation ({a.gen})", "",
         "A = Phase 5 recorded x group size; B = re-scored per key (must equal A); C = per example, finding_id aligned; "
         "D = per example, raw.", ""]
    for name, r in out.items():
        L += [f"## {name}", f"- examples {r['n_examples']}, keys {r['n_keys']}, expected outcomes {r['examples_by_expected_outcome']}",
              f"- A {r['A_recorded_weighted']}  B {r['B_per_key_rescored_weighted']}  C {r['C_per_example_aligned']}  "
              f"D {r['D_per_example_raw']}  (B == A: {r['B_equals_A']})",
              f"- differing examples (B vs C): {r['n_differing_B_vs_C']}, causes {r['cause_counts']}", ""]
    stem = Path(a.out)
    stem.parent.mkdir(parents=True, exist_ok=True)
    Path(str(stem) + ".md").write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
    Path(str(stem) + ".json").write_text(json.dumps(out, indent=2, sort_keys=True, default=str) + "\n",
                                         encoding="utf-8", newline="\n")
    common.write_provenance(str(stem) + ".json", inputs=["ml/mutation_engine/dataset/val.jsonl"])
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
