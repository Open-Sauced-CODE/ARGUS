"""
Graph fixtures for Phase 3 tests.

All graphs use raw networkx only.  Every node has ``kind`` and ``label``.
Every edge has ``p`` (0 < p <= 1) and ``etype`` (str).

No imports from prioritize.* in this file — fixtures must be importable
without the full package installed.

Exports:
    toy_graph()           -- Phase 2-style toy graph (5-node + bucket)
    parallel_paths()      -- Exercise 3 graph (documented differing case)
    exercise1()           -- Exercise 1 hand-check graph
    random_graph(seed, n_nodes, n_edges, n_fixes)
    multi_crown_graph(seed)  -- graph with 2 entries and 2 crown jewels
"""

import math
import random

import networkx as nx

DELTA_MAX = -math.log(1e-6)  # 13.8155...


# ---------------------------------------------------------------------------
# toy_graph — mirrors the Phase 2 canonical shape for testing findings.py
# ---------------------------------------------------------------------------

def toy_graph():
    """Small Phase 2-style attack graph with known findings.

    Nodes:
        S   (key)   INTERNET-style entry via key
        U   (user)
        POL (policy)
        STM (stmt)   → ADMIN_EQUIV (CAN_ESCALATE) and BUCKET (CAN_ACCESS)
        ADMIN_EQUIV  (admin)
        BUCKET       (bucket, personal_data=True)

    Expected findings from enumerate_findings (simulated only):
        One remove_policy_statement covering both STM out-edges.
    """
    G = nx.DiGraph()
    G.add_node("S",           kind="key",    label="test-key")
    G.add_node("U",           kind="user",   label="test-user")
    G.add_node("POL",         kind="policy", label="test-policy")
    G.add_node("STM",         kind="stmt",   label="TestStmt")
    G.add_node("ADMIN_EQUIV", kind="admin",  label="ADMIN_EQUIV")
    G.add_node("BUCKET",      kind="bucket", label="test-bucket",
               personal_data=True)

    G.add_edge("S",   "U",           p=0.9,  etype="USES_KEY")
    G.add_edge("U",   "POL",         p=1.0,  etype="HAS_POLICY")
    G.add_edge("POL", "STM",         p=1.0,  etype="HAS_STATEMENT")
    G.add_edge("STM", "ADMIN_EQUIV", p=0.85, etype="CAN_ESCALATE")
    G.add_edge("STM", "BUCKET",      p=0.8,  etype="CAN_ACCESS")
    return G


# ---------------------------------------------------------------------------
# parallel_paths — Exercise 3 (the documented differing case)
# ---------------------------------------------------------------------------

def parallel_paths():
    """Exercise 3 graph with two parallel routes to crown jewel T.

    Path A:  S0 →(p=0.9) A1 →(p=0.9) A2 →(p=0.9) T0
    Path B:  S0 →(p=0.5) B1 →(p=0.5) T0

    Budget = 2, all fix costs = 1, delta = DELTA_MAX (edge removed):
      Naive picks α and β (both on Path A) → Path B stays open.
      Interdiction picks α and γ (one per path) → both paths blocked.

    Returns (G, entry, crown, findings):
        entry  = ["S0"]
        crown  = ["T0"]
        findings = [alpha, beta, gamma]
    """
    G = nx.DiGraph()
    G.add_node("S0", kind="internet", label="S0")
    G.add_node("A1", kind="user",     label="A1")
    G.add_node("A2", kind="user",     label="A2")
    G.add_node("B1", kind="user",     label="B1")
    G.add_node("T0", kind="admin",    label="T0")

    G.add_edge("S0", "A1", p=0.9, etype="USES_KEY")
    G.add_edge("A1", "A2", p=0.9, etype="CAN_ASSUME")
    G.add_edge("A2", "T0", p=0.9, etype="CAN_ESCALATE")
    G.add_edge("S0", "B1", p=0.5, etype="USES_KEY")
    G.add_edge("B1", "T0", p=0.5, etype="CAN_ESCALATE")

    findings = [
        {
            "finding_id": "F-alpha",
            "fix_op": "remove_policy_statement",
            "target": "S0",   # conceptual — covers edge S0->A1
            "target_label": "alpha",
            "covers": [["S0", "A1", "USES_KEY"]],
            "delta": DELTA_MAX,
            "cost": 1,
            "rule_family": "iam_privilege_escalation",
            "rule_ids": [],
            "rule_gap": True,
            "simulated": True,
        },
        {
            "finding_id": "F-beta",
            "fix_op": "remove_policy_statement",
            "target": "A1",
            "target_label": "beta",
            "covers": [["A1", "A2", "CAN_ASSUME"]],
            "delta": DELTA_MAX,
            "cost": 1,
            "rule_family": "iam_privilege_escalation",
            "rule_ids": [],
            "rule_gap": True,
            "simulated": True,
        },
        {
            "finding_id": "F-gamma",
            "fix_op": "remove_policy_statement",
            "target": "S0_B",
            "target_label": "gamma",
            "covers": [["S0", "B1", "USES_KEY"]],
            "delta": DELTA_MAX,
            "cost": 1,
            "rule_family": "iam_privilege_escalation",
            "rule_ids": [],
            "rule_gap": True,
            "simulated": True,
        },
    ]

    return G, ["S0"], ["T0"], findings


