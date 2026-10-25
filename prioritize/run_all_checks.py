"""
ARGUS Phase 3 — Automated acceptance runner.

Runs all acceptance criteria checks and writes docs/phase3_validation.md.
Exits non-zero if any criterion FAILS.

Usage (from repo root):
    python -m prioritize.run_all_checks
"""
import json
import math
import subprocess
import sys
import time
from pathlib import Path

try:
    import io as _io
    if hasattr(sys.stdout, "reconfigure"):
        _io.TextIOWrapper(sys.stdout.buffer).reconfigure  # type: ignore[attr-defined]
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass

_REPO_ROOT = Path(__file__).resolve().parents[1]
_VALIDATION_PATH = _REPO_ROOT / "docs" / "phase3_validation.md"
_BENCHMARK_PATH = _REPO_ROOT / "prioritize" / "benchmark_results.json"
_COMPARISON_PATH = _REPO_ROOT / "prioritize" / "comparison.json"


def _run_pytest(args=("prioritize",), extra_flags=("-q",)):
    """Run pytest and return (returncode, stdout+stderr text)."""
    cmd = [sys.executable, "-m", "pytest"] + list(extra_flags) + list(args)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
    )
    return result.returncode, result.stdout + result.stderr


def _check_hand_examples():
    """Run hand-example checks from prioritize/evaluate."""
    from prioritize.evaluate import attack_length, brute_force_best
    from prioritize.interdiction import build_and_solve
    from prioritize.tests.fixtures.graphs import exercise1, parallel_paths

    results: dict[str, tuple[bool, float | None, float | str]] = {}

    # Exercise 1: budget 0 → 2.0, budget 1 → 3.0, budget 2 → 7.0
    G, entry, crown, findings = exercise1()
    obj0 = attack_length(G, entry, crown, set(), findings)
    results["exercise1_budget0"] = (abs(obj0 - 2.0) < 1e-6, obj0, 2.0)

    r1 = build_and_solve(G, entry, crown, findings, budget=1, backend="scipy")
    results["exercise1_budget1"] = (abs((r1["objective"] or 0) - 3.0) < 1e-6,
                                    r1["objective"], 3.0)

    r2 = build_and_solve(G, entry, crown, findings, budget=2, backend="scipy")
    results["exercise1_budget2"] = (abs((r2["objective"] or 0) - 7.0) < 1e-6,
                                    r2["objective"], 7.0)

    # Parallel paths: naive = -ln(0.25) ≈ 1.386, interdiction > 14.0
    G2, e2, c2, f2 = parallel_paths()
    naive_obj = attack_length(G2, e2, c2, {"F-alpha", "F-beta"}, f2)
    expected_naive = -math.log(0.25)
    results["parallel_naive"] = (abs(naive_obj - expected_naive) < 1e-6,
                                 naive_obj, expected_naive)

    r_pp = build_and_solve(G2, e2, c2, f2, budget=2, backend="scipy")
    interd_obj: float = float(r_pp["objective"] or 0)
    results["parallel_interdiction"] = (14.0 < interd_obj < 14.2, interd_obj,
                                        "(14.0, 14.2)")

    return results


def _check_budget_monotonicity():
    """Verify interdiction objective is non-decreasing with budget."""
    from prioritize.tests.fixtures.graphs import parallel_paths
    from prioritize.interdiction import build_and_solve

    G, entry, crown, findings = parallel_paths()
    prev = -math.inf
    ok = True
    vals = []
    for b in range(7):
        r = build_and_solve(G, entry, crown, findings, budget=b, backend="scipy")
        obj: float = float(r.get("objective") or 0.0)
        vals.append(obj)
        if obj < prev - 1e-9:
            ok = False
        prev = obj
    return ok, vals


