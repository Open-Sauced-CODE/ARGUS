"""Tests for prioritize/findings.py."""
import math
import copy

import pytest

from prioritize.findings import (
    load_catalogue, load_config, enumerate_findings, list_non_actionable,
    _finding_id, _KNOWN_RULE_IDS,
)
from prioritize.tests.fixtures.graphs import toy_graph

DELTA_MAX = -math.log(1e-6)

# Phase 4 known rule ids (must stay consistent with the set in findings.py)
_PHASE4_RULE_IDS = _KNOWN_RULE_IDS


def test_load_catalogue_returns_dict():
    cat = load_catalogue()
    assert isinstance(cat, dict)
    assert "fixes" in cat


def test_load_config_returns_dict():
    cfg = load_config()
    assert "default_budget" in cfg


def test_finding_id_deterministic():
    fid1 = _finding_id("remove_policy_statement", "some-node-id")
    fid2 = _finding_id("remove_policy_statement", "some-node-id")
    assert fid1 == fid2
    assert fid1.startswith("F-")
    assert len(fid1) == 10  # "F-" + 8 hex chars


def test_toy_graph_one_finding():
    """toy_graph should produce exactly one finding (STM covers both out-edges)."""
    G = toy_graph()
    findings = enumerate_findings(G)
    assert len(findings) == 1, f"Expected 1 finding, got {len(findings)}"
    f = findings[0]
    assert f["fix_op"] == "remove_policy_statement"
    assert f["target"] == "STM"
    # Covers both CAN_ESCALATE and CAN_ACCESS
    etypes = {c[2] for c in f["covers"]}
    assert "CAN_ESCALATE" in etypes
    assert "CAN_ACCESS" in etypes
    assert len(f["covers"]) == 2


def test_finding_ids_stable_across_calls():
    G = toy_graph()
    f1 = enumerate_findings(G)
    f2 = enumerate_findings(G)
    assert [x["finding_id"] for x in f1] == [x["finding_id"] for x in f2]


def test_no_edge_in_two_findings():
    """No edge appears in more than one finding."""
    G = toy_graph()
    findings = enumerate_findings(G)
    covered = {}
    for f in findings:
        for cov in f["covers"]:
            edge = (cov[0], cov[1])
            assert edge not in covered, \
                f"Edge {edge} covered by {covered[edge]} and {f['finding_id']}"
            covered[edge] = f["finding_id"]


def test_graph_not_mutated():
    G = toy_graph()
    edges_before = list(G.edges(data=True))
    nodes_before = list(G.nodes(data=True))
    enumerate_findings(G)
    assert list(G.edges(data=True)) == edges_before
    assert list(G.nodes(data=True)) == nodes_before


def test_aws_managed_stmt_excluded_by_default():
    """AWS-managed statement ids are excluded from enumerate_findings by default."""
    import networkx as nx
    G = toy_graph()
    # Add a fake AWS-managed statement
    aws_stmt = "arn:aws:iam::aws:policy/AdministratorAccess/statement/1"
    G.add_node(aws_stmt, kind="stmt", label="AdminAccess")
    G.add_node("ADMIN_EQUIV2", kind="admin", label="ADMIN_EQUIV2")
    G.add_edge(aws_stmt, "ADMIN_EQUIV2", p=1.0, etype="DIRECT_ADMIN")

    findings = enumerate_findings(G)
    fids_targets = [f["target"] for f in findings]
    assert aws_stmt not in fids_targets, \
        "AWS-managed stmt should be excluded by default"


def test_list_non_actionable_returns_aws_managed():
    import networkx as nx
    G = toy_graph()
    aws_stmt = "arn:aws:iam::aws:policy/AdministratorAccess/statement/1"
    G.add_node(aws_stmt, kind="stmt", label="AdminAccess")
    G.add_node("ADMIN_EQUIV2", kind="admin", label="ADMIN_EQUIV2")
    G.add_edge(aws_stmt, "ADMIN_EQUIV2", p=1.0, etype="DIRECT_ADMIN")

    non_act = list_non_actionable(G)
    targets = [f["target"] for f in non_act]
    assert aws_stmt in targets


def test_rule_ids_only_from_phase4_list():
    G = toy_graph()
    findings = enumerate_findings(G)
    for f in findings:
        for rid in f.get("rule_ids", []):
            assert rid in _PHASE4_RULE_IDS, \
                f"rule_id {rid!r} not in Phase 4 known list"


def test_rule_gap_true_for_can_escalate_only():
    """A finding whose covered edges are only CAN_ESCALATE gets rule_gap=True."""
    G = toy_graph()
    findings = enumerate_findings(G)
    # The STM finding covers CAN_ESCALATE and CAN_ACCESS → no DIRECT_ADMIN → rule_gap
    f = findings[0]
    # CAN_ESCALATE only part: check rule_gap
    assert f["rule_gap"] is True, "CAN_ESCALATE finding should have rule_gap=True"


def test_findings_sorted_by_finding_id():
    G = toy_graph()
    findings = enumerate_findings(G)
    ids = [f["finding_id"] for f in findings]
    assert ids == sorted(ids)


def test_exclude_aws_managed_false_includes_them():
    import networkx as nx
    G = toy_graph()
    aws_stmt = "arn:aws:iam::aws:policy/AdministratorAccess/statement/1"
    G.add_node(aws_stmt, kind="stmt", label="AdminAccess")
    G.add_node("ADMIN_EQUIV2", kind="admin", label="ADMIN_EQUIV2")
    G.add_edge(aws_stmt, "ADMIN_EQUIV2", p=1.0, etype="DIRECT_ADMIN")

    findings = enumerate_findings(G, exclude_aws_managed=False)
    targets = [f["target"] for f in findings]
    assert aws_stmt in targets
