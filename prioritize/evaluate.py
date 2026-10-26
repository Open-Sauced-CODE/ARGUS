"""
ARGUS Phase 3 — Independent evaluator and comparison utilities.

This module is the **independent checker** — it never imports PuLP.
Every length calculation uses Dijkstra on -ln(p) edge lengths so that
the MILP's answer can be verified without trusting the solver.

Public API:
    attack_length(G, entry, crown, selected_ids, findings) -> float
    residual_prob(objective) -> float
    brute_force_best(G, entry, crown, findings, budget) -> (float, list[set])
    compare_methods(G, entry, crown, findings, budget) -> dict
    budget_sweep(G, entry, crown, findings, budgets) -> list[dict]
    paths_cut_at_k(G, entry, crown, findings, selected_ids, k,
                   max_paths=2000) -> int

No Neo4j imports in this file.
"""

import itertools
import json
import math
from pathlib import Path

import networkx as nx

_S = "__S__"
_T = "__T__"
_HERE = Path(__file__).resolve().parent


def attack_length(G, entry, crown, selected_ids, findings):
    """Shortest __S__ → __T__ path length under modified edge lengths.

    Edge length = -ln(p) + sum(delta for selected findings covering that edge).
    Returns math.inf if no path exists.

    This function is the **independent evaluator** — it does not import PuLP
    or any solver.  It is used to verify solver output.

    Parameters
    ----------
    G : nx.DiGraph
        Attack graph with edge attribute ``p`` (0 < p <= 1).
    entry : list
        Entry node ids (virtual super-source connects to each present in G).
    crown : list
        Crown-jewel node ids (each present in G connects to virtual super-sink).
    selected_ids : set or list
        Finding ids that are applied.
    findings : list[dict]
        Full list of findings (only those in selected_ids matter).

    Returns
    -------
    float
        Shortest __S__ → __T__ path length, or math.inf if unreachable.
    """
    # Build per-edge additive delta from selected findings
    add = {}
    for f in findings:
        if f["finding_id"] in selected_ids:
            for cover in f["covers"]:
                u, v = cover[0], cover[1]
                add[(u, v)] = add.get((u, v), 0.0) + float(f["delta"])

    # Build a temporary graph with modified lengths
    H = nx.DiGraph()
    for u, v, d in G.edges(data=True):
        length = -math.log(float(d["p"])) + add.get((u, v), 0.0)
        H.add_edge(u, v, w=length)

    # Virtual super-source and super-sink (zero-length edges)
    for e in entry:
        if e in G:
            H.add_edge(_S, e, w=0.0)
    for c in crown:
        if c in G:
            H.add_edge(c, _T, w=0.0)

    if _S not in H or _T not in H:
        return math.inf
    if not nx.has_path(H, _S, _T):
        return math.inf
    return nx.dijkstra_path_length(H, _S, _T, weight="w")


def residual_prob(objective):
    """Convert an objective (shortest path length) to residual attack probability.

    Parameters
    ----------
    objective : float or None
        Attack length. None (NoPath) → 0.0; inf → 0.0.

    Returns
    -------
    float
        exp(-objective), floored to 0.0 for inf/None.
    """
    if objective is None or not math.isfinite(objective):
        return 0.0
    return math.exp(-objective)


def brute_force_best(G, entry, crown, findings, budget):
    """Enumerate all budget-feasible subsets and return the best objective.

    Parameters
    ----------
    G, entry, crown, findings, budget : see attack_length
    budget : numeric
        Total budget constraint.

    Returns
    -------
    (best_objective, list_of_optimal_sets)
        best_objective : float
        list_of_optimal_sets : list[set[str]]  all sets achieving the optimum

    Raises
    ------
    ValueError
        If len(findings) > 16 (too slow for brute force).
    """
    if len(findings) > 16:
        raise ValueError(
            f"brute_force_best: {len(findings)} findings > 16; too slow"
        )
    ids = [f["finding_id"] for f in findings]
    cost = {f["finding_id"]: f["cost"] for f in findings}
    best = -math.inf
    best_sets = []

    for r in range(len(ids) + 1):
        for combo in itertools.combinations(ids, r):
            if sum(cost[i] for i in combo) > budget:
                continue
            val = attack_length(G, entry, crown, set(combo), findings)
            if val > best + 1e-9:
                best = val
                best_sets = [set(combo)]
            elif abs(val - best) <= 1e-9:
                best_sets.append(set(combo))

    return best, best_sets


