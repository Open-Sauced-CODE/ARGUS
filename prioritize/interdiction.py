"""
ARGUS Phase 3 — Network-interdiction MILP solver.

Implements the shortest-path dual MILP for optimal fix prioritization:
  maximize  π_T − π_S
  s.t.      π_S = 0
            π_j − π_i ≤ -ln(p_ij) + Σ_{f covers (i,j)} Δ_f · x_f   ∀ edge (i,j)
            π_e − π_S ≤ 0                                              ∀ entry e
            π_T − π_c ≤ 0                                              ∀ crown c
            Σ_f cost_f · x_f ≤ B
            π_v ≥ 0 (continuous),  x_f ∈ {0,1}

Public API (frozen):
    build_and_solve(G, entry, crown, findings, budget, backend="auto") -> dict
    prioritize(findings, budget, G, entry_nodes=None, crown_jewels=None) -> list[str]
    prioritize_detailed(...) -> dict

SolverMismatchError is raised when the solver's objective does not match the
independent Dijkstra re-evaluation within 1e-6.

No Neo4j imports in this file.
"""

import math
import time
from pathlib import Path

import networkx as nx

from prioritize.evaluate import attack_length, residual_prob

_S = "__S__"
_T = "__T__"
_HERE = Path(__file__).resolve().parent


class SolverMismatchError(Exception):
    """Raised when solver objective ≠ independent Dijkstra re-evaluation."""


def _check_findings(G, findings):
    """Validate that all covered edges exist and no edge is covered twice."""
    seen = {}
    for f in findings:
        for cover in f["covers"]:
            u, v = cover[0], cover[1]
            if not G.has_edge(u, v):
                raise ValueError(
                    f"Finding {f['finding_id']} covers edge ({u!r}, {v!r}) "
                    f"which is not in G."
                )
            key = (u, v)
            if key in seen:
                raise ValueError(
                    f"Edge ({u!r}, {v!r}) is covered by both "
                    f"{seen[key]!r} and {f['finding_id']!r}. "
                    "Edge-disjointness required."
                )
            seen[key] = f["finding_id"]


def _highspy_available():
    """Return True if highspy can be imported (enables PuLP HiGHS solver)."""
    try:
        import highspy  # noqa: F401
        return True
    except ImportError:
        return False


def _solve_pulp(G, entry, crown, findings, budget, cover):
    """Solve with PuLP 4.0 + HiGHS solver (requires highspy).

    PuLP 4 API: variables ONLY via prob.add_variable(), not pulp.LpVariable().
    """
    import pulp

    nodes = list(G.nodes()) + [_S, _T]
    idx = {n: i for i, n in enumerate(nodes)}

    prob = pulp.LpProblem("interdiction", pulp.LpMaximize)

    # Continuous potential variables (π ≥ 0)
    pi = {n: prob.add_variable(f"pi{idx[n]}", lowBound=0) for n in nodes}

    # Binary fix variables (x ∈ {0,1})
    x = {
        f["finding_id"]: prob.add_variable(f"x{k}", cat="Binary")
        for k, f in enumerate(findings)
    }

    # Objective: maximize π_T - π_S
    prob += pi[_T] - pi[_S]

    # Pin π_S = 0
    prob += pi[_S] == 0

    # Edge constraints: π_j - π_i ≤ length + Σ Δ_f · x_f
    for u, v, d in G.edges(data=True):
        length = -math.log(float(d["p"]))
        extra = pulp.lpSum(dl * x[fid] for fid, dl in cover.get((u, v), []))
        prob += pi[v] - pi[u] <= length + extra

    # Super-source constraints: π_e - π_S ≤ 0
    for e in entry:
        prob += pi[e] - pi[_S] <= 0

    # Super-sink constraints: π_T - π_c ≤ 0
    for c in crown:
        prob += pi[_T] - pi[c] <= 0

    # Budget constraint
    prob += pulp.lpSum(f["cost"] * x[f["finding_id"]] for f in findings) <= budget

    result = prob.solve(pulp.HiGHS(msg=False))

    sel = {fid for fid, var in x.items() if (var.value() or 0.0) > 0.5}
    obj = pulp.value(prob.objective)
    return sel, obj, f"pulp+HiGHS:{result}"