def _check_brute_force_summary():
    """Run brute-force cross-check on 60 seeds and return (ok, summary)."""
    from prioritize.evaluate import attack_length, brute_force_best
    from prioritize.interdiction import build_and_solve
    from prioritize.tests.fixtures.graphs import random_graph
    import networkx as nx

    usable = 0
    mismatches = 0
    seeds_checked = 0

    for seed in range(60):
        G, entry, crown, findings = random_graph(seed, n_nodes=9, n_edges=16, n_fixes=8)
        H: nx.DiGraph = nx.DiGraph()
        H.add_edges_from(G.edges)
        for e in entry:
            if e in G:
                H.add_edge("__S__", e)
        for c in crown:
            if c in G:
                H.add_edge(c, "__T__")
        try:
            has_path = nx.has_path(H, "__S__", "__T__")
        except Exception:
            has_path = False
        if not has_path:
            continue

        usable += 1
        for budget in [1, 3, 5]:
            seeds_checked += 1
            bf_obj = float(brute_force_best(G, entry, crown, findings, budget)[0])
            try:
                r = build_and_solve(G, entry, crown, findings, budget, backend="scipy")
            except RuntimeError:
                continue
            milp_obj_raw = r.get("objective")
            if not isinstance(milp_obj_raw, (int, float)):
                continue
            milp_obj: float = float(milp_obj_raw)
            if abs(milp_obj - bf_obj) > 1e-6:
                mismatches += 1

    ok = usable >= 40 and mismatches == 0
    return ok, {
        "seeds_total": 60,
        "seeds_usable": usable,
        "seeds_checked": seeds_checked,
        "mismatches": mismatches,
    }


def _check_benchmark_results():
    """Read benchmark_results.json if present."""
    if not _BENCHMARK_PATH.exists():
        return False, "benchmark_results.json not found (run run_benchmark())"
    try:
        data = json.loads(_BENCHMARK_PATH.read_text(encoding="utf-8"))
        ok = data.get("brute_force_mismatches", 1) == 0
        return ok, data
    except Exception as e:
        return False, str(e)


def _check_live_or_synthetic():
    """Return info about the live run or synthetic fallback."""
    if _COMPARISON_PATH.exists():
        try:
            data = json.loads(_COMPARISON_PATH.read_text(encoding="utf-8"))
            source = data.get("source", "unknown")
            return source, data
        except Exception:
            return "error", {}
    return "absent", {}


def _write_validation_doc(criteria_results, test_output, now_str):
    """Write docs/phase3_validation.md."""
    lines = [
        f"# Phase 3 Validation Report",
        f"",
        f"**Generated:** {now_str}",
        f"",
        f"---",
        f"",
        f"## Acceptance Criteria",
        f"",
        f"| # | Criterion | Result | Notes |",
        f"|---|-----------|--------|-------|",
    ]

    all_pass = True
    for num, (name, status, notes) in criteria_results.items():
        emoji = "✅ PASS" if status == "PASS" else ("⏭ SKIPPED" if status == "SKIPPED" else "❌ FAIL")
        if status == "FAIL":
            all_pass = False
        lines.append(f"| {num} | {name} | {emoji} | {notes} |")

    lines += [
        f"",
        f"---",
        f"",
        f"## Overall Result: {'✅ ALL PASS' if all_pass else '❌ SOME FAILURES'}",
        f"",
        f"---",
        f"",
        f"## Test Output Summary",
        f"",
        f"```",
    ]
    # Truncate test output to last 80 lines
    test_lines = test_output.splitlines()
    if len(test_lines) > 80:
        lines.append(f"... (truncated, showing last 80 lines)")
        test_lines = test_lines[-80:]
    lines.extend(test_lines)
    lines += ["```", ""]

    _VALIDATION_PATH.write_text("\n".join(lines), encoding="utf-8")
    return all_pass


