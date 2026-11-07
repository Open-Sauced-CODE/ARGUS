"""Honest negative accounting for the M2 pre-registered bar (Shaurya-owned).

Contract
--------
Counts are DISTINCT candidates (generator, input_key, answer_key) and CLUSTERS (input_key); generated rows are
never added to a count. Natural and corruptor negatives are reported separately and never summed into one PASS.

Natural scored candidate: gate_pass AND outcome == "fixed" AND oracle_class in {minimal_correct,
valid_not_minimal, wrong, fixed_should_escalate}. Strict negative = everything except minimal_correct (the
pre-registered strict label); harmful negative = wrong or fixed_should_escalate only.

Pools (per generator and union):
  all          every labeled input
  usable       input in no held-out set
  calibration  usable AND not seen by that generator's training (A_val-only inputs live here; note that M1
               model selection used A_val, so candidates on A_val are mildly optimistic)
"""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from typing import Any, Iterable, Mapping

from ml.train_m2.labels.leakguard import CORRUPTOR, KeySets

POS = {"minimal_correct"}
STRICT_NEG = {"wrong", "valid_not_minimal", "fixed_should_escalate"}
HARM_NEG = {"wrong", "fixed_should_escalate"}
NATURAL_CLUSTER_THRESHOLD = 59
NEGATIVE_BAR = 300
POOLS = ("all", "usable", "calibration")


def cp_upper_zero_errors(n: int, delta: float = 0.05) -> float:
    """One-sided Clopper-Pearson upper bound on the error rate after 0 errors in n accepted clusters."""
    return float("nan") if n <= 0 else 1.0 - delta ** (1.0 / n)


def is_scored_candidate(row: Mapping[str, Any]) -> bool:
    return (
        row.get("source") != CORRUPTOR
        and row.get("gate_pass") is True
        and row.get("outcome") == "fixed"
        and row.get("oracle_class") in (POS | STRICT_NEG)
    )


def _cand_key(row: Mapping[str, Any]) -> tuple:
    ak = row.get("answer_key")
    return (row["input_key"], ak if ak is not None else f"row:{row.get('source_file')}:{row.get('sample_idx')}")


def _pools(row: Mapping[str, Any], ks: KeySets) -> list[str]:
    k = row["input_key"]
    out = ["all"]
    if not ks.heldout_sets_of(k):
        out.append("usable")
        if not ks.generator_seen(row["generator"], k):
            out.append("calibration")
    return out


def _summarise(cands: Mapping[tuple, str]) -> dict[str, Any]:
    cls = Counter(cands.values())
    clusters: dict[str, set[str]] = {"all": set(), "pos": set(), "strict_neg": set(), "harm_neg": set()}
    for (ik, _), c in cands.items():
        clusters["all"].add(ik)
        if c in POS:
            clusters["pos"].add(ik)
        if c in STRICT_NEG:
            clusters["strict_neg"].add(ik)
        if c in HARM_NEG:
            clusters["harm_neg"].add(ik)
    return {
        "candidates": len(cands),
        "positives": sum(cls[c] for c in POS),
        "strict_negatives": sum(cls[c] for c in STRICT_NEG),
        "harmful_negatives": sum(cls[c] for c in HARM_NEG),
        "by_class": dict(sorted(cls.items())),
        "clusters": len(clusters["all"]),
        "clusters_with_positive": len(clusters["pos"]),
        "clusters_with_strict_negative": len(clusters["strict_neg"]),
        "clusters_with_harmful_negative": len(clusters["harm_neg"]),
    }