def _solve_scipy(G, entry, crown, findings, budget, cover):
    """Solve with scipy.optimize.milp (HiGHS inside SciPy; no highspy needed)."""
    import numpy as np
    from scipy.optimize import milp, LinearConstraint, Bounds
    from scipy.sparse import lil_matrix

    nodes = list(G.nodes()) + [_S, _T]
    idx = {n: i for i, n in enumerate(nodes)}
    nN = len(nodes)
    nF = len(findings)
    nv = nN + nF

    # Build per-edge cover index (parallel to scipy _solve_scipy's kcover)
    kcover = {}
    for k, f in enumerate(findings):
        for cov in f["covers"]:
            u, v = cov[0], cov[1]
            kcover.setdefault((u, v), []).append((k, float(f["delta"])))

    # Number of constraints:
    # - one per graph edge
    # - one per entry node
    # - one per crown jewel
    # - one for budget
    n_edges = G.number_of_edges()
    n_entry = len(entry)
    n_crown = len(crown)
    nrows = n_edges + n_entry + n_crown + 1

    A = lil_matrix((nrows, nv))
    ub = []
    row = 0

    # Edge constraints: π_j - π_i - Σ Δ_k x_k ≤ -ln(p)
    for u, v, d in G.edges(data=True):
        A[row, idx[v]] = 1.0
        A[row, idx[u]] = -1.0
        for k, dl in kcover.get((u, v), []):
            A[row, nN + k] -= dl
        ub.append(-math.log(float(d["p"])))
        row += 1

    # Entry constraints: π_e - π_S ≤ 0
    for e in entry:
        A[row, idx[e]] = 1.0
        A[row, idx[_S]] = -1.0
        ub.append(0.0)
        row += 1

    # Crown constraints: π_T - π_c ≤ 0
    for c in crown:
        A[row, idx[_T]] = 1.0
        A[row, idx[c]] = -1.0
        ub.append(0.0)
        row += 1

    # Budget constraint: Σ cost_k x_k ≤ budget
    for k, f in enumerate(findings):
        A[row, nN + k] = float(f["cost"])
    ub.append(float(budget))

    # Objective: minimize -(π_T - π_S) → cvec[T] = -1, cvec[S] = +1
    cvec = np.zeros(nv)
    cvec[idx[_T]] = -1.0
    cvec[idx[_S]] = 1.0

    # Bounds: π_v ≥ 0, π_S ≤ 0 (pins π_S = 0 together with objective),
    #         x_k ∈ [0, 1]
    lb = np.zeros(nv)
    ub_bounds = np.full(nv, np.inf)
    ub_bounds[idx[_S]] = 0.0   # π_S pinned to 0
    ub_bounds[nN:] = 1.0       # x ≤ 1

    # Integrality: x variables are integer (1); π variables are continuous (0)
    integrality = np.zeros(nv)
    integrality[nN:] = 1.0

    res = milp(
        cvec,
        constraints=LinearConstraint(A.tocsr(), -np.inf, np.array(ub)),
        integrality=integrality,
        bounds=Bounds(lb, ub_bounds),
    )

    if res.status not in (0, 1):  # 0=optimal, 1=iteration limit (near-optimal)
        raise RuntimeError(
            f"scipy.optimize.milp returned status {res.status}: {res.message}"
        )

    sel = {findings[k]["finding_id"] for k in range(nF) if res.x[nN + k] > 0.5}
    obj = -res.fun  # we minimized the negative
    return sel, obj, f"scipy milp status={res.status}"


def build_and_solve(G, entry, crown, findings, budget, backend="auto"):
    """Build and solve the interdiction MILP.

    Parameters
    ----------
    G : nx.DiGraph
        Phase 2 attack graph (never mutated).
    entry : list
        Entry node ids.
    crown : list
        Crown-jewel node ids.
    findings : list[dict]
        Findings from enumerate_findings().
    budget : numeric
        Total budget.
    backend : str
        "pulp", "scipy", or "auto" (pulp if highspy available, else scipy).

    Returns
    -------
    dict with keys:
        selected, objective, baseline_objective, status, backend, solve_seconds
    """
    # Filter entry/crown to nodes present in G
    entry = [e for e in entry if e in G]
    crown_in_G = [c for c in crown if c in G]

    if not entry:
        raise ValueError("No valid entry nodes found in G.")

    # Validate findings
    _check_findings(G, findings)

    # Build cover map: (u, v) -> list of (finding_id, delta)
    cover = {}
    for f in findings:
        for cov in f["covers"]:
            u, v = cov[0], cov[1]
            cover.setdefault((u, v), []).append((f["finding_id"], float(f["delta"])))

    # Reachability check BEFORE calling solver (unbounded dual if no path)
    H_reach = nx.DiGraph(G)
    for e in entry:
        H_reach.add_edge(_S, e)
    for c in crown_in_G:
        H_reach.add_edge(c, _T)

    baseline_obj = attack_length(G, entry, crown, set(), findings)

    if _T not in H_reach or not nx.has_path(H_reach, _S, _T):
        return {
            "selected": set(),
            "objective": None,
            "baseline_objective": None,
            "status": "NoPath",
            "backend": "none",
            "solve_seconds": 0.0,
        }

    # Handle edge case: crown jewel == entry (objective is 0)
    crown_entry_overlap = [c for c in crown_in_G if c in set(entry)]
    if crown_entry_overlap:
        return {
            "selected": set(),
            "objective": 0.0,
            "baseline_objective": 0.0,
            "status": "CrownIsEntry",
            "backend": "none",
            "solve_seconds": 0.0,
        }

    # Budget 0: no solver needed
    if budget <= 0:
        return {
            "selected": set(),
            "objective": baseline_obj,
            "baseline_objective": baseline_obj,
            "status": "BudgetZero",
            "backend": "none",
            "solve_seconds": 0.0,
        }

    # Choose backend
    use_backend = backend
    if backend == "auto":
        use_backend = "pulp" if _highspy_available() else "scipy"

    t0 = time.time()
    try:
        if use_backend == "pulp":
            sel, obj, status_str = _solve_pulp(G, entry, crown_in_G, findings, budget, cover)
        elif use_backend == "scipy":
            sel, obj, status_str = _solve_scipy(G, entry, crown_in_G, findings, budget, cover)
        else:
            raise ValueError(f"Unknown backend: {use_backend!r}")
    except Exception as exc:
        # If pulp fails, fall back to scipy
        if use_backend == "pulp" and backend == "auto":
            t0 = time.time()
            sel, obj, status_str = _solve_scipy(G, entry, crown_in_G, findings, budget, cover)
            use_backend = "scipy (fallback)"
        else:
            raise
    solve_secs = time.time() - t0

    # Self-check: re-evaluate with independent Dijkstra
    check = attack_length(G, entry, crown, sel, findings)
    if obj is not None and abs(check - obj) > 1e-6:
        raise SolverMismatchError(
            f"Solver reported objective {obj:.8f} but independent Dijkstra "
            f"gives {check:.8f} (diff={abs(check-obj):.2e}). "
            f"Backend: {use_backend}."
        )

    # Verify budget constraint
    total_cost = sum(f["cost"] for f in findings if f["finding_id"] in sel)
    if total_cost > budget + 1e-9:
        raise SolverMismatchError(
            f"Selected set costs {total_cost} > budget {budget}."
        )

    return {
        "selected": sel,
        "objective": check,       # use the verified value
        "baseline_objective": baseline_obj,
        "status": status_str,
        "backend": use_backend,
        "solve_seconds": solve_secs,
    }


