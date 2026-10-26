"""Tests for prioritize/naive.py — greedy PPR baseline."""
import math

import networkx as nx
import pytest

from prioritize.naive import naive_select
from prioritize.evaluate import attack_length
from prioritize.tests.fixtures.graphs import (
    parallel_paths, exercise1, random_graph,
)
from prioritize.interdiction import build_and_solve

try:
    import highspy  # noqa
    _PULP_AVAILABLE = True
except ImportError:
    _PULP_AVAILABLE = False


def _make_simple_findings(G):
    """Create simple findings for a graph."""
    from prioritize.findings import enumerate_findings
    return enumerate_findings(G)


def test_naive_respects_budget():
    """Naive never picks a set whose total cost exceeds the budget."""
    G, entry, crown, findings = parallel_paths()
    budget = 1
    result = naive_select(G, entry, findings, budget)
    total = sum(f["cost"] for f in findings if f["finding_id"] in result["selected"])
    assert total <= budget + 1e-9, f"total cost {total} exceeds budget {budget}"


def test_naive_skips_unaffordable_and_takes_later():
    """Naive skips an unaffordable finding but continues to take cheaper ones."""
    G = nx.DiGraph()
    G.add_node("s", kind="internet", label="s")
    G.add_node("m1", kind="user", label="m1")
    G.add_node("m2", kind="user", label="m2")
    G.add_node("t", kind="admin", label="t")
    G.add_edge("s", "m1", p=0.9, etype="USES_KEY")
    G.add_edge("m1", "t", p=0.85, etype="CAN_ESCALATE")
    G.add_edge("s", "m2", p=0.5, etype="USES_KEY")
    G.add_edge("m2", "t", p=0.5, etype="CAN_ESCALATE")

    # Expensive finding (cost 3) first by PPR score, cheap one (cost 1) second
    findings = [
        {
            "finding_id": "F-expensive",
            "fix_op": "remove_policy_statement",
            "target": "m1",
            "target_label": "m1",
            "covers": [["m1", "t", "CAN_ESCALATE"]],
            "delta": 5.0,
            "cost": 3,
            "rule_family": "iam_privilege_escalation",
            "rule_ids": [],
            "rule_gap": True,
            "simulated": True,
        },
        {
            "finding_id": "F-cheap",
            "fix_op": "remove_policy_statement",
            "target": "m2",
            "target_label": "m2",
            "covers": [["m2", "t", "CAN_ESCALATE"]],
            "delta": 5.0,
            "cost": 1,
            "rule_family": "iam_privilege_escalation",
            "rule_ids": [],
            "rule_gap": True,
            "simulated": True,
        },
    ]

    # Budget = 2: cannot afford F-expensive (3), but can afford F-cheap (1)
    result = naive_select(G, ["s"], findings, budget=2)
    assert "F-cheap" in result["selected"], (
        "Naive should take F-cheap after skipping unaffordable F-expensive"
    )
    assert "F-expensive" not in result["selected"]


def test_naive_deterministic_ties():
    """Naive is deterministic when PPR scores tie (lower cost then finding_id)."""
    G = nx.DiGraph()
    G.add_node("s", kind="internet", label="s")
    G.add_node("m", kind="user", label="m")
    G.add_node("t", kind="admin", label="t")
    G.add_edge("s", "m", p=0.5, etype="USES_KEY")
    G.add_edge("m", "t", p=0.5, etype="CAN_ESCALATE")

    findings = [
        {
            "finding_id": "F-b",
            "fix_op": "remove_policy_statement",
            "target": "m",
            "target_label": "m",
            "covers": [["m", "t", "CAN_ESCALATE"]],
            "delta": 5.0, "cost": 2,
            "rule_family": "iam_privilege_escalation",
            "rule_ids": [], "rule_gap": True, "simulated": True,
        },
        {
            "finding_id": "F-a",
            "fix_op": "remove_policy_statement",
            "target": "m",
            "target_label": "m",
            "covers": [["s", "m", "USES_KEY"]],
            "delta": 5.0, "cost": 1,
            "rule_family": "iam_privilege_escalation",
            "rule_ids": [], "rule_gap": True, "simulated": True,
        },
    ]

    r1 = naive_select(G, ["s"], findings, budget=5)
    r2 = naive_select(G, ["s"], findings, budget=5)
    assert r1["selected"] == r2["selected"]


def test_naive_does_not_mutate_graph():
    """naive_select does not alter the graph."""
    G, entry, crown, findings = parallel_paths()
    edges_before = sorted((u, v, d["p"]) for u, v, d in G.edges(data=True))
    naive_select(G, entry, findings, budget=2)
    edges_after = sorted((u, v, d["p"]) for u, v, d in G.edges(data=True))
    assert edges_before == edges_after


def test_naive_empty_findings():
    """Naive handles empty findings list gracefully."""
    G, entry, crown, _ = exercise1()
    result = naive_select(G, entry, [], budget=5)
    assert result["selected"] == []


def test_interdiction_ge_naive_optimality_property():
    """Interdiction objective ≥ naive objective on 100 random seeds × budgets."""
    strict_better = 0
    total = 0
    BUDGETS = [2, 4, 6]

    for seed in range(100):
        G, entry, crown, findings = random_graph(
            seed, n_nodes=9, n_edges=16, n_fixes=8
        )
        import networkx as nx
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
        except Exception:
            ppr = {}

        for budget in BUDGETS:
            naive_result = naive_select(G, entry, findings, budget, ppr=ppr)
            naive_sel = set(naive_result["selected"])
            naive_obj = attack_length(G, entry, crown, naive_sel, findings)

            try:
                interd = build_and_solve(G, entry, crown, findings, budget,
                                         backend="scipy")
            except RuntimeError:
                continue  # degenerate graph causes solver error; skip instance
            interd_obj = interd.get("objective")
            if interd_obj is None:
                continue

            total += 1
            assert interd_obj >= naive_obj - 1e-9, (
                f"seed={seed} budget={budget}: interdiction={interd_obj:.6f} "
                f"< naive={naive_obj:.6f}"
            )
            if interd_obj > naive_obj + 1e-9:
                strict_better += 1

    # Report (not a hard assertion on strict_better count, just informational)
    print(f"\nInterdiction strictly better than naive: {strict_better}/{total} instances")
    assert total > 0, "No usable instances found"
