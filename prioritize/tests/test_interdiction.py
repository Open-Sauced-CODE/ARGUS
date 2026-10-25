"""Tests for prioritize/interdiction.py — MILP solver."""
import math

import networkx as nx
import pytest

from prioritize.interdiction import build_and_solve, prioritize, SolverMismatchError
from prioritize.evaluate import attack_length
from prioritize.tests.fixtures.graphs import (
    parallel_paths, exercise1, random_graph, multi_crown_graph,
)

DELTA_MAX = -math.log(1e-6)

# Test both backends
try:
    import highspy  # noqa
    _PULP_AVAILABLE = True
except ImportError:
    _PULP_AVAILABLE = False

_BACKENDS = ["scipy"]
if _PULP_AVAILABLE:
    _BACKENDS.append("pulp")


@pytest.mark.parametrize("backend", _BACKENDS)
def test_budget_zero_empty_selection(backend):
    """Budget 0 → empty selection, objective equals baseline."""
    G, entry, crown, findings = exercise1()
    result = build_and_solve(G, entry, crown, findings, budget=0, backend=backend)
    assert result["selected"] == set()
    baseline = attack_length(G, entry, crown, set(), findings)
    assert result["objective"] is not None
    assert abs(result["objective"] - baseline) < 1e-9


@pytest.mark.parametrize("backend", _BACKENDS)
def test_exercise1_budget1(backend):
    """exercise1 budget 1 → objective 3.0."""
    G, entry, crown, findings = exercise1()
    result = build_and_solve(G, entry, crown, findings, budget=1, backend=backend)
    assert result["objective"] is not None
    assert abs(result["objective"] - 3.0) < 1e-9, \
        f"Expected 3.0, got {result['objective']}"


@pytest.mark.parametrize("backend", _BACKENDS)
def test_exercise1_budget2(backend):
    """exercise1 budget 2 → objective 7.0."""
    G, entry, crown, findings = exercise1()
    result = build_and_solve(G, entry, crown, findings, budget=2, backend=backend)
    assert result["objective"] is not None
    assert abs(result["objective"] - 7.0) < 1e-9, \
        f"Expected 7.0, got {result['objective']}"


@pytest.mark.parametrize("backend", _BACKENDS)
def test_parallel_paths_budget2(backend):
    """parallel_paths budget 2 → selected contains gamma and one of alpha/beta."""
    G, entry, crown, findings = parallel_paths()
    result = build_and_solve(G, entry, crown, findings, budget=2, backend=backend)
    sel = result["selected"]
    assert "F-gamma" in sel, f"gamma not selected: {sel}"
    assert "F-alpha" in sel or "F-beta" in sel, \
        f"Neither alpha nor beta selected: {sel}"
    obj = result["objective"]
    assert obj is not None
    assert obj > 14.0, f"Objective {obj} not > 14.0"
    assert obj < 14.2, f"Objective {obj} not < 14.2"


@pytest.mark.parametrize("backend", _BACKENDS)
def test_parallel_paths_naive_check(backend):
    """alpha+beta set (naive choice) gives attack_length ≈ -ln(0.25)."""
    G, entry, crown, findings = parallel_paths()
    val = attack_length(G, entry, crown, {"F-alpha", "F-beta"}, findings)
    expected = -math.log(0.25)
    assert abs(val - expected) < 1e-6, f"{val} vs {expected}"


@pytest.mark.parametrize("backend", _BACKENDS)
def test_objective_nondecreasing_with_budget(backend):
    """Objective never decreases as budget grows 0..4."""
    G, entry, crown, findings = parallel_paths()
    prev_obj = -math.inf
    for b in range(5):
        result = build_and_solve(G, entry, crown, findings, budget=b, backend=backend)
        obj = result["objective"] if result["objective"] is not None else 0.0
        assert obj >= prev_obj - 1e-9, \
            f"Objective decreased from {prev_obj} to {obj} at budget {b}"
        prev_obj = obj


@pytest.mark.parametrize("backend", _BACKENDS)
def test_no_path_returns_no_path(backend):
    """If no path from entry to crown, return NoPath without calling solver."""
    G = nx.DiGraph()
    G.add_node("a", kind="internet", label="a")
    G.add_node("b", kind="admin", label="b")
    # No edges at all
    result = build_and_solve(G, ["a"], ["b"], [], budget=5, backend=backend)
    assert result["status"] == "NoPath"
    assert result["selected"] == set()
    assert result["objective"] is None


