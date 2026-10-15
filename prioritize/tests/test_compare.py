"""Tests for compare_methods and budget_sweep in evaluate.py.

Validates the documented differing case (naive vs interdiction on parallel_paths)
and ensures comparison dict has the frozen keys and is JSON-serialisable.
"""
import json
import math

import pytest

from prioritize.evaluate import (
    compare_methods, budget_sweep, attack_length, residual_prob,
)
from prioritize.tests.fixtures.graphs import parallel_paths


_FROZEN_METHOD_KEYS = {
    "name", "selected", "objective", "residual_attack_prob",
    "ppr_crown_jewel_delta", "paths_cut_at_k",
}

_FROZEN_TOP_KEYS = {
    "budget", "entry_count", "crown_jewel_count", "methods", "budget_sweep",
}


def test_documented_differing_case_naive_vs_interdiction():
    """parallel_paths budget=2: naive residual ≈ 0.25, interdiction residual < 1e-5."""
    G, entry, crown, findings = parallel_paths()
    comp = compare_methods(G, entry, crown, findings, budget=2)

    methods = {m["name"]: m for m in comp["methods"]}
    naive = methods["naive"]
    interd = methods["interdiction"]

    # Naive picks alpha+beta, leaving path B open
    assert abs(naive["residual_attack_prob"] - 0.25) < 1e-6, (
        f"Naive residual should be ≈ 0.25, got {naive['residual_attack_prob']}"
    )

    # Interdiction picks alpha+gamma (or beta+gamma), blocking both paths
    assert interd["residual_attack_prob"] < 1e-5, (
        f"Interdiction residual should be < 1e-5, got {interd['residual_attack_prob']}"
    )

    # Interdiction strictly better
    assert interd["objective"] > naive["objective"] + 1e-9, (
        f"Interdiction obj={interd['objective']:.4f} should be > "
        f"naive obj={naive['objective']:.4f}"
    )


def test_comparison_dict_has_frozen_keys():
    """compare_methods returns dict with all frozen keys."""
    G, entry, crown, findings = parallel_paths()
    comp = compare_methods(G, entry, crown, findings, budget=2)

    assert _FROZEN_TOP_KEYS.issubset(comp.keys()), (
        f"Missing keys: {_FROZEN_TOP_KEYS - set(comp.keys())}"
    )
    for m in comp["methods"]:
        assert _FROZEN_METHOD_KEYS.issubset(m.keys()), (
            f"Method {m['name']} missing keys: "
            f"{_FROZEN_METHOD_KEYS - set(m.keys())}"
        )


def test_comparison_dict_json_serialisable():
    """compare_methods output is JSON-serialisable (sets → sorted lists)."""
    G, entry, crown, findings = parallel_paths()
    comp = compare_methods(G, entry, crown, findings, budget=2)

    # sets must be converted; compare_methods should return lists
    try:
        json.dumps(comp)
    except TypeError as e:
        pytest.fail(f"compare_methods output is not JSON-serialisable: {e}")


def test_budget_sweep_monotone_for_interdiction():
    """Interdiction objective never decreases as budget grows."""
    G, entry, crown, findings = parallel_paths()
    sweep = budget_sweep(G, entry, crown, findings, list(range(7)))

    prev = -math.inf
    for row in sweep:
        obj = row["interdiction_objective"]
        assert obj >= prev - 1e-9, (
            f"budget={row['budget']}: obj={obj:.4f} < prev={prev:.4f}"
        )
        prev = obj


def test_stackelberg_note_present():
    """stackelberg_rounded method has the 'comparison only' note."""
    G, entry, crown, findings = parallel_paths()
    comp = compare_methods(G, entry, crown, findings, budget=2)
    methods = {m["name"]: m for m in comp["methods"]}
    ssg = methods.get("stackelberg_rounded")
    if ssg is not None:
        assert "note" in ssg, "stackelberg_rounded should have a 'note' key"
        assert "comparison" in ssg["note"].lower(), (
            "Note should say 'comparison only'"
        )


def test_comparison_three_methods_present():
    """compare_methods returns exactly naive, stackelberg_rounded, interdiction."""
    G, entry, crown, findings = parallel_paths()
    comp = compare_methods(G, entry, crown, findings, budget=2)
    names = {m["name"] for m in comp["methods"]}
    assert names == {"naive", "stackelberg_rounded", "interdiction"}, (
        f"Expected {{naive, stackelberg_rounded, interdiction}}, got {names}"
    )


def test_budget_sweep_returns_all_budgets():
    """budget_sweep returns one row per input budget."""
    G, entry, crown, findings = parallel_paths()
    budgets = list(range(5))
    sweep = budget_sweep(G, entry, crown, findings, budgets)
    assert len(sweep) == len(budgets)
    for row, b in zip(sweep, budgets):
        assert row["budget"] == b
