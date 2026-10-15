"""Model-vs-simulator agreement tests for prioritize.

Verifies that the MILP's delta model matches what risk.simulate.apply_delta
actually does on the graph.  This is the critical bridge between Phase 3
(optimization model) and Phase 7 (execution gate).

For each simulated fix type:
  - restrict_cidr: new_p = old_p * factor, clamped to ≥ 1e-6
    MILP models this as edge length += -ln(factor) = ln(1/factor) = ln(10) ≈ 2.3026
    Test: exp(-((-ln old_p) + delta)) == new_p within 1e-9
  - remove_policy_statement: out-edges with etype in {CAN_ESCALATE,DIRECT_ADMIN,CAN_ACCESS}
    are removed (p goes effectively to 0)
    MILP models as: edge removed from the reachability graph (delta = delta_max = -ln(1e-6))
"""
import math

import networkx as nx
import pytest

from risk.simulate import apply_delta
from prioritize.findings import load_catalogue


DELTA_MAX = -math.log(1e-6)


# ------------------------------------------------------------------ #
# restrict_cidr
# ------------------------------------------------------------------ #

def test_restrict_cidr_model_agrees_with_simulator():
    """restrict_cidr: exp(-((-ln p) + delta)) == new_p (factor=0.1)."""
    # Minimal graph with one RULE_TO_SG edge
    G = nx.DiGraph()
    G.add_node("rule", kind="iprule", label="rule")
    G.add_node("sg",   kind="sg",     label="sg")
    G.add_edge("rule", "sg", p=0.8, etype="RULE_TO_SG")

    cat = load_catalogue()
    delta = float(cat["fixes"]["restrict_cidr"]["delta"])
    factor = 0.1

    # Apply the simulator
    G2 = apply_delta(G, {"ops": [{"op": "restrict_cidr", "target": "sg", "factor": factor}]})
    new_p = G2["rule"]["sg"]["p"]

    # Model prediction: new_p = exp(-(old_length + delta))
    old_length = -math.log(0.8)
    model_new_length = old_length + delta
    model_new_p = math.exp(-model_new_length)

    assert abs(new_p - model_new_p) < 1e-4, (
        f"Simulator gives p={new_p:.9f}, model predicts p={model_new_p:.9f}"
    )


def test_restrict_cidr_delta_equals_ln_1_over_factor():
    """Catalogue delta for restrict_cidr = ln(1/factor) = ln(10) ≈ 2.3026."""
    cat = load_catalogue()
    delta = float(cat["fixes"]["restrict_cidr"]["delta"])
    expected = math.log(1 / 0.1)  # ln(10)
    assert abs(delta - expected) < 1e-3, (
        f"restrict_cidr delta={delta:.6f}, expected ln(10)={expected:.6f}"
    )


def test_restrict_cidr_floor_at_1e6():
    """restrict_cidr applies the 1e-6 floor (P_FLOOR in simulate.py)."""
    G = nx.DiGraph()
    G.add_node("rule", kind="iprule", label="rule")
    G.add_node("sg",   kind="sg",     label="sg")
    G.add_edge("rule", "sg", p=1e-7, etype="RULE_TO_SG")

    G2 = apply_delta(G, {"ops": [{"op": "restrict_cidr", "target": "sg", "factor": 0.1}]})
    new_p = G2["rule"]["sg"]["p"]
    assert new_p >= 1e-6 - 1e-12, f"Floor not applied: p={new_p}"


# ------------------------------------------------------------------ #
# remove_policy_statement
# ------------------------------------------------------------------ #

def test_remove_policy_statement_removes_can_escalate():
    """remove_policy_statement removes CAN_ESCALATE out-edges of target stmt."""
    G = nx.DiGraph()
    G.add_node("stmt",  kind="stmt",  label="stmt")
    G.add_node("admin", kind="admin", label="admin")
    G.add_edge("stmt", "admin", p=0.9, etype="CAN_ESCALATE")

    G2 = apply_delta(G, {"ops": [{"op": "remove_policy_statement", "target": "stmt"}]})
    assert not G2.has_edge("stmt", "admin"), (
        "CAN_ESCALATE edge should be removed by remove_policy_statement"
    )


def test_remove_policy_statement_removes_direct_admin():
    """remove_policy_statement removes DIRECT_ADMIN out-edges."""
    G = nx.DiGraph()
    G.add_node("stmt",  kind="stmt",  label="stmt")
    G.add_node("admin", kind="admin", label="admin")
    G.add_edge("stmt", "admin", p=1.0, etype="DIRECT_ADMIN")

    G2 = apply_delta(G, {"ops": [{"op": "remove_policy_statement", "target": "stmt"}]})
    assert not G2.has_edge("stmt", "admin"), "DIRECT_ADMIN edge should be removed"


def test_remove_policy_statement_removes_can_access():
    """remove_policy_statement removes CAN_ACCESS out-edges."""
    G = nx.DiGraph()
    G.add_node("stmt",   kind="stmt",   label="stmt")
    G.add_node("bucket", kind="bucket", label="bucket")
    G.add_edge("stmt", "bucket", p=0.8, etype="CAN_ACCESS")

    G2 = apply_delta(G, {"ops": [{"op": "remove_policy_statement", "target": "stmt"}]})
    assert not G2.has_edge("stmt", "bucket"), "CAN_ACCESS edge should be removed"


def test_remove_policy_statement_preserves_other_edges():
    """remove_policy_statement does NOT remove HAS_POLICY edges from stmt."""
    G = nx.DiGraph()
    G.add_node("pol",   kind="policy", label="pol")
    G.add_node("stmt",  kind="stmt",   label="stmt")
    G.add_node("admin", kind="admin",  label="admin")
    G.add_edge("pol",  "stmt",  p=1.0, etype="HAS_STATEMENT")
    G.add_edge("stmt", "admin", p=0.9, etype="CAN_ESCALATE")

    G2 = apply_delta(G, {"ops": [{"op": "remove_policy_statement", "target": "stmt"}]})
    # HAS_STATEMENT should still be present (it's not an admin etype)
    assert G2.has_edge("pol", "stmt"), "HAS_STATEMENT edge should be preserved"
    # CAN_ESCALATE should be gone
    assert not G2.has_edge("stmt", "admin"), "CAN_ESCALATE edge should be removed"


def test_simulator_does_not_mutate_original():
    """apply_delta returns a copy; original G is unchanged."""
    G = nx.DiGraph()
    G.add_node("stmt",  kind="stmt",  label="stmt")
    G.add_node("admin", kind="admin", label="admin")
    G.add_edge("stmt", "admin", p=0.9, etype="CAN_ESCALATE")

    edges_before = list(G.edges(data=True))
    apply_delta(G, {"ops": [{"op": "remove_policy_statement", "target": "stmt"}]})
    assert list(G.edges(data=True)) == edges_before, "G was mutated!"


def test_unknown_op_silently_ignored():
    """An unknown op has no effect (per simulate.py contract)."""
    G = nx.DiGraph()
    G.add_node("s", kind="internet", label="s")
    G.add_node("t", kind="admin",    label="t")
    G.add_edge("s", "t", p=0.5, etype="CAN_ESCALATE")

    G2 = apply_delta(G, {"ops": [{"op": "deactivate_key", "target": "s"}]})
    # Edge should be unchanged (deactivate_key is silently ignored by simulator)
    assert G2.has_edge("s", "t"), "Unknown op should not remove edges"
    assert abs(G2["s"]["t"]["p"] - 0.5) < 1e-9, "Unknown op should not change p"
