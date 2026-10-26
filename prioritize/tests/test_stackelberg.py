"""Tests for prioritize/stackelberg_baseline.py.

COMPARISON BASELINE ONLY — not for production.
"""
import math

import pytest

from prioritize.stackelberg_baseline import solve_stackelberg, round_to_binary
from prioritize.evaluate import attack_length
from prioritize.interdiction import build_and_solve
from prioritize.naive import naive_select
from prioritize.tests.fixtures.graphs import random_graph


def _make_findings(ids, costs):
    """Helper: create minimal findings from ids and costs lists."""
    return [
        {
            "finding_id": fid,
            "fix_op": "remove_policy_statement",
            "target": f"t_{fid}",
            "target_label": f"target_{fid}",
            "covers": [],
            "delta": 5.0,
            "cost": cost,
            "rule_family": "iam_privilege_escalation",
            "rule_ids": [],
            "rule_gap": True,
            "simulated": True,
        }
        for fid, cost in zip(ids, costs)
    ]


def test_stackelberg_symmetric_gives_half():
    """Two targets Ra=(10,10), unit costs, B=1 → x=(0.5,0.5)."""
    findings = _make_findings(["F-1", "F-2"], [1, 1])
    ra = {"F-1": 10.0, "F-2": 10.0}
    result = solve_stackelberg(findings, ra, budget=1, pa_ratio=0.2)
    assert result is not None, "Expected a result, got None"
    x = result["x"]
    assert abs(x["F-1"] - 0.5) < 1e-6, f"F-1 coverage: {x['F-1']}"
    assert abs(x["F-2"] - 0.5) < 1e-6, f"F-2 coverage: {x['F-2']}"


def test_stackelberg_asymmetric_pa_zero():
    """Ra=(10,5), pa_ratio=0, unit costs, B=1 → x=(2/3, 1/3)."""
    findings = _make_findings(["F-1", "F-2"], [1, 1])
    ra = {"F-1": 10.0, "F-2": 5.0}
    result = solve_stackelberg(findings, ra, budget=1, pa_ratio=0.0)
    assert result is not None, "Expected a result, got None"
    x = result["x"]
    assert abs(x["F-1"] - 2.0 / 3.0) < 1e-6, f"F-1 coverage: {x['F-1']}"
    assert abs(x["F-2"] - 1.0 / 3.0) < 1e-6, f"F-2 coverage: {x['F-2']}"


def test_stackelberg_all_x_in_0_1():
    """All coverage values must be in [0,1]."""
    findings = _make_findings(["F-1", "F-2", "F-3"], [1, 2, 1])
    ra = {"F-1": 8.0, "F-2": 5.0, "F-3": 3.0}
    result = solve_stackelberg(findings, ra, budget=3, pa_ratio=0.2)
    assert result is not None
    for fid, val in result["x"].items():
        assert -1e-9 <= val <= 1 + 1e-9, f"{fid}: x={val} not in [0,1]"


def test_stackelberg_budget_constraint():
    """Total cost · x ≤ budget + 1e-9."""
    findings = _make_findings(["F-1", "F-2", "F-3"], [1, 2, 1])
    ra = {"F-1": 8.0, "F-2": 5.0, "F-3": 3.0}
    result = solve_stackelberg(findings, ra, budget=2, pa_ratio=0.2)
    assert result is not None
    costs = {f["finding_id"]: f["cost"] for f in findings}
    total = sum(costs[fid] * val for fid, val in result["x"].items())
    assert total <= 2 + 1e-9, f"budget violated: total={total}"


def test_stackelberg_attacker_best_response():
    """At the solution, attacker best-response is at best_target within 1e-6."""
    findings = _make_findings(["F-1", "F-2"], [1, 1])
    ra = {"F-1": 10.0, "F-2": 5.0}
    pa_ratio = 0.2
    result = solve_stackelberg(findings, ra, budget=1, pa_ratio=pa_ratio)
    assert result is not None
    x = result["x"]
    best_t = result["best_target"]

    # Compute Ua for each finding at the solution
    Pa = {fid: -pa_ratio * ra[fid] for fid in ra}
    Ua = {}
    for fid in ra:
        Ua[fid] = (1 - x[fid]) * ra[fid] + x[fid] * Pa[fid]

    # best_target should have Ua at least as large as all others
    max_ua = max(Ua.values())
    assert abs(Ua[best_t] - max_ua) < 1e-6, (
        f"best_target={best_t} Ua={Ua[best_t]:.6f} != max_ua={max_ua:.6f}"
    )


def test_round_to_binary_respects_budget():
    """round_to_binary produces a selected set within budget."""
    findings = _make_findings(["F-1", "F-2", "F-3"], [2, 1, 1])
    x = {"F-1": 0.8, "F-2": 0.6, "F-3": 0.4}
    result = round_to_binary(x, findings, budget=2)
    costs = {f["finding_id"]: f["cost"] for f in findings}
    total = sum(costs[fid] for fid in result["selected"])
    assert total <= 2 + 1e-9


def test_stackelberg_returns_none_for_empty():
    """solve_stackelberg returns None for empty findings."""
    result = solve_stackelberg([], {}, budget=5)
    assert result is None


def test_interdiction_ge_stackelberg_property():
    """Interdiction objective ≥ rounded-Stackelberg on 100 seeds × budgets."""
    import networkx as nx
    strict_better = 0
    total = 0
    BUDGETS = [2, 4, 6]

    for seed in range(100):
        G, entry, crown, findings = random_graph(
            seed, n_nodes=9, n_edges=16, n_fixes=8
        )
        H = nx.DiGraph(G)
        for e in entry:
            if e in G:
                H.add_edge("__S__", e)
        for c in crown:
            if c in G:
                H.add_edge(c, "__T__")
        try:
            has_path = nx.has_path(H, "__S__", "__T__")
        except Exception:
            has_path = False
        if not has_path:
            continue

        try:
            ppr = __import__("risk.pagerank", fromlist=["score_digraph"]).score_digraph(
                G, entry
            )
            ppr_pct = __import__("risk.pagerank", fromlist=["to_percent"]).to_percent(ppr)
        except Exception:
            ppr = {}
            ppr_pct = {}

        ra = {f["finding_id"]: ppr_pct.get(f["target"], 0.0) for f in findings}

        for budget in BUDGETS:
            try:
                interd = build_and_solve(G, entry, crown, findings, budget,
                                         backend="scipy")
            except RuntimeError:
                continue  # degenerate graph; skip
            interd_obj = interd.get("objective")
            if interd_obj is None:
                continue

            try:
                ssg = solve_stackelberg(findings, ra, budget, pa_ratio=0.2)
                if ssg:
                    rounded = round_to_binary(ssg["x"], findings, budget)
                    ssg_sel = set(rounded["selected"])
                else:
                    ssg_sel = set()
            except Exception:
                ssg_sel = set()

            ssg_obj = attack_length(G, entry, crown, ssg_sel, findings)
            total += 1

            assert interd_obj >= ssg_obj - 1e-9, (
                f"seed={seed} budget={budget}: interdiction={interd_obj:.6f} "
                f"< stackelberg={ssg_obj:.6f}"
            )
            if interd_obj > ssg_obj + 1e-9:
                strict_better += 1

    print(f"\nInterdiction strictly better than Stackelberg: {strict_better}/{total}")
    assert total > 0