def _solo_gain(G, entry, crown, fid, findings, baseline_obj):
    """Objective with only finding fid selected, minus baseline."""
    val = attack_length(G, entry, crown, {fid}, findings)
    return val - baseline_obj


def prioritize(findings, budget, G, entry_nodes=None, crown_jewels=None):
    """Return ordered list of finding ids (frozen public API).

    Selected findings first (ordered by solo gain desc, then lower cost,
    then finding_id); unselected after (ordered by solo gain per cost desc,
    then finding_id).

    Parameters
    ----------
    findings : list[dict]
    budget : numeric
    G : nx.DiGraph
        Phase 2 attack graph.
    entry_nodes : list or None
        If None, resolved via risk.attack_graph.resolve_entry_nodes.
    crown_jewels : list or None
        If None, resolved via risk.attack_graph.get_crown_jewels.

    Returns
    -------
    list[str]
        Every finding_id exactly once, in the ordering rule order.
    """
    result = prioritize_detailed(findings, budget, G, entry_nodes, crown_jewels)
    return [f["finding_id"] for f in result["ranked"]]


def prioritize_detailed(findings, budget, G, entry_nodes=None, crown_jewels=None):
    """Return the full prioritization record (for dashboard and Phase 7).

    Returns
    -------
    dict with keys:
        budget, selected, ranked, objective, baseline_objective,
        residual_attack_prob_before, residual_attack_prob_after,
        solve_seconds, status, backend
    """
    # Lazy import of Phase 2 entry/crown resolvers so module loads without Neo4j
    if entry_nodes is None:
        from risk.attack_graph import resolve_entry_nodes
        entry_nodes = resolve_entry_nodes(G)
    if crown_jewels is None:
        from risk.attack_graph import get_crown_jewels
        crown_jewels = get_crown_jewels(G)

    entry = [e for e in entry_nodes if e in G]
    crown = [c for c in crown_jewels if c in G]

    result = build_and_solve(G, entry, crown, findings, budget)
    selected = result["selected"]
    baseline_obj = result["baseline_objective"]
    obj = result["objective"]
    status = result["status"]

    # Compute solo gains for ordering
    solo = {}
    for f in findings:
        solo[f["finding_id"]] = _solo_gain(G, entry, crown, f["finding_id"],
                                           findings, baseline_obj or 0.0)

    fid_to_cost = {f["finding_id"]: f["cost"] for f in findings}

    # Selected: sorted by solo gain desc, then lower cost, then finding_id
    sel_list = sorted(
        [f for f in findings if f["finding_id"] in selected],
        key=lambda f: (-solo[f["finding_id"]], f["cost"], f["finding_id"])
    )

    # Unselected: sorted by solo gain per cost desc, then finding_id
    unsel_list = sorted(
        [f for f in findings if f["finding_id"] not in selected],
        key=lambda f: (
            -(solo[f["finding_id"]] / f["cost"]) if f["cost"] > 0 else -math.inf,
            f["finding_id"]
        )
    )

    ranked = sel_list + unsel_list

    return {
        "budget": budget,
        "selected": sorted(selected),
        "ranked": ranked,
        "objective": obj,
        "baseline_objective": baseline_obj,
        "residual_attack_prob_before": residual_prob(baseline_obj),
        "residual_attack_prob_after": residual_prob(obj),
        "solve_seconds": result["solve_seconds"],
        "status": status,
        "backend": result["backend"],
    }
