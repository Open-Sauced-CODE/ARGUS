"""Tests for prioritize/evaluate.py — independent evaluator."""
import math

import networkx as nx
import pytest

from prioritize.evaluate import attack_length, brute_force_best, residual_prob
from prioritize.tests.fixtures.graphs import (
    toy_graph, parallel_paths, exercise1, random_graph,
)

DELTA_MAX = -math.log(1e-6)


# ---------------------------------------------------------------------------
# attack_length basics
# ---------------------------------------------------------------------------

def test_attack_length_budget0_equals_dijkstra():
    """attack_length with empty selection equals networkx shortest path."""
    G, entry, crown, findings = exercise1()
    # Budget 0: no fixes applied
    al = attack_length(G, entry, crown, set(), findings)
    # Manual Dijkstra on -ln(p) graph
    H = nx.DiGraph()
    for u, v, d in G.edges(data=True):
        H.add_edge(u, v, w=-math.log(d["p"]))
    H.add_edge("__S__", "s", w=0.0)
    H.add_edge("t", "__T__", w=0.0)
    expected = nx.dijkstra_path_length(H, "__S__", "__T__", weight="w")
    assert abs(al - expected) < 1e-9


def test_attack_length_no_path_returns_inf():
    G = nx.DiGraph()
    G.add_node("a", kind="user", label="a")
    G.add_node("b", kind="admin", label="b")
    # No edges
    val = attack_length(G, ["a"], ["b"], set(), [])
    assert val == math.inf


def test_attack_length_parallel_paths_naive_set():
    """alpha+beta set leaves path B open → attack_length ≈ -ln(0.25)."""
    G, entry, crown, findings = parallel_paths()
    sel = {"F-alpha", "F-beta"}
    val = attack_length(G, entry, crown, sel, findings)
    expected = -math.log(0.25)
    assert abs(val - expected) < 1e-6, f"{val} != {expected}"


def test_attack_length_parallel_paths_interdiction_set():
    """alpha+gamma set cuts both paths → attack_length >> 14."""
    G, entry, crown, findings = parallel_paths()
    sel = {"F-alpha", "F-gamma"}
    val = attack_length(G, entry, crown, sel, findings)
    assert val > 14.0, f"Expected > 14.0, got {val}"
    assert val < 14.2, f"Expected < 14.2, got {val}"


def test_attack_length_exercise1_fix_sa():
    """Fixing s→a in exercise1 should give objective 3.0."""
    G, entry, crown, findings = exercise1()
    # Fix s→a (delta=5): path s→a→t has length 1+1+5=7; path s→t has length 3
    sel = {"F-sa"}
    val = attack_length(G, entry, crown, sel, findings)
    assert abs(val - 3.0) < 1e-9, f"Expected 3.0, got {val}"


# ---------------------------------------------------------------------------
# brute_force_best
# ---------------------------------------------------------------------------

def test_brute_force_exercise1_budget2():
    """Brute force on exercise1 with budget 2 gives objective 7.0."""
    G, entry, crown, findings = exercise1()
    best_obj, best_sets = brute_force_best(G, entry, crown, findings, budget=2)
    assert abs(best_obj - 7.0) < 1e-9, f"Expected 7.0, got {best_obj}"


def test_brute_force_exercise1_budget1():
    """Brute force on exercise1 with budget 1 gives objective 3.0."""
    G, entry, crown, findings = exercise1()
    best_obj, _ = brute_force_best(G, entry, crown, findings, budget=1)
    assert abs(best_obj - 3.0) < 1e-9, f"Expected 3.0, got {best_obj}"


def test_brute_force_refuses_too_many_findings():
    """brute_force_best raises ValueError for > 16 findings."""
    G = nx.DiGraph()
    G.add_node("s", kind="internet", label="s")
    G.add_node("t", kind="admin", label="t")
    # 17 dummy findings (all covering a non-existent edge, but we check count first)
    findings = [
        {
            "finding_id": f"F-{i:02d}",
            "fix_op": "remove_policy_statement",
            "target": f"n{i}",
            "covers": [["s", "t", "CAN_ESCALATE"]],
            "delta": 1.0,
            "cost": 1,
        }
        for i in range(17)
    ]
    with pytest.raises(ValueError, match="brute_force_best"):
        brute_force_best(G, ["s"], ["t"], findings, budget=100)


# ---------------------------------------------------------------------------
# residual_prob
# ---------------------------------------------------------------------------

def test_residual_prob_finite():
    assert abs(residual_prob(2.0) - math.exp(-2.0)) < 1e-12


def test_residual_prob_inf():
    assert residual_prob(math.inf) == 0.0


def test_residual_prob_none():
    assert residual_prob(None) == 0.0
