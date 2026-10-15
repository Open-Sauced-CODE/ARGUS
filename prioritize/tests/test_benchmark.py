"""Tests for prioritize/benchmark.py — synthetic enterprise benchmark."""
import json
import math
import time

import pytest

from prioritize.benchmark import synthetic_enterprise, run_benchmark, _large_enterprise
from prioritize.evaluate import attack_length, residual_prob
from prioritize.interdiction import build_and_solve
from prioritize.naive import naive_select


try:
    import highspy  # noqa
    _PULP_AVAILABLE = True
except ImportError:
    _PULP_AVAILABLE = False


def _has_path(G, entry, crown):
    """Check if any entry can reach any crown jewel."""
    import networkx as nx
    H = nx.DiGraph(G)
    entry_g = [e for e in entry if e in G]
    crown_g = [c for c in crown if c in G]
    for e in entry_g:
        H.add_edge("__S__", e)
    for c in crown_g:
        H.add_edge(c, "__T__")
    try:
        return nx.has_path(H, "__S__", "__T__")
    except Exception:
        return False


def test_generator_deterministic():
    """synthetic_enterprise is deterministic for the same seed."""
    G1, e1, c1, f1 = synthetic_enterprise(seed=0)
    G2, e2, c2, f2 = synthetic_enterprise(seed=0)
    assert sorted(G1.nodes()) == sorted(G2.nodes())
    assert sorted(f1, key=lambda f: f["finding_id"]) == sorted(f2, key=lambda f: f["finding_id"])


def test_generator_all_edges_have_valid_p_and_etype():
    """Every edge has 0 < p ≤ 1 and a non-empty etype."""
    for seed in range(10):
        G, entry, crown, findings = synthetic_enterprise(seed)
        for u, v, d in G.edges(data=True):
            p = d.get("p")
            etype = d.get("etype")
            assert p is not None and 0 < p <= 1.0, (
                f"seed={seed} edge ({u},{v}): invalid p={p}"
            )
            assert etype, f"seed={seed} edge ({u},{v}): missing etype"


def test_interdiction_ge_naive_on_100_seeds():
    """Interdiction objective ≥ naive on 100 seeds."""
    import networkx as nx
    mismatches = 0
    usable = 0

    try:
        ppr_mod = __import__("risk.pagerank", fromlist=["score_digraph"])
        score_digraph = ppr_mod.score_digraph
    except ImportError:
        score_digraph = None

    for seed in range(100):
        G, entry, crown, findings = synthetic_enterprise(seed)
        if not findings:
            continue
        entry_g = [e for e in entry if e in G]
        crown_g = [c for c in crown if c in G]
        if not _has_path(G, entry_g, crown_g):
            continue
        usable += 1

        ppr = {}
        if score_digraph is not None:
            try:
                ppr = score_digraph(G, entry_g)
            except Exception:
                pass

        naive_r = naive_select(G, entry_g, findings, budget=4, ppr=ppr)
        naive_sel = set(naive_r["selected"])
        naive_obj = attack_length(G, entry_g, crown_g, naive_sel, findings)

        try:
            interd = build_and_solve(G, entry_g, crown_g, findings, budget=4,
                                     backend="scipy")
        except RuntimeError:
            continue
        interd_obj = interd.get("objective")
        if interd_obj is None:
            continue

        if interd_obj < naive_obj - 1e-9:
            mismatches += 1
            pytest.fail(
                f"seed={seed}: interdiction={interd_obj:.6f} < naive={naive_obj:.6f}"
            )

    assert usable >= 50, f"Only {usable} usable seeds"
    assert mismatches == 0


def test_scale_probe_time():
    """Large graph (≥40 findings) solves within 5 seconds."""
    G, entry, crown, findings = _large_enterprise(seed=0)
    entry_g = [e for e in entry if e in G]
    crown_g = [c for c in crown if c in G]

    n_findings = len(findings)
    assert n_findings >= 40, (
        f"Scale probe has only {n_findings} findings; expected ≥40. "
        "Consider increasing n_stmts in _large_enterprise."
    )

    t0 = time.time()
    result = build_and_solve(G, entry_g, crown_g, findings, budget=4,
                             backend="scipy")
    elapsed = time.time() - t0

    print(f"\nScale probe: {n_findings} findings, scipy solve time: {elapsed:.3f}s")
    assert elapsed < 5.0, (
        f"Scale probe took {elapsed:.2f}s > 5s limit. n_findings={n_findings}"
    )


def test_benchmark_results_schema():
    """benchmark_results.json (if present) has the expected schema keys."""
    from pathlib import Path
    results_path = Path(__file__).resolve().parents[1] / "benchmark_results.json"
    if not results_path.exists():
        pytest.skip("benchmark_results.json not yet generated; run run_benchmark()")

    data = json.loads(results_path.read_text(encoding="utf-8"))
    required = {"n_seeds", "budgets", "mean_solve_time_s", "max_solve_time_s",
                "brute_force_checks", "brute_force_mismatches", "by_budget"}
    assert required.issubset(data.keys()), (
        f"Missing keys: {required - set(data.keys())}"
    )
    assert data["brute_force_mismatches"] == 0, (
        f"Brute-force mismatches: {data['brute_force_mismatches']}"
    )
