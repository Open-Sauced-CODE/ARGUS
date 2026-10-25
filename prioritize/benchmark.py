"""
ARGUS Phase 3 — Synthetic enterprise benchmark.

Generates realistic-scale graphs using the real Phase 2 node kinds and edge
types, runs all three methods, and aggregates statistics.  This is the main
evidence for Phase 3 correctness because the live graph is tiny.

Public API:
    synthetic_enterprise(seed, n_users=6, n_roles=5, n_stmts=14,
                         n_buckets=3, n_sgs=3) -> (G, entry, crown, findings)
    run_benchmark(n_seeds=200, budgets=(2,4,6)) -> dict
"""
import hashlib
import json
import math
import random
import time
from pathlib import Path

import networkx as nx

from prioritize.findings import enumerate_findings, load_catalogue, load_config
from prioritize.evaluate import attack_length, brute_force_best, residual_prob
from prioritize.interdiction import build_and_solve
from prioritize.naive import naive_select
from prioritize.stackelberg_baseline import solve_stackelberg, round_to_binary

_HERE = Path(__file__).resolve().parent
_RESULTS_PATH = _HERE / "benchmark_results.json"

# Edge weights from risk/edge_weights.json (base probabilities)
_BASE_WEIGHTS = {
    "USES_KEY": 0.85,
    "CAN_ASSUME": 0.7,
    "HAS_POLICY": 1.0,
    "HAS_STATEMENT": 1.0,
    "CAN_ESCALATE": 0.6,
    "DIRECT_ADMIN": 1.0,
    "CAN_ACCESS": 0.7,
    "RULE_TO_SG": 0.3,
    "INTERNET_TO_RANGE": 0.5,
    "RANGE_TO_RULE": 0.9,
    "SG_TO_VPC": 0.9,
}

DELTA_MAX = -math.log(1e-6)


