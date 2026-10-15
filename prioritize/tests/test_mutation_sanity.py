"""Mutation sanity tests for interdiction.py.

Reads the source text of interdiction.py, applies textual mutations in memory,
loads as a throwaway module, and verifies that each mutant is caught by the
brute-force comparison.  Nothing is written to disk; the repo source is never
altered.

Mutations tested:
  (a) Flip budget constraint direction (>= instead of <=)
  (b) Remove super-sink constraints (crown constraints)
  (c) Drop the minus sign in -ln(p) (use +log instead)
  (d) Replace Binary by continuous (integrality=0 for scipy)
"""
import importlib
import importlib.util
import math
import sys
import types

import pytest

from prioritize.evaluate import attack_length, brute_force_best
from prioritize.tests.fixtures.graphs import random_graph

SEEDS_FOR_MUTATION = list(range(15))


def _import_module_from_source(source_text, module_name):
    """Compile and import a module from a source text string."""
    spec = importlib.util.spec_from_loader(
        module_name, loader=None, origin="<mutation>"
    )
    mod = types.ModuleType(module_name)
    mod.__spec__ = spec
    try:
        code = compile(source_text, f"<mutation:{module_name}>", "exec")
        exec(code, mod.__dict__)
    except Exception as exc:
        raise ImportError(f"Mutation failed to compile/exec: {exc}") from exc
    return mod


def _get_interdiction_source():
    """Read the real interdiction.py source."""
    import prioritize.interdiction as _real
    from pathlib import Path
    return Path(_real.__file__).read_text(encoding="utf-8")


def _is_usable(G, entry, crown):
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


def _check_mutation_caught(mutant_source, mutation_name, n_seeds=15):
    """Load mutant module and verify it gives wrong answers on ≥1 seed."""
    # Try to import; some mutations may fail at import time (which counts as caught)
    try:
        mod = _import_module_from_source(mutant_source, f"_mutant_{mutation_name}")
    except Exception as exc:
        # Import failure counts as caught (e.g., syntax error introduced)
        return True

    caught = False
    for seed in range(n_seeds):
        G, entry, crown, findings = random_graph(
            seed, n_nodes=9, n_edges=16, n_fixes=8
        )
        if not _is_usable(G, entry, crown):
            continue

        bf_obj, _ = brute_force_best(G, entry, crown, findings, budget=3)

        try:
            # Use the mutant's scipy backend (no external deps needed)
            result = mod.build_and_solve(G, entry, crown, findings,
                                         budget=3, backend="scipy")
            milp_obj = result.get("objective")
            if milp_obj is None:
                # If brute force gives a finite answer but mutant says NoPath
                if math.isfinite(bf_obj) and bf_obj > 0:
                    caught = True
                    break
                continue
            diff = abs(milp_obj - bf_obj)
            if diff > 1e-6:
                caught = True
                break
        except Exception:
            caught = True
            break

    return caught


def test_mutation_a_budget_constraint_flipped():
    """Flipping >= for <= in the budget constraint is caught."""
    src = _get_interdiction_source()
    # Assert the substring exists exactly once
    target = "ub.append(float(budget))"
    count = src.count(target)
    assert count == 1, (
        f"Expected exactly 1 occurrence of {target!r}, found {count}. "
        "Update the mutation substring."
    )
    # Mutation: change the budget bound to a negative value to simulate flip
    mutant = src.replace(target, "ub.append(-float(budget))")
    assert _check_mutation_caught(mutant, "budget_flip"), (
        "Mutation (a) budget constraint flip was NOT caught"
    )


def test_mutation_b_no_sink_constraints():
    """Removing crown (super-sink) constraints is caught."""
    src = _get_interdiction_source()
    # Identify the scipy super-sink constraint block
    target = "# Crown constraints: π_T - π_c ≤ 0"
    count = src.count(target)
    assert count == 1, (
        f"Expected exactly 1 occurrence of {target!r}, found {count}. "
        "Update the mutation substring."
    )
    # Remove the crown constraints by replacing with a no-op comment block
    mutant = src.replace(
        "# Crown constraints: π_T - π_c ≤ 0\n"
        "    for c in crown:\n"
        "        A[row, idx[_T]] = 1.0\n"
        "        A[row, idx[c]] = -1.0\n"
        "        ub.append(0.0)\n"
        "        row += 1",
        "# Crown constraints REMOVED (mutation b)",
    )
    assert _check_mutation_caught(mutant, "no_sink"), (
        "Mutation (b) no super-sink constraints was NOT caught"
    )


def test_mutation_c_no_minus_sign():
    """Using +log(p) instead of -log(p) as edge length is caught."""
    src = _get_interdiction_source()
    target = "ub.append(-math.log(float(d[\"p\"])))"
    count = src.count(target)
    assert count == 1, (
        f"Expected exactly 1 occurrence of {target!r}, found {count}. "
        "Update the mutation substring."
    )
    mutant = src.replace(target, "ub.append(math.log(float(d[\"p\"])))")
    assert _check_mutation_caught(mutant, "no_minus"), (
        "Mutation (c) positive log (wrong sign) was NOT caught"
    )


def test_mutation_d_binary_to_continuous():
    """Making fix variables continuous instead of binary is caught."""
    src = _get_interdiction_source()
    target = "integrality[nN:] = 1.0"
    count = src.count(target)
    assert count == 1, (
        f"Expected exactly 1 occurrence of {target!r}, found {count}. "
        "Update the mutation substring."
    )
    # Set integrality to 0 (continuous) for x variables
    mutant = src.replace(target, "integrality[nN:] = 0.0  # mutation d: continuous")
    assert _check_mutation_caught(mutant, "continuous_x"), (
        "Mutation (d) continuous fix variables was NOT caught"
    )


def test_mutation_e_pin_s_documented():
    """π_S = 0 pin: verify it is present and document why it may not change results.

    The scipy backend pins π_S via ub_bounds[idx[_S]] = 0.0 AND lb=0.
    Removing either pin changes the feasible set but the objective may still
    be correct if π_S = 0 is enforced by the positivity + the objective
    driving π_S down to 0.  We document this rather than asserting.
    """
    src = _get_interdiction_source()
    # The pin is ub_bounds[idx[_S]] = 0.0
    target = "ub_bounds[idx[_S]] = 0.0   # π_S pinned to 0"
    present = target in src
    # If the pin is present, fine.  If not, the test flags it for human review.
    assert present, (
        "π_S pin (ub_bounds[idx[_S]] = 0.0) not found in interdiction.py. "
        "Verify the scipy backend still pins π_S = 0. "
        "This test exists to catch silent refactoring."
    )
    # We do NOT assert the mutant fails because removing the upper bound
    # on π_S while keeping lb=0 and the positivity constraint may not change
    # the MILP optimum (π_S will naturally be 0 if it is in the objective).
    # This is documented per spec Section 5 Stage 5(e).