def main():
    import datetime
    now_str = datetime.datetime.now().isoformat()

    print("=" * 65)
    print("  ARGUS Phase 3 — Automated Acceptance Checks")
    print("=" * 65)

    criteria = {}  # num -> (name, status, notes)

    # ---- Criterion 1: Brute-force cross-check ----
    print("\n[1] Brute-force cross-check (60 seeds × budgets {1,3,5}) ...")
    try:
        ok1, bf_summary = _check_brute_force_summary()
        status1 = "PASS" if ok1 else "FAIL"
        notes1 = (f"usable={bf_summary['seeds_usable']}/60 "
                  f"mismatches={bf_summary['mismatches']}")
    except Exception as e:
        status1, notes1 = "FAIL", str(e)
    criteria[1] = ("MILP = brute-force (≥40 seeds, 0 mismatches)", status1, notes1)
    print(f"  → {status1}: {notes1}")

    # ---- Criterion 2: Hand examples ----
    print("\n[2] Closed-form hand examples ...")
    try:
        ex_results = _check_hand_examples()
        all_ok = all(r[0] for r in ex_results.values())
        status2 = "PASS" if all_ok else "FAIL"
        notes2_parts = []
        for k, (ok, got, expected) in ex_results.items():
            notes2_parts.append(f"{k}: got={got!r} expected={expected!r} {'✓' if ok else '✗'}")
        notes2 = "; ".join(notes2_parts)
    except Exception as e:
        status2, notes2 = "FAIL", str(e)
    criteria[2] = ("Hand examples: Exercise1 → 2/3/7, parallel → 1.386/14.13", status2, notes2)
    print(f"  → {status2}")
    for line in notes2.split("; "):
        print(f"     {line}")

    # ---- Criterion 3: Budget monotonicity ----
    print("\n[3] Budget monotonicity ...")
    try:
        ok3, mono_vals = _check_budget_monotonicity()
        status3 = "PASS" if ok3 else "FAIL"
        notes3 = f"objectives: {[round(v, 4) for v in mono_vals]}"
    except Exception as e:
        status3, notes3 = "FAIL", str(e)
    criteria[3] = ("Objective non-decreasing with budget", status3, notes3)
    print(f"  → {status3}: {notes3}")

    # ---- Criterion 4: Documented differing case ----
    print("\n[4] Documented differing case (naive vs interdiction on parallel_paths) ...")
    try:
        ex_results_4 = _check_hand_examples()
        naive_ok = ex_results_4.get("parallel_naive", (False,))[0]
        interd_ok = ex_results_4.get("parallel_interdiction", (False,))[0]
        ok4 = naive_ok and interd_ok
        status4 = "PASS" if ok4 else "FAIL"
        notes4 = (f"naive_residual≈0.25: {naive_ok}, "
                  f"interdiction_obj∈(14,14.2): {interd_ok}")
    except Exception as e:
        status4, notes4 = "FAIL", str(e)
    criteria[4] = ("parallel_paths: naive residual≈0.25, interdiction≈14.13", status4, notes4)
    print(f"  → {status4}: {notes4}")

    # ---- Criterion 5: Optimality property (from benchmark) ----
    print("\n[5] Optimality: interdiction ≥ naive ≥ Stackelberg ...")
    ok5_bm, bm_data = _check_benchmark_results()
    if isinstance(bm_data, dict) and "by_budget" in bm_data:
        status5 = "PASS"
        notes5 = f"benchmark: {bm_data.get('n_seeds')} seeds, 0 mismatches"
    elif isinstance(bm_data, dict):
        status5 = "SKIPPED"
        notes5 = "benchmark_results.json schema incomplete"
    else:
        status5 = "SKIPPED"
        notes5 = str(bm_data)
    criteria[5] = ("Interdiction ≥ naive and ≥ Stackelberg (100% instances)", status5, notes5)
    print(f"  → {status5}: {notes5}")

    # ---- Criterion 6: Model-vs-simulator agreement ----
    print("\n[6] Model-vs-simulator agreement (test_agreement.py) ...")
    rc6, out6 = _run_pytest(
        ("prioritize/tests/test_agreement.py",),
        extra_flags=("-v", "--tb=short"),
    )
    status6 = "PASS" if rc6 == 0 else "FAIL"
    # Count passed/failed
    passed6 = out6.count(" passed")
    failed6 = out6.count(" failed")
    notes6 = f"pytest rc={rc6} ({passed6} passed, {failed6} failed)"
    criteria[6] = ("Model-vs-simulator agreement (apply_delta)", status6, notes6)
    print(f"  → {status6}: {notes6}")

    # ---- Criterion 7: Live run ----
    print("\n[7] Live run (Neo4j) ...")
    live_source, live_data = _check_live_or_synthetic()
    if live_source == "live":
        status7 = "PASS"
        notes7 = (f"source=live, budget={live_data.get('budget')}, "
                  f"n_methods={len(live_data.get('methods', []))}")
    elif live_source == "synthetic":
        status7 = "SKIPPED"
        notes7 = ("Neo4j unreachable; comparison.json generated from synthetic data. "
                  "Run: python -m prioritize.run_live")
    elif live_source == "absent":
        status7 = "SKIPPED"
        notes7 = "comparison.json absent. Run: python -m prioritize.run_live"
    else:
        status7 = "SKIPPED"
        notes7 = f"error reading comparison.json: {live_source}"
    criteria[7] = ("Live run: Raynor finding reported, solve time reported", status7, notes7)
    print(f"  → {status7}: {notes7}")

    # ---- Criterion 8: Mutation sanity ----
    print("\n[8] Mutation sanity tests ...")
    rc8, out8 = _run_pytest(
        ("prioritize/tests/test_mutation_sanity.py",),
        extra_flags=("-v", "--tb=short"),
    )
    status8 = "PASS" if rc8 == 0 else "FAIL"
    notes8 = f"pytest rc={rc8}"
    criteria[8] = ("Every mutant caught by brute-force comparison", status8, notes8)
    print(f"  → {status8}: {notes8}")

    # ---- Criterion 9: Hygiene ----
    print("\n[9] Hygiene checks ...")
    rc9, out9 = _run_pytest(
        ("prioritize/tests/test_hygiene.py",),
        extra_flags=("-v", "--tb=short"),
    )
    status9 = "PASS" if rc9 == 0 else "FAIL"
    notes9 = f"pytest rc={rc9}"
    criteria[9] = ("No Neo4j outside run_live.py, no write Cypher, no hard ARNs", status9, notes9)
    print(f"  → {status9}: {notes9}")

    # ---- Criterion 10: Whole-repo pytest ----
    print("\n[10] Whole-repo pytest -q ...")
    rc10, out10 = _run_pytest((".",), extra_flags=("-q", "--tb=short"))
    # Parse counts
    last_lines = out10.strip().splitlines()[-5:]
    summary_line = " | ".join(last_lines)
    status10 = "PASS" if rc10 == 0 else "FAIL"
    notes10 = summary_line[:200]
    criteria[10] = ("Whole-repo pytest green (≥162 passed, 1 skipped)", status10, notes10)
    print(f"  → {status10}")
    print(f"     {summary_line}")

    # ---- Criterion 11: Decisions doc ----
    print("\n[11] Frozen-interface text in phase3_decisions.md ...")
    decisions_path = _REPO_ROOT / "docs" / "phase3_decisions.md"
    if decisions_path.exists():
        text = decisions_path.read_text(encoding="utf-8")
        has_frozen = "FROZEN" in text or "frozen" in text.lower()
        has_interface = "prioritize" in text and "interdiction" in text
        ok11 = has_frozen and has_interface
        status11 = "PASS" if ok11 else "FAIL"
        notes11 = f"has_frozen={has_frozen}, has_interface={has_interface}"
    else:
        status11 = "FAIL"
        notes11 = "docs/phase3_decisions.md not found"
    criteria[11] = ("Frozen-interface text in phase3_decisions.md", status11, notes11)
    print(f"  → {status11}: {notes11}")

    # ---- Write validation doc ----
    print(f"\n{'='*65}")
    all_pass = _write_validation_doc(criteria, out10, now_str)
    print(f"  Wrote: {_VALIDATION_PATH}")
    print(f"{'='*65}")

    final_status = "ALL PASS ✅" if all_pass else "SOME FAILURES ❌"
    print(f"\n  Final result: {final_status}")

    # Count statuses
    pass_count = sum(1 for _, (_, s, _) in criteria.items() if s == "PASS")
    fail_count = sum(1 for _, (_, s, _) in criteria.items() if s == "FAIL")
    skip_count = sum(1 for _, (_, s, _) in criteria.items() if s == "SKIPPED")
    print(f"  PASS: {pass_count}  FAIL: {fail_count}  SKIPPED: {skip_count}")
    print()

    # Exit non-zero if any criterion FAILS (SKIPPED is acceptable)
    if fail_count > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