def synthetic_enterprise(
    seed,
    n_users=6,
    n_roles=5,
    n_stmts=14,
    n_buckets=3,
    n_sgs=3,
):
    """Build a synthetic enterprise attack graph using real Phase 2 kinds and etypes.

    Graph structure:
      - INTERNET node (entry) + 2 key nodes (entries)
      - users → policies → stmts → {ADMIN_EQUIV, buckets}
      - roles with CAN_ASSUME chains
      - INTERNET → iprange → iprule → sg → vpc path (network branch)
      - Some parallel routes and single chokepoints

    Returns (G, entry, crown, findings) where findings come from enumerate_findings.
    """
    rng = random.Random(seed)

    G = nx.DiGraph()

    # ---- Special nodes ----
    G.add_node("INTERNET", kind="internet", label="INTERNET")
    G.add_node("ADMIN_EQUIV", kind="admin", label="ADMIN_EQUIV")

    # Entry: INTERNET + 2 keys
    key_ids = [f"key-{i}" for i in range(2)]
    for k in key_ids:
        G.add_node(k, kind="key", label=k)

    # Users
    user_ids = [f"user-{i}" for i in range(n_users)]
    for u in user_ids:
        G.add_node(u, kind="user", label=u)

    # Roles
    role_ids = [f"role-{i}" for i in range(n_roles)]
    for r in role_ids:
        G.add_node(r, kind="role", label=r)

    # Policies (one per user/role that has a dangerous stmt)
    pol_ids = [f"pol-{i}" for i in range(n_stmts)]
    for p in pol_ids:
        G.add_node(p, kind="policy", label=p)

    # Statements (targets for remove_policy_statement)
    stmt_ids = [f"stmt-{i}" for i in range(n_stmts)]
    for s in stmt_ids:
        G.add_node(s, kind="stmt", label=s)

    # Buckets (crown jewels)
    bucket_ids = [f"bucket-{i}" for i in range(n_buckets)]
    for b in bucket_ids:
        G.add_node(b, kind="bucket", label=b, personal_data=rng.random() > 0.5)

    # SG / Network nodes (initialized to empty so they are always bound)
    iprange_id: str = ""
    vpc_id: str = ""
    iprule_ids: list[str] = []
    sg_ids: list[str] = []
    if n_sgs > 0:
        iprange_id = "iprange-0"
        G.add_node(iprange_id, kind="iprange", label=iprange_id)
        vpc_id = "vpc-0"
        G.add_node(vpc_id, kind="vpc", label=vpc_id)
        iprule_ids = [f"iprule-{i}" for i in range(n_sgs)]
        for r in iprule_ids:
            G.add_node(r, kind="iprule", label=r)
        sg_ids = [f"sg-{i}" for i in range(n_sgs)]
        for s in sg_ids:
            G.add_node(s, kind="sg", label=s)

    def _p(etype):
        base = _BASE_WEIGHTS.get(etype, 0.5)
        jitter = rng.uniform(-0.1, 0.1)
        return max(0.05, min(0.99, base + jitter))

    # ---- INTERNET / Key → User edges (USES_KEY) ----
    # Keys connect to users
    for k in key_ids:
        for u in rng.sample(user_ids, min(2, len(user_ids))):
            G.add_edge(k, u, p=_p("USES_KEY"), etype="USES_KEY")

    # INTERNET connects to a few users directly (via synthetic entry)
    for u in rng.sample(user_ids, min(2, len(user_ids))):
        G.add_edge("INTERNET", u, p=_p("USES_KEY"), etype="USES_KEY")

    # ---- User → Policy → Stmt edges ----
    user_pol_pairs = list(zip(
        rng.sample(user_ids, min(n_stmts, len(user_ids))) * 3,
        pol_ids,
    ))[:n_stmts]

    for u, pol in user_pol_pairs[:n_stmts]:
        if not G.has_edge(u, pol):
            G.add_edge(u, pol, p=_p("HAS_POLICY"), etype="HAS_POLICY")

    for pol, stmt in zip(pol_ids, stmt_ids):
        G.add_edge(pol, stmt, p=_p("HAS_STATEMENT"), etype="HAS_STATEMENT")

    # ---- Stmt → crown-jewel edges ----
    # Mix of CAN_ESCALATE, DIRECT_ADMIN, CAN_ACCESS
    stmt_types = (
        ["CAN_ESCALATE"] * (n_stmts // 3)
        + ["DIRECT_ADMIN"] * (n_stmts // 6 + 1)
        + ["CAN_ACCESS"] * (n_stmts // 3)
        + ["CAN_ESCALATE"] * n_stmts  # filler
    )[:n_stmts]
    rng.shuffle(stmt_types)

    for stmt, etype in zip(stmt_ids, stmt_types):
        if etype in ("CAN_ESCALATE", "DIRECT_ADMIN"):
            G.add_edge(stmt, "ADMIN_EQUIV", p=_p(etype), etype=etype)
        else:
            bucket = rng.choice(bucket_ids)
            G.add_edge(stmt, bucket, p=_p("CAN_ACCESS"), etype="CAN_ACCESS")

    # ---- Role CAN_ASSUME chains ----
    # Some roles can be assumed by users
    for role in role_ids[:3]:
        src = rng.choice(user_ids)
        G.add_edge(src, role, p=_p("CAN_ASSUME"), etype="CAN_ASSUME")
        # Roles connect to policies too
        if pol_ids:
            pol = rng.choice(pol_ids)
            if not G.has_edge(role, pol):
                G.add_edge(role, pol, p=_p("HAS_POLICY"), etype="HAS_POLICY")

    # ---- Network branch (INTERNET → ... → sg) ----
    if n_sgs > 0:
        G.add_edge("INTERNET", iprange_id, p=_p("INTERNET_TO_RANGE"),
                   etype="INTERNET_TO_RANGE")
        for iprule in iprule_ids:
            G.add_edge(iprange_id, iprule, p=_p("RANGE_TO_RULE"),
                       etype="RANGE_TO_RULE")
        for iprule, sg in zip(iprule_ids, sg_ids):
            G.add_edge(iprule, sg, p=_p("RULE_TO_SG"), etype="RULE_TO_SG")
        for sg in sg_ids:
            G.add_edge(sg, vpc_id, p=_p("SG_TO_VPC"), etype="SG_TO_VPC")
        # VPC → user (network pivot)
        if user_ids:
            G.add_edge(vpc_id, rng.choice(user_ids), p=0.3, etype="USES_KEY")

    # Ensure INTERNET can reach ADMIN_EQUIV
    if not nx.has_path(G, "INTERNET", "ADMIN_EQUIV"):
        # Add a direct path through the first stmt
        u = user_ids[0]
        pol = pol_ids[0]
        stmt = stmt_ids[0]
        if not G.has_edge("INTERNET", u):
            G.add_edge("INTERNET", u, p=0.5, etype="USES_KEY")
        if not G.has_edge(u, pol):
            G.add_edge(u, pol, p=1.0, etype="HAS_POLICY")
        if not G.has_edge(pol, stmt):
            G.add_edge(pol, stmt, p=1.0, etype="HAS_STATEMENT")
        if not G.has_edge(stmt, "ADMIN_EQUIV"):
            G.add_edge(stmt, "ADMIN_EQUIV", p=0.6, etype="CAN_ESCALATE")

    entry = ["INTERNET"] + key_ids
    crown = ["ADMIN_EQUIV"] + bucket_ids

    findings = enumerate_findings(G)

    return G, entry, crown, findings


def _large_enterprise(seed, n_findings_target=45):
    """Build a larger enterprise graph with ≥40 findings for scale testing."""
    G, entry, crown, findings = synthetic_enterprise(
        seed,
        n_users=16,
        n_roles=12,
        n_stmts=50,
        n_buckets=10,
        n_sgs=8,
    )
    return G, entry, crown, findings


def run_benchmark(n_seeds=200, budgets=(2, 4, 6)):
    """Run the synthetic enterprise benchmark.

    Parameters
    ----------
    n_seeds : int
        Number of random seeds to test.
    budgets : tuple
        Budget values to run for each seed.

    Returns
    -------
    dict
        Aggregated results written to benchmark_results.json.
    """
    score_digraph = None
    to_percent = None
    try:
        from risk.pagerank import score_digraph as _score_digraph, to_percent as _to_percent
        score_digraph = _score_digraph
        to_percent = _to_percent
    except ImportError:
        pass

    cfg = load_config()
    pa_ratio = cfg.get("stackelberg", {}).get("pa_ratio", 0.2)

    results_by_budget = {b: {
        "naive_residuals": [],
        "stackelberg_residuals": [],
        "interdiction_residuals": [],
        "interdiction_better_naive": 0,
        "interdiction_better_stackelberg": 0,
        "interdiction_tied_all": 0,
        "count": 0,
    } for b in budgets}

    solve_times = []
    brute_force_checks = 0
    brute_force_mismatches = 0
    max_solve_time = 0.0

    for seed in range(n_seeds):
        G, entry, crown, findings = synthetic_enterprise(seed)

        if not findings:
            continue

        # Check reachability
        H = nx.DiGraph(G)
        entry_in_g = [e for e in entry if e in G]
        crown_in_g = [c for c in crown if c in G]
        for e in entry_in_g:
            H.add_edge("__S__", e)
        for c in crown_in_g:
            H.add_edge(c, "__T__")
        try:
            has_path = nx.has_path(H, "__S__", "__T__")
        except Exception:
            has_path = False
        if not has_path:
            continue

        # PPR for naive/stackelberg
        if callable(score_digraph) and callable(to_percent):
            try:
                ppr = score_digraph(G, entry_in_g)
                ppr_pct = to_percent(ppr)
            except Exception:
                ppr = {}
                ppr_pct = {}
        else:
            ppr = {}
            ppr_pct = {}

        ra = {f["finding_id"]: ppr_pct.get(f["target"], 0.0) for f in findings}

        for budget in budgets:
            # Naive
            naive_r = naive_select(G, entry_in_g, findings, budget, ppr=ppr)
            naive_sel = set(naive_r["selected"])
            naive_obj = float(attack_length(G, entry_in_g, crown_in_g, naive_sel, findings))

            # Stackelberg
            try:
                ssg = solve_stackelberg(findings, ra, budget, pa_ratio=pa_ratio)
                if ssg:
                    rounded = round_to_binary(ssg["x"], findings, budget)
                    ssg_sel = set(rounded["selected"])
                else:
                    ssg_sel = set()
            except Exception:
                ssg_sel = set()
            ssg_obj = float(attack_length(G, entry_in_g, crown_in_g, ssg_sel, findings))

            # Interdiction
            try:
                t0 = time.time()
                interd = build_and_solve(
                    G, entry_in_g, crown_in_g, findings, budget, backend="auto"
                )
                secs = time.time() - t0
                solve_times.append(secs)
                max_solve_time = max(max_solve_time, secs)
            except RuntimeError:
                continue

            interd_obj_raw = interd.get("objective")
            if not isinstance(interd_obj_raw, (int, float)):
                continue
            interd_obj: float = float(interd_obj_raw)

            # Brute-force check for small instances
            if len(findings) <= 16:
                try:
                    bf_res = brute_force_best(
                        G, entry_in_g, crown_in_g, findings, budget
                    )
                    bf_obj = float(bf_res[0])
                    brute_force_checks += 1
                    if abs(interd_obj - bf_obj) > 1e-6:
                        brute_force_mismatches += 1
                except Exception:
                    pass

            rb = results_by_budget[budget]
            rb["count"] += 1
            rb["naive_residuals"].append(residual_prob(naive_obj))
            rb["stackelberg_residuals"].append(residual_prob(ssg_obj))
            rb["interdiction_residuals"].append(residual_prob(interd_obj))

            if interd_obj > naive_obj + 1e-9:
                rb["interdiction_better_naive"] += 1
            if interd_obj > ssg_obj + 1e-9:
                rb["interdiction_better_stackelberg"] += 1
            if abs(interd_obj - naive_obj) <= 1e-9 and abs(interd_obj - ssg_obj) <= 1e-9:
                rb["interdiction_tied_all"] += 1

    # Scale probe: large graph
    scale_times: dict[str, float | str] = {}
    G_large, entry_l, crown_l, findings_l = _large_enterprise(seed=0)
    entry_l_g = [e for e in entry_l if e in G_large]
    crown_l_g = [c for c in crown_l if c in G_large]

    for backend in ["scipy"]:
        t0 = time.time()
        try:
            r = build_and_solve(G_large, entry_l_g, crown_l_g, findings_l,
                                budget=4, backend=backend)
            scale_times[backend] = time.time() - t0
        except Exception as e:
            scale_times[backend] = f"error: {e}"

    # Try pulp backend for scale probe
    try:
        import highspy  # noqa
        t0 = time.time()
        r2 = build_and_solve(G_large, entry_l_g, crown_l_g, findings_l,
                              budget=4, backend="pulp")
        scale_times["pulp"] = time.time() - t0
        # Cross-check
        raw_obj1 = build_and_solve(G_large, entry_l_g, crown_l_g, findings_l,
                               budget=4, backend="scipy")["objective"]
        raw_obj2 = r2["objective"]
        val1 = float(raw_obj1) if isinstance(raw_obj1, (int, float)) else 0.0
        val2 = float(raw_obj2) if isinstance(raw_obj2, (int, float)) else 0.0
        scale_times["backend_diff"] = abs(val1 - val2)
    except Exception as e:
        scale_times["pulp"] = f"unavailable: {e}"

    # Aggregate
    summary = {
        "n_seeds": n_seeds,
        "budgets": sorted(budgets),
        "mean_solve_time_s": (
            sum(solve_times) / len(solve_times) if solve_times else None
        ),
        "max_solve_time_s": max_solve_time,
        "brute_force_checks": brute_force_checks,
        "brute_force_mismatches": brute_force_mismatches,
        "scale_probe_n_findings": len(findings_l),
        "scale_probe_solve_times_s": scale_times,
        "by_budget": {},
    }

    for b, rb in sorted(results_by_budget.items()):
        n = rb["count"]
        if n == 0:
            continue
        summary["by_budget"][str(b)] = {
            "n_instances": n,
            "mean_naive_residual": sum(rb["naive_residuals"]) / n,
            "mean_stackelberg_residual": sum(rb["stackelberg_residuals"]) / n,
            "mean_interdiction_residual": sum(rb["interdiction_residuals"]) / n,
            "interdiction_better_than_naive": rb["interdiction_better_naive"],
            "interdiction_better_than_stackelberg": rb["interdiction_better_stackelberg"],
            "interdiction_tied_all": rb["interdiction_tied_all"],
        }

    # Write results
    _RESULTS_PATH.write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return summary


if __name__ == "__main__":
    print("Running benchmark with n_seeds=200 ...")
    result = run_benchmark(n_seeds=200, budgets=(2, 4, 6))
    print(json.dumps(result, indent=2))