def paths_cut_at_k(G, entry, crown, findings, selected_ids, k=5, max_paths=2000):
    """Count how many of the top-k most probable simple paths are cut.

    A path is *cut* if it uses at least one edge covered by a selected finding.
    Enumeration is capped at max_paths to avoid blow-up on large graphs.

    Enumerates simple paths via ``nx.shortest_simple_paths`` on a super-source /
    super-sink graph with -ln(p) weights; returns count of cut paths among the
    first min(k, max_paths) enumerated.  Capped enumeration is noted in results.

    Parameters
    ----------
    G : nx.DiGraph
    entry, crown : lists of node ids
    findings : list[dict]
    selected_ids : set or list
    k : int
        How many top paths to consider.
    max_paths : int
        Hard cap on enumeration to avoid combinatorial blow-up.

    Returns
    -------
    int
        Number of paths (out of up to k) that are cut by the selected findings.
    """
    # Build covered edge set
    covered_edges = set()
    for f in findings:
        if f["finding_id"] in selected_ids:
            for cover in f["covers"]:
                covered_edges.add((cover[0], cover[1]))

    # Build the super-source/sink graph for path enumeration
    H = nx.DiGraph()
    for u, v, d in G.edges(data=True):
        H.add_edge(u, v, w=-math.log(float(d["p"])))
    for e in entry:
        if e in G:
            H.add_edge(_S, e, w=0.0)
    for c in crown:
        if c in G:
            H.add_edge(c, _T, w=0.0)

    if _S not in H or _T not in H:
        return 0
    if not nx.has_path(H, _S, _T):
        return 0

    cut = 0
    examined = 0
    try:
        for path in nx.shortest_simple_paths(H, _S, _T, weight="w"):
            examined += 1
            if examined > max_paths:
                break
            if examined > k:
                break
            # Check if path uses a covered edge
            edges_in_path = set(zip(path[:-1], path[1:]))
            # Remove virtual edges
            edges_in_path -= {(_S, e) for e in entry}
            edges_in_path -= {(c, _T) for c in crown}
            if edges_in_path & covered_edges:
                cut += 1
    except (nx.NetworkXNoPath, nx.NetworkXError):
        pass
    return cut


