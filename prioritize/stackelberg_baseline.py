"""
ARGUS Phase 3 — Stackelberg security-game baseline.

COMPARISON BASELINE ONLY — NOT FOR PRODUCTION.
The fractional coverage x_i ∈ [0,1] has no operational meaning for patching
(you cannot patch a system "68%").  This baseline is kept as an honest foil
to show that the Stackelberg model (designed for randomised inspection
schedules) gives worse results than the interdiction MILP for patching.

Theory (zero-sum Stackelberg security game):
  - Each finding i is a "target" the attacker can attack.
  - x_i ∈ [0,1]: defender's mixed coverage of finding i.
  - Attacker's payoff (uncovered): Ra_i = ppr_percent[target_i]
    Attacker's payoff (covered):   Pa_i = -pa_ratio * Ra_i
  - Defender's payoffs (zero-sum): Rd_i = -Pa_i, Pd_i = -Ra_i
  - Attacker utility: Ua(i) = (1 - x_i) * Ra_i + x_i * Pa_i
  - Multiple-LP method: for each candidate attacker target i*,
    solve:   maximize   x_{i*} * Rd_{i*} + (1 - x_{i*}) * Pd_{i*}
             subject to Ua(i*) >= Ua(i)  for all i
                        0 <= x <= 1
                        Σ cost_i * x_i <= budget
    skip infeasible; keep the x with the best defender utility at i*.

Public API:
    solve_stackelberg(findings, ra, budget, pa_ratio=0.2) -> dict or None
    round_to_binary(x, findings, budget) -> dict
"""

import math

from scipy.optimize import linprog


def solve_stackelberg(findings, ra, budget, pa_ratio=0.2):
    """Solve the Stackelberg multiple-LP problem.

    Parameters
    ----------
    findings : list[dict]
        Findings.  finding_id, cost.
    ra : dict
        {finding_id: Ra_i} — attacker's payoff when uncovered.
        Typically ppr_percent[target].
    budget : numeric
    pa_ratio : float
        Ratio for attacker's covered payoff: Pa_i = -pa_ratio * Ra_i.
        Default 0.2 from config.json.

    Returns
    -------
    dict or None
        {'x': {finding_id: float}, 'best_target': finding_id, 'value': float}
        or None if no LP is feasible.
    """
    ids = [f["finding_id"] for f in findings]
    if not ids:
        return None

    Ra = {i: float(ra.get(i, 0.0)) for i in ids}
    Pa = {i: -pa_ratio * Ra[i] for i in ids}
    Rd = {i: -Pa[i] for i in ids}     # defender payoff when covered
    Pd = {i: -Ra[i] for i in ids}     # defender payoff when uncovered
    cost = {f["finding_id"]: float(f["cost"]) for f in findings}
    n = len(ids)
    id_idx = {fid: j for j, fid in enumerate(ids)}

    best = None

    for ts_idx, ts in enumerate(ids):
        # Variables: x_0 .. x_{n-1}
        # Objective (for maximization → linprog needs negation):
        #   maximize x_ts * Rd[ts] + (1 - x_ts) * Pd[ts]
        #          = x_ts * (Rd[ts] - Pd[ts]) + Pd[ts]
        # → minimize -x_ts * (Rd[ts] - Pd[ts])
        c_obj = [0.0] * n
        c_obj[ts_idx] = -(Rd[ts] - Pd[ts])

        # Inequality constraints Ax <= b (linprog convention)
        # We need:  Ua(ts) >= Ua(i) for all i != ts
        # i.e.      Ua(i) - Ua(ts) <= 0
        # Ua(i) = (1 - x_i) * Ra[i] + x_i * Pa[i] = Ra[i] + x_i * (Pa[i] - Ra[i])
        A_ub = []
        b_ub = []

        for i in ids:
            if i == ts:
                continue
            # Ua(i) - Ua(ts) <= 0
            # [Ra[i] + x_i*(Pa[i]-Ra[i])] - [Ra[ts] + x_ts*(Pa[ts]-Ra[ts])] <= 0
            row = [0.0] * n
            row[id_idx[i]] = Pa[i] - Ra[i]
            row[ts_idx] += -(Pa[ts] - Ra[ts])
            rhs = Ra[ts] - Ra[i]
            A_ub.append(row)
            b_ub.append(rhs)

        # Budget constraint: Σ cost_i * x_i <= budget
        budget_row = [cost[i] for i in ids]
        A_ub.append(budget_row)
        b_ub.append(float(budget))

        # Bounds: 0 <= x_i <= 1
        bounds = [(0.0, 1.0)] * n

        res = linprog(c_obj, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method="highs")

        if res.status != 0:
            continue  # infeasible or unbounded for this attacker target

        val = -res.fun + Pd[ts]   # restore constant term
        x_vals = {ids[j]: float(res.x[j]) for j in range(n)}

        if best is None or val > best["value"]:
            best = {
                "value": val,
                "best_target": ts,
                "x": x_vals,
            }

    return best


def round_to_binary(x, findings, budget):
    """Round fractional Stackelberg coverage to a binary set.

    Same greedy rule as naive: sort by x_i descending (ties: lower cost, then
    finding_id), take each finding that fits in remaining budget.

    Parameters
    ----------
    x : dict
        {finding_id: float} fractional coverage.
    findings : list[dict]
    budget : numeric

    Returns
    -------
    dict with keys:
        selected : list[str]
        ordered  : list[dict]
    """
    ordered = sorted(
        findings,
        key=lambda f: (-(x.get(f["finding_id"], 0.0)), f["cost"], f["finding_id"])
    )
    selected = []
    remaining = float(budget)
    for f in ordered:
        if f["cost"] <= remaining + 1e-9:
            selected.append(f["finding_id"])
            remaining -= f["cost"]

    return {"selected": selected, "ordered": ordered}