def compute_accounting(rows: Iterable[Mapping[str, Any]], ks: KeySets, deployment: str = "sft") -> dict[str, Any]:
    per: dict[tuple[str, str], dict[tuple, str]] = defaultdict(dict)   # (pool, generator|"union") -> cand -> class
    cor_all: dict[tuple, dict] = {}
    n_missing_ak = 0
    for row in rows:
        if row.get("source") == CORRUPTOR:
            sk = row.get("source_input_key") or row["input_key"]
            cor_all.setdefault((sk, row.get("corruption_type"), row.get("answer_key")), dict(row))
            continue
        if not is_scored_candidate(row):
            continue
        if row.get("answer_key") is None:
            n_missing_ak += 1
        ck = _cand_key(row)
        for pool in _pools(row, ks):
            per[(pool, row["generator"])].setdefault(ck, row["oracle_class"])
            per[(pool, "union")].setdefault(ck, row["oracle_class"])
    natural: dict[str, dict[str, Any]] = {}
    for (pool, scope), cands in sorted(per.items()):
        natural.setdefault(pool, {})[scope] = _summarise(cands)

    cor_types: dict[str, dict[str, Any]] = {}
    hard_keys: set[tuple] = set()
    for (sk, ct, ak), row in cor_all.items():
        t = cor_types.setdefault(str(ct), {"distinct": 0, "hard_negatives": 0, "seed_clusters": set()})
        t["distinct"] += 1
        if row.get("gate_pass") is True and row.get("oracle_class") == "wrong":
            t["hard_negatives"] += 1
            t["seed_clusters"].add(sk)
            hard_keys.add((sk, ct, ak))
    cor_summary = {
        "distinct_rows": len(cor_all),
        "hard_negatives": len(hard_keys),
        "hard_negative_seed_clusters": len({k[0] for k in hard_keys}),
        "per_type": {t: {"distinct": v["distinct"], "hard_negatives": v["hard_negatives"],
                         "seed_clusters": len(v["seed_clusters"])} for t, v in sorted(cor_types.items())},
    }
    usable_u = natural.get("usable", {}).get("union", {})
    nat_clusters = usable_u.get("clusters_with_strict_negative", 0)
    nat_cands = usable_u.get("strict_negatives", 0)
    total = nat_cands + cor_summary["hard_negatives"]
    calib = {g: {"clusters": s["clusters"], "min_certifiable_alpha_at_0_errors_delta_0.05":
                 cp_upper_zero_errors(s["clusters"])}
             for g, s in natural.get("calibration", {}).items() if g != "union"}
    dep_u = natural.get("usable", {}).get(deployment, {})
    dep_c = natural.get("calibration", {}).get(deployment, {})
    dep_neg_clusters = dep_u.get("clusters_with_strict_negative", 0)
    dep_cal_neg = dep_c.get("strict_negatives", 0)
    deployment_block = {
        "generator": deployment,
        "usable_strict_negative_clusters": dep_neg_clusters,
        "calibration_clusters": dep_c.get("clusters", 0),
        "calibration_strict_negatives": dep_cal_neg,
        "verdict": ("NO NEGATIVES IN THE CALIBRATION POOL: the auto-apply error rate of this generator cannot be "
                    "estimated from it" if dep_cal_neg == 0 else "calibration pool contains negatives"),
        "pooled_bar_note": "the pooled natural-cluster count includes non-deployed generators (e.g. rft_v2, zeroshot); "
                           "it supports TRAINING M2 across generators, not the deployment error estimate",
    }
    bar = {
        "natural_usable_strict_negative_clusters": nat_clusters,
        "natural_cluster_threshold": NATURAL_CLUSTER_THRESHOLD,
        "natural_cluster_verdict": "PASS" if nat_clusters >= NATURAL_CLUSTER_THRESHOLD
        else f"FAIL (shortfall {NATURAL_CLUSTER_THRESHOLD - nat_clusters})",
        "natural_usable_strict_negative_candidates": nat_cands,
        "corruptor_hard_negatives_distinct": cor_summary["hard_negatives"],
        "total_negatives": total,
        "negative_bar": NEGATIVE_BAR,
        "total_verdict": "PASS" if total >= NEGATIVE_BAR else f"FAIL (shortfall {NEGATIVE_BAR - total})",
        "natural_share_of_total": (nat_cands / total) if total else float("nan"),
        "note": "Corruptor negatives are train-only and trivially separable unless shortcut_by_type says "
                "otherwise; evaluation and calibration use natural candidates only.",
    }
    return {"natural": natural, "corruptor": cor_summary, "bar": bar, "deployment": deployment_block,
            "calibration_alpha": calib,
            "rows_missing_answer_key": n_missing_ak}


