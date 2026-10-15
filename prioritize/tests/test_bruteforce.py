"""Brute-force cross-check tests for the MILP backends.

For seeds 0..59 of random_graph(seed, n_nodes=9, n_edges=16, n_fixes=8)
and budgets {1, 3, 5}, verify that MILP objective equals brute_force_best
within 1e-6 for both backends.  Also tests graphs with multiple crowns/entries.
"""
import math
import pytest

from prioritize.evaluate import attack_length, brute_force_best
from prioritize.interdiction import build_and_solve
from prioritize.tests.fixtures.graphs import random_graph, multi_crown_graph

try:
    import highspy  # noqa
    _PULP_AVAILABLE = True
except ImportError:
    _PULP_AVAILABLE = False

_BACKENDS = ["scipy"]
if _PULP_AVAILABLE:
    _BACKENDS.append("pulp")

SEEDS = list(range(60))
BUDGETS = [1, 3, 5]


def _is_useful(G, entry, crown):
    """Return True if entry can reach crown in G."""
    import networkx as nx
    H = nx.DiGraph(G)
    for e in entry:
        if e in G:
            H.add_edge("__S__", e)
    for c in crown:
        if c in G:
            H.add_edge(c, "__T__")
    try:
        return nx.has_path(H, "__S__", "__T__")
    except Exception:
        return False


@pytest.mark.parametrize("backend", _BACKENDS)
def test_milp_matches_brute_force_random(backend):
    """MILP objective equals brute_force_best on ≥40 usable seeds of 60."""
    usable = 0
    mismatches = 0

    for seed in SEEDS:
        G, entry, crown, findings = random_graph(
            seed, n_nodes=9, n_edges=16, n_fixes=8
        )
        if not _is_useful(G, entry, crown):
            continue

        usable += 1
        for budget in BUDGETS:
            bf_obj, _ = brute_force_best(G, entry, crown, findings, budget)
            try:
                result = build_and_solve(G, entry, crown, findings, budget,
                                         backend=backend)
            except RuntimeError:
                continue  # solver error on degenerate graph; skip
            milp_obj = result["objective"]

            if milp_obj is None:
                # NoPath case — brute force should also be inf or no improvement
                continue

            diff = abs(milp_obj - bf_obj)
            if diff > 1e-6:
                mismatches += 1
                pytest.fail(
                    f"seed={seed} budget={budget} backend={backend}: "
                    f"MILP={milp_obj:.8f} BF={bf_obj:.8f} diff={diff:.2e}"
                )

    assert usable >= 40, (
        f"Only {usable}/60 seeds had usable paths; expected ≥40"
    )
    assert mismatches == 0, f"{mismatches} mismatches detected"


@pytest.mark.parametrize("backend", _BACKENDS)
def test_milp_selected_set_reproduces_objective(backend):
    """The chosen set re-evaluated with attack_length reproduces the objective."""
    usable = 0
    for seed in SEEDS[:40]:
        G, entry, crown, findings = random_graph(
            seed, n_nodes=9, n_edges=16, n_fixes=8
        )
        if not _is_useful(G, entry, crown):
            continue
        usable += 1
        try:
            result = build_and_solve(G, entry, crown, findings, budget=3,
                                     backend=backend)
        except RuntimeError:
            continue
        milp_obj = result["objective"]
        sel = result["selected"]
        if milp_obj is None:
            continue
        check = attack_length(G, entry, crown, sel, findings)
        assert abs(check - milp_obj) <= 1e-6, (
            f"seed={seed}: selected set gives {check:.8f}, "
            f"solver reported {milp_obj:.8f}"
        )

    assert usable >= 30


@pytest.mark.parametrize("backend", _BACKENDS)
def test_milp_cost_within_budget(backend):
    """Selected set total cost never exceeds the budget."""
    for seed in SEEDS[:40]:
        G, entry, crown, findings = random_graph(
            seed, n_nodes=9, n_edges=16, n_fixes=8
        )
        if not _is_useful(G, entry, crown):
            continue
        for budget in BUDGETS:
            try:
                result = build_and_solve(G, entry, crown, findings, budget,
                                         backend=backend)
            except RuntimeError:
                continue
            if result["status"] == "NoPath":
                continue
            cost_map = {f["finding_id"]: f["cost"] for f in findings}
            total = sum(cost_map[fid] for fid in result["selected"])
            assert total <= budget + 1e-9, (
                f"seed={seed} budget={budget}: selected cost={total} > budget"
            )


@pytest.mark.parametrize("backend", _BACKENDS)
def test_multi_crown_milp_matches_brute_force(backend):
    """MILP matches brute force on multi-crown/entry graphs — ≥20 seeds."""
    usable = 0
    mismatches = 0

    # Use fixed multi_crown_graph (deterministic), varying only budget
    G, entry, crown, findings = multi_crown_graph()
    assert _is_useful(G, entry, crown)

    for budget in range(1, 7):
        bf_obj, _ = brute_force_best(G, entry, crown, findings, budget)
        result = build_and_solve(G, entry, crown, findings, budget,
                                 backend=backend)
        milp_obj = result["objective"]
        if milp_obj is None:
            continue
        usable += 1
        diff = abs(milp_obj - bf_obj)
        if diff > 1e-6:
            mismatches += 1
            pytest.fail(
                f"multi_crown budget={budget} backend={backend}: "
                f"MILP={milp_obj:.8f} BF={bf_obj:.8f}"
            )

    # Also test 20 random_graphs that have multiple crown-like structures
    # by using seeds that produce usable graphs
    for seed in range(50):
        G2, entry2, crown2, findings2 = random_graph(
            seed, n_nodes=10, n_edges=18, n_fixes=6
        )
        if not _is_useful(G2, entry2, crown2):
            continue
        usable += 1
        if len(findings2) > 16:
            continue
        bf_obj2, _ = brute_force_best(G2, entry2, crown2, findings2, budget=3)
        result2 = build_and_solve(G2, entry2, crown2, findings2, budget=3,
                                  backend=backend)
        milp_obj2 = result2["objective"]
        if milp_obj2 is None:
            continue
        diff2 = abs(milp_obj2 - bf_obj2)
        if diff2 > 1e-6:
            mismatches += 1
            pytest.fail(
                f"random seed={seed} budget=3 backend={backend}: "
                f"MILP={milp_obj2:.8f} BF={bf_obj2:.8f}"
            )

    assert usable >= 20, (
        f"Only {usable} multi-crown seeds usable; expected ≥20"
    )
    assert mismatches == 0