@pytest.mark.parametrize("backend", _BACKENDS)
def test_graph_not_mutated(backend):
    G, entry, crown, findings = exercise1()
    edges_before = sorted((u, v, d["p"]) for u, v, d in G.edges(data=True))
    build_and_solve(G, entry, crown, findings, budget=2, backend=backend)
    edges_after = sorted((u, v, d["p"]) for u, v, d in G.edges(data=True))
    assert edges_before == edges_after


def test_unknown_covered_edge_raises():
    G = nx.DiGraph()
    G.add_node("s", kind="internet", label="s")
    G.add_node("t", kind="admin", label="t")
    G.add_edge("s", "t", p=0.5, etype="CAN_ESCALATE")
    bad_finding = [{
        "finding_id": "F-bad",
        "fix_op": "remove_policy_statement",
        "target": "x",
        "covers": [["x", "y", "CAN_ESCALATE"]],  # edges not in G
        "delta": 5.0,
        "cost": 1,
    }]
    with pytest.raises(ValueError, match="not in G"):
        build_and_solve(G, ["s"], ["t"], bad_finding, budget=5)


def test_same_edge_covered_twice_raises():
    G = nx.DiGraph()
    G.add_node("s", kind="internet", label="s")
    G.add_node("t", kind="admin", label="t")
    G.add_edge("s", "t", p=0.5, etype="CAN_ESCALATE")
    dup_findings = [
        {
            "finding_id": "F-d1",
            "fix_op": "remove_policy_statement",
            "target": "d1",
            "covers": [["s", "t", "CAN_ESCALATE"]],
            "delta": 5.0, "cost": 1,
        },
        {
            "finding_id": "F-d2",
            "fix_op": "remove_policy_statement",
            "target": "d2",
            "covers": [["s", "t", "CAN_ESCALATE"]],
            "delta": 5.0, "cost": 1,
        },
    ]
    with pytest.raises(ValueError, match="Edge-disjointness"):
        build_and_solve(G, ["s"], ["t"], dup_findings, budget=5)


def test_no_valid_entry_raises():
    G = nx.DiGraph()
    G.add_node("a", kind="internet", label="a")
    G.add_node("b", kind="admin", label="b")
    G.add_edge("a", "b", p=0.5, etype="CAN_ESCALATE")
    with pytest.raises(ValueError, match="entry"):
        build_and_solve(G, ["nonexistent"], ["b"], [], budget=5)


@pytest.mark.parametrize("backend", _BACKENDS)
def test_prioritize_returns_all_ids_exactly_once(backend):
    G, entry, crown, findings = exercise1()
    ranked = prioritize(findings, budget=2, G=G, entry_nodes=entry,
                        crown_jewels=crown)
    assert sorted(ranked) == sorted(f["finding_id"] for f in findings)
    assert len(ranked) == len(findings)


@pytest.mark.parametrize("backend", _BACKENDS)
def test_ordering_rule_selected_first(backend):
    """Selected findings appear before unselected in prioritize output."""
    G, entry, crown, findings = parallel_paths()
    from prioritize.interdiction import prioritize_detailed
    result = prioritize_detailed(findings, budget=2, G=G,
                                 entry_nodes=entry, crown_jewels=crown)
    ranked = result["ranked"]
    selected = set(result["selected"])
    # All selected should appear before any unselected
    in_selected = [f["finding_id"] in selected for f in ranked]
    # Find last selected position
    last_sel = max((i for i, v in enumerate(in_selected) if v), default=-1)
    first_unsel = min((i for i, v in enumerate(in_selected) if not v), default=len(ranked))
    assert last_sel < first_unsel or first_unsel == len(ranked), \
        "Unselected findings appear before selected ones"


@pytest.mark.parametrize("backend", _BACKENDS)
def test_multi_crown_multi_entry(backend):
    """Graph with 2 entries and 2 crown jewels is handled correctly."""
    G, entry, crown, findings = multi_crown_graph()
    result = build_and_solve(G, entry, crown, findings, budget=3, backend=backend)
    assert result["status"] != "NoPath"
    obj = result["objective"]
    assert obj is not None
    assert obj >= 0


@pytest.mark.parametrize("backend", _BACKENDS)
def test_backends_agree_on_exercise1(backend):
    """Both backends produce objectives within 1e-6 on exercise1."""
    G, entry, crown, findings = exercise1()
    r1 = build_and_solve(G, entry, crown, findings, budget=2, backend="scipy")
    r2 = build_and_solve(G, entry, crown, findings, budget=2, backend=backend)
    assert r1["objective"] is not None and r2["objective"] is not None
    assert abs(r1["objective"] - r2["objective"]) < 1e-6, \
        f"scipy={r1['objective']}, {backend}={r2['objective']}"