# ---------------------------------------------------------------------------
# exercise1 — from the spec B1 / Section 4 hand checks
# ---------------------------------------------------------------------------

def exercise1():
    """Exercise 1 hand-check graph.

    s →(d=1) a →(d=1) t     i.e. p=e^{-1} ≈ 0.3679
    s →(d=3)           t    i.e. p=e^{-3} ≈ 0.0498

    Budget 0 → objective 2.0 (via s-a-t)
    Budget 1 (fix s→a, delta 5) → objective 3.0 (attacker switches to s→t)
    Budget 2 (fix s→a and s→t, delta 5 each) → objective 7.0

    Returns (G, entry, crown, findings):
        entry  = ["s"]
        crown  = ["t"]
        findings = [fix_sa, fix_st]
    """
    p_1 = math.exp(-1.0)   # d=1
    p_3 = math.exp(-3.0)   # d=3

    G = nx.DiGraph()
    G.add_node("s", kind="internet", label="s")
    G.add_node("a", kind="user",     label="a")
    G.add_node("t", kind="admin",    label="t")

    G.add_edge("s", "a", p=p_1, etype="CAN_ASSUME")
    G.add_edge("a", "t", p=p_1, etype="CAN_ESCALATE")
    G.add_edge("s", "t", p=p_3, etype="CAN_ESCALATE")

    findings = [
        {
            "finding_id": "F-sa",
            "fix_op": "remove_policy_statement",
            "target": "sa",
            "target_label": "fix s->a",
            "covers": [["s", "a", "CAN_ASSUME"]],
            "delta": 5.0,
            "cost": 1,
            "rule_family": "iam_privilege_escalation",
            "rule_ids": [],
            "rule_gap": True,
            "simulated": True,
        },
        {
            "finding_id": "F-st",
            "fix_op": "remove_policy_statement",
            "target": "st",
            "target_label": "fix s->t",
            "covers": [["s", "t", "CAN_ESCALATE"]],
            "delta": 5.0,
            "cost": 1,
            "rule_family": "iam_privilege_escalation",
            "rule_ids": [],
            "rule_gap": True,
            "simulated": True,
        },
    ]

    return G, ["s"], ["t"], findings


# ---------------------------------------------------------------------------
# random_graph — reproducible random DAG for brute-force cross-check
# ---------------------------------------------------------------------------