def compare_methods(G, entry, crown, findings, budget):
    """Run naive, stackelberg_rounded, and interdiction; return comparison dict.

    Parameters
    ----------
    G : nx.DiGraph
    entry : list
    crown : list
    findings : list[dict]
    budget : int or float

    Returns
    -------
    dict
        Matches the comparison.json frozen shape (Section 6.4 of the prompt).
    """
    from prioritize.interdiction import build_and_solve
    from prioritize.naive import naive_select
    from prioritize.stackelberg_baseline import solve_stackelberg, round_to_binary
    from prioritize import findings as _findings_mod
    from risk.pagerank import score_digraph, to_percent
    from risk.simulate import apply_delta

    cfg = _findings_mod.load_config()
    k = cfg.get("critical_paths_k", 5)
    max_paths = cfg.get("max_paths_enumerated", 2000)

    entry = [e for e in entry if e in G]
    crown_present = [c for c in crown if c in G]

    baseline_obj = attack_length(G, entry, crown, set(), findings)

    # --- PPR for naive baseline ---
    try:
        ppr = score_digraph(G, entry)
        ppr_pct = to_percent(ppr)
    except Exception:
        ppr = {}
        ppr_pct = {}

    def _ppr_delta(selected):
        """Change in PPR score per crown jewel after applying selected fixes."""
        delta = {}
        ops = []
        for f in findings:
            if f["finding_id"] in selected and f.get("simulated"):
                if f["fix_op"] == "restrict_cidr":
                    ops.append({"op": f["fix_op"], "target": f["target"], "factor": 0.1})
                else:
                    ops.append({"op": f["fix_op"], "target": f["target"]})
        if not ops:
            return {c: 0.0 for c in crown_present}
        G2 = apply_delta(G, {"ops": ops})
        try:
            ppr2 = score_digraph(G2, entry)
        except Exception:
            return {c: None for c in crown_present}
        for c in crown_present:
            before = ppr.get(c, 0.0)
            after = ppr2.get(c, 0.0)
            delta[c] = after - before
        return delta

    methods = []

    # --- Naive ---
    naive_result = naive_select(G, entry, findings, budget, ppr=ppr)
    naive_sel = set(naive_result["selected"])
    naive_obj = attack_length(G, entry, crown, naive_sel, findings)
    methods.append({
        "name": "naive",
        "selected": sorted(naive_sel),
        "objective": naive_obj,
        "residual_attack_prob": residual_prob(naive_obj),
        "ppr_crown_jewel_delta": _ppr_delta(naive_sel),
        "paths_cut_at_k": paths_cut_at_k(G, entry, crown, findings, naive_sel,
                                          k=k, max_paths=max_paths),
    })

    # --- Stackelberg (rounded) ---
    ra = {f["finding_id"]: ppr_pct.get(f["target"], 0.0) for f in findings}
    pa_ratio = cfg.get("stackelberg", {}).get("pa_ratio", 0.2)
    try:
        ssg = solve_stackelberg(findings, ra, budget, pa_ratio=pa_ratio)
        if ssg:
            ssg_rounded = round_to_binary(ssg["x"], findings, budget)
            ssg_sel = set(ssg_rounded["selected"])
            ssg_frac = ssg["x"]
        else:
            ssg_sel = set()
            ssg_frac = {}
    except Exception:
        ssg_sel = set()
        ssg_frac = {}
    ssg_obj = attack_length(G, entry, crown, ssg_sel, findings)
    methods.append({
        "name": "stackelberg_rounded",
        "fractional_x": {k2: v for k2, v in ssg_frac.items()},
        "selected": sorted(ssg_sel),
        "objective": ssg_obj,
        "residual_attack_prob": residual_prob(ssg_obj),
        "ppr_crown_jewel_delta": _ppr_delta(ssg_sel),
        "paths_cut_at_k": paths_cut_at_k(G, entry, crown, findings, ssg_sel,
                                          k=k, max_paths=max_paths),
        "note": "comparison only; fractional coverage has no operational meaning",
    })

    # --- Interdiction ---
    interd = build_and_solve(G, entry, crown, findings, budget)
    interd_sel = interd.get("selected", set())
    interd_obj = interd.get("objective") or attack_length(G, entry, crown, interd_sel, findings)
    methods.append({
        "name": "interdiction",
        "selected": sorted(interd_sel),
        "objective": interd_obj,
        "residual_attack_prob": residual_prob(interd_obj),
        "ppr_crown_jewel_delta": _ppr_delta(interd_sel),
        "paths_cut_at_k": paths_cut_at_k(G, entry, crown, findings, interd_sel,
                                          k=k, max_paths=max_paths),
    })

    # --- Budget sweep ---
    sweep = budget_sweep(G, entry, crown, findings, list(range(min(7, budget + 4))))

    return {
        "budget": budget,
        "entry_count": len(entry),
        "crown_jewel_count": len(crown_present),
        "methods": methods,
        "budget_sweep": sweep,
    }


def budget_sweep(G, entry, crown, findings, budgets):
    """Run naive and interdiction over a range of budgets.

    Parameters
    ----------
    G, entry, crown, findings : see attack_length
    budgets : list[int]
        Budget values to sweep.

    Returns
    -------
    list[dict]
        One dict per budget with keys: budget, naive_objective,
        naive_residual, interdiction_objective, interdiction_residual.
    """
    from prioritize.interdiction import build_and_solve
    from prioritize.naive import naive_select
    from risk.pagerank import score_digraph, to_percent

    entry = [e for e in entry if e in G]

    try:
        ppr = score_digraph(G, entry)
    except Exception:
        ppr = {}

    results = []
    for b in budgets:
        naive_result = naive_select(G, entry, findings, b, ppr=ppr)
        naive_sel = set(naive_result["selected"])
        naive_obj = attack_length(G, entry, crown, naive_sel, findings)

        interd = build_and_solve(G, entry, crown, findings, b)
        interd_sel = interd.get("selected", set())
        interd_obj = (interd.get("objective")
                      if interd.get("objective") is not None
                      else attack_length(G, entry, crown, interd_sel, findings))

        results.append({
            "budget": b,
            "naive_objective": naive_obj,
            "naive_residual": residual_prob(naive_obj),
            "interdiction_objective": interd_obj,
            "interdiction_residual": residual_prob(interd_obj),
        })
    return results