def render_markdown(rep: Mapping[str, Any]) -> str:
    L = ["# Label acceptance (distinct candidates and clusters; generated rows never summed)", ""]
    for pool in POOLS:
        L += [f"## Natural, pool = {pool}", "",
              "| scope | candidates | positives | strict neg | harmful neg | clusters | clusters w/ strict neg | clusters w/ harmful neg |",
              "|---|---|---|---|---|---|---|---|"]
        for scope, s in sorted(rep["natural"].get(pool, {}).items()):
            L.append(f"| {scope} | {s['candidates']} | {s['positives']} | {s['strict_negatives']} | "
                     f"{s['harmful_negatives']} | {s['clusters']} | {s['clusters_with_strict_negative']} | "
                     f"{s['clusters_with_harmful_negative']} |")
        L.append("")
    c = rep["corruptor"]
    L += ["## Corruptor (train-only, distinct)", "", f"distinct rows {c['distinct_rows']}, hard negatives "
          f"{c['hard_negatives']}, seed clusters {c['hard_negative_seed_clusters']}", "",
          "| type | distinct | hard negatives | seed clusters |", "|---|---|---|---|"]
    for t, v in c["per_type"].items():
        L.append(f"| {t} | {v['distinct']} | {v['hard_negatives']} | {v['seed_clusters']} |")
    b = rep["bar"]
    L += ["", "## Pre-registered bar (natural and corruptor reported separately)", "",
          f"- natural usable strict-negative clusters, POOLED over all generators: "
          f"{b['natural_usable_strict_negative_clusters']} vs {b['natural_cluster_threshold']}: "
          f"**{b['natural_cluster_verdict']}** (pooled count, see deployment line)",
          f"- natural usable strict-negative candidates: {b['natural_usable_strict_negative_candidates']}",
          f"- corruptor hard negatives (distinct): {b['corruptor_hard_negatives_distinct']}",
          f"- total {b['total_negatives']} vs {b['negative_bar']}: **{b['total_verdict']}** "
          f"(natural share {b['natural_share_of_total']:.2f})", f"- {b['note']}", "",
          f"## Deployment generator ({rep['deployment']['generator']})", "",
          f"- usable strict-negative clusters: {rep['deployment']['usable_strict_negative_clusters']}",
          f"- calibration pool: {rep['deployment']['calibration_clusters']} clusters, "
          f"{rep['deployment']['calibration_strict_negatives']} strict negatives",
          f"- **{rep['deployment']['verdict']}**", f"- {rep['deployment']['pooled_bar_note']}", "",
          "## Calibration pool: smallest error rate certifiable with 0 errors (binomial, delta 0.05)", "",
          "| generator | clusters | min alpha |", "|---|---|---|"]
    for g, v in rep["calibration_alpha"].items():
        L.append(f"| {g} | {v['clusters']} | {v['min_certifiable_alpha_at_0_errors_delta_0.05']:.3f} |")
    L += ["", f"rows without answer_key: {rep['rows_missing_answer_key']}"]
    return "\n".join(L) + "\n"


def _main() -> int:  # pragma: no cover - thin CLI
    import argparse
    import glob
    from pathlib import Path

    from ml.train_m2 import common
    from ml.train_m2.labels.leakguard import audit_label_rows, load_key_sets, raise_if_violations

    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", nargs="+", required=True, help="label jsonl files or globs")
    ap.add_argument("--root", default=str(common.repo_root()))
    ap.add_argument("--out", required=True, help="output stem, e.g. ml/train_m2/out/reports/label_acceptance")
    a = ap.parse_args()
    files = sorted({f for g in a.labels for f in glob.glob(g)})
    rows = [r for f in files for r in common.jsonl_iter(f)]
    ks = load_key_sets(Path(a.root))
    raise_if_violations(audit_label_rows(rows, ks))      # never account for rows that fail the leak audit
    rep = compute_accounting(rows, ks)
    Path(a.out + ".md").write_text(render_markdown(rep), encoding="utf-8", newline="\n")
    Path(a.out + ".json").write_text(json.dumps(rep, indent=2, sort_keys=True, default=str) + "\n",
                                     encoding="utf-8", newline="\n")
    common.write_provenance(a.out + ".json", inputs=files, extra={"n_rows": len(rows)})
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