def random_graph(seed, n_nodes=9, n_edges=16, n_fixes=8):
    """Reproducible random DAG for brute-force testing.

    Parameters
    ----------
    seed : int
    n_nodes : int
    n_edges : int
        Approximate number of edges (may be less due to DAG constraints).
    n_fixes : int
        Number of fix-findings (each covering a distinct edge).

    Returns
    -------
    (G, entry, crown, findings)
        entry  = [node 0]
        crown  = [node n_nodes-1]
        findings = list[dict], sorted by finding_id

    Notes
    -----
    - p ∈ [0.2, 0.95]
    - costs ∈ {1, 2, 3}
    - deltas ∈ {2.3026, DELTA_MAX}
    - Edges are iterated in sorted order for cross-Python determinism.
    - Findings cover distinct edges; no edge covered twice.
    """
    rng = random.Random(seed)

    G = nx.DiGraph()
    # Add nodes 0..n_nodes-1
    for i in range(n_nodes):
        G.add_node(i, kind="user", label=f"node{i}")
    # Override first/last kind
    G.nodes[0]["kind"] = "internet"
    G.nodes[n_nodes - 1]["kind"] = "admin"

    # Add edges from lower to higher index (DAG)
    candidate_edges = [(i, j) for i in range(n_nodes) for j in range(i+1, n_nodes)]
    rng.shuffle(candidate_edges)
    added = []
    for (u, v) in candidate_edges:
        if len(added) >= n_edges:
            break
        p = round(rng.uniform(0.2, 0.95), 4)
        etype = rng.choice(["CAN_ASSUME", "CAN_ESCALATE", "HAS_POLICY",
                             "USES_KEY", "CAN_ACCESS"])
        G.add_edge(u, v, p=p, etype=etype)
        added.append((u, v))

    # Ensure entry can reach crown (add a direct edge if needed)
    entry = [0]
    crown = [n_nodes - 1]
    if not nx.has_path(G, 0, n_nodes - 1):
        G.add_edge(0, n_nodes - 1, p=0.5, etype="CAN_ESCALATE")
        added.append((0, n_nodes - 1))

    # Build findings covering distinct edges (sorted iteration for determinism)
    sorted_edges = sorted(added)
    rng.shuffle(sorted_edges)  # re-shuffle to get a random n_fixes subset
    chosen_edges = sorted_edges[:min(n_fixes, len(sorted_edges))]
    chosen_edges.sort()  # sort again for determinism

    findings = []
    for u, v in chosen_edges:
        if not G.has_edge(u, v):
            continue
        etype = G[u][v]["etype"]
        delta = rng.choice([2.3026, DELTA_MAX])
        cost = rng.choice([1, 2, 3])
        fid_str = f"remove_policy_statement|{u}|{v}"
        import hashlib
        fid = "F-" + hashlib.sha1(fid_str.encode()).hexdigest()[:8]
        findings.append({
            "finding_id": fid,
            "fix_op": "remove_policy_statement",
            "target": f"{u}_{v}",
            "target_label": f"fix {u}->{v}",
            "covers": [[u, v, etype]],
            "delta": delta,
            "cost": cost,
            "rule_family": "iam_privilege_escalation",
            "rule_ids": [],
            "rule_gap": True,
            "simulated": True,
        })
    findings.sort(key=lambda f: f["finding_id"])
    # Deduplicate finding_ids (edge case: sha1 collision)
    seen_fids = set()
    unique_findings = []
    for f in findings:
        if f["finding_id"] not in seen_fids:
            unique_findings.append(f)
            seen_fids.add(f["finding_id"])
    return G, entry, crown, unique_findings


# ---------------------------------------------------------------------------
# multi_crown_graph — two entries, two crown jewels
# ---------------------------------------------------------------------------

def multi_crown_graph(seed=42):
    """Graph with two entries (E1, E2) and two crown jewels (C1, C2).

    Used to test the super-source/super-sink formulation with multiple
    entries and crowns.

    Returns (G, entry, crown, findings)
    """
    rng = random.Random(seed)

    G = nx.DiGraph()
    nodes = ["E1", "E2", "M1", "M2", "M3", "C1", "C2"]
    kinds = {"E1": "internet", "E2": "key", "C1": "admin", "C2": "bucket",
             "M1": "user", "M2": "role", "M3": "stmt"}
    for n in nodes:
        G.add_node(n, kind=kinds[n], label=n)

    edges = [
        ("E1", "M1", 0.8, "USES_KEY"),
        ("E2", "M1", 0.7, "USES_KEY"),
        ("M1", "M2", 0.6, "CAN_ASSUME"),
        ("M2", "M3", 1.0, "HAS_POLICY"),
        ("M3", "C1", 0.9, "CAN_ESCALATE"),
        ("M3", "C2", 0.8, "CAN_ACCESS"),
        ("E1", "M3", 0.5, "HAS_POLICY"),
    ]
    for u, v, p, etype in edges:
        G.add_edge(u, v, p=p, etype=etype)

    findings = [
        {
            "finding_id": "F-mc1",
            "fix_op": "remove_policy_statement",
            "target": "M3",
            "target_label": "M3",
            "covers": [["M3", "C1", "CAN_ESCALATE"], ["M3", "C2", "CAN_ACCESS"]],
            "delta": DELTA_MAX,
            "cost": 2,
            "rule_family": "iam_privilege_escalation",
            "rule_ids": [],
            "rule_gap": True,
            "simulated": True,
        },
        {
            "finding_id": "F-mc2",
            "fix_op": "remove_policy_statement",
            "target": "E1M3",
            "target_label": "E1->M3",
            "covers": [["E1", "M3", "HAS_POLICY"]],
            "delta": DELTA_MAX,
            "cost": 1,
            "rule_family": "iam_privilege_escalation",
            "rule_ids": [],
            "rule_gap": True,
            "simulated": True,
        },
    ]

    return G, ["E1", "E2"], ["C1", "C2"], findings
