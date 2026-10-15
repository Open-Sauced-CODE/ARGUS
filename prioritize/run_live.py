"""
ARGUS Phase 3 — Live graph run (read-only Neo4j).

Opens a Neo4j session via risk.graph_loader.get_driver(), builds the Phase 2
attack graph, enumerates findings, runs all three methods at the configured
default budget, prints a table, and writes prioritize/comparison.json.

RULES:
  - Read-only (MATCH ... RETURN only; no CREATE/MERGE/DELETE/SET/REMOVE)
  - No secrets printed (NEO4J_PASSWORD masked)
  - Clear error if Neo4j is unreachable
  - Only this file may open a Neo4j session in the prioritize package

Usage (from repo root):
    python -m prioritize.run_live
"""

import json
import math
import sys
import time
import traceback
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_COMPARISON_PATH = _HERE / "comparison.json"


def _mask_password(s):
    """Replace any occurrence of the Neo4j password with ****."""
    import os
    pw = os.environ.get("NEO4J_PASSWORD", "")
    if pw and pw in s:
        s = s.replace(pw, "****")
    return s


def _print_table(methods, findings, budget):
    """Print a simple text table of results."""
    print(f"\n{'='*70}")
    print(f"  Phase 3 — Interdiction Results (budget={budget})")
    print(f"{'='*70}")
    print(f"  {'Method':<25} {'Selected':<35} {'Residual Prob':>15}")
    print(f"  {'-'*65}")
    for m in methods:
        sel_str = ", ".join(m["selected"][:3])
        if len(m["selected"]) > 3:
            sel_str += f" (+{len(m['selected'])-3} more)"
        rp = m.get("residual_attack_prob", 0)
        print(f"  {m['name']:<25} {sel_str:<35} {rp:>15.2e}")
    print(f"{'='*70}\n")


def run():
    """Main entry point for the live run."""
    try:
        from risk.graph_loader import get_driver
        from risk.attack_graph import build_attack_graph, resolve_entry_nodes, get_crown_jewels
    except ImportError as e:
        print(f"ERROR: Cannot import risk modules: {e}", file=sys.stderr)
        sys.exit(1)

    from prioritize.findings import enumerate_findings, list_non_actionable, load_config
    from prioritize.evaluate import compare_methods, attack_length, residual_prob

    cfg = load_config()
    budget = cfg.get("default_budget", 3)

    # ---- Connect to Neo4j ----
    print("Connecting to Neo4j (read-only)...")
    try:
        driver = get_driver()
    except Exception as e:
        msg = _mask_password(str(e))
        print(f"ERROR: Cannot connect to Neo4j: {msg}", file=sys.stderr)
        print("\nGenerating comparison.json from synthetic data instead.", file=sys.stderr)
        _write_synthetic_comparison(budget)
        sys.exit(0)

    # ---- Build attack graph ----
    print("Building attack graph...")
    try:
        with driver.session() as session:
            G = build_attack_graph(session)
    except Exception as e:
        msg = _mask_password(str(e))
        print(f"ERROR: build_attack_graph failed: {msg}", file=sys.stderr)
        driver.close()
        _write_synthetic_comparison(budget)
        sys.exit(0)
    finally:
        try:
            driver.close()
        except Exception:
            pass

    n_nodes = G.number_of_nodes()
    n_edges = G.number_of_edges()
    from collections import Counter
    etype_counts = Counter(d.get("etype", "?") for _, _, d in G.edges(data=True))

    print(f"Graph: {n_nodes} nodes, {n_edges} edges")
    for etype, count in sorted(etype_counts.items()):
        print(f"  {etype}: {count}")

    # ---- Resolve entry / crown ----
    entry = resolve_entry_nodes(G)
    crown = get_crown_jewels(G)
    print(f"\nEntry nodes ({len(entry)}): {entry}")
    print(f"Crown jewels ({len(crown)}): {crown}")

    # ---- Enumerate findings ----
    findings = enumerate_findings(G)
    non_act = list_non_actionable(G)

    print(f"\nActionable findings: {len(findings)}")
    for f in findings:
        print(f"  [{f['finding_id']}] {f['fix_op']} → {f['target_label']!r}"
              f" cost={f['cost']} delta={f['delta']:.4f}")

    print(f"\nNon-actionable (AWS-managed) statements: {len(non_act)}")
    for f in non_act:
        print(f"  [{f['finding_id']}] {f['target']!r} → {f.get('note','')}")

    # Check for Raynor IAM privilege-escalation finding
    raynor_found = any(
        "IAMPrivilegeEscalationByRollback" in f.get("target_label", "")
        or "escalation" in f.get("target_label", "").lower()
        for f in findings
    )
    print(f"\nRaynor IAMPrivilegeEscalationByRollback finding present: {raynor_found}")

    # ---- Run comparison ----
    if not findings:
        print("\nNo actionable findings found. Skipping comparison.")
        comp = {
            "source": "live",
            "budget": budget,
            "entry_count": len(entry),
            "crown_jewel_count": len(crown),
            "methods": [],
            "budget_sweep": [],
            "note": "No actionable findings on live graph.",
        }
    else:
        print(f"\nRunning comparison (budget={budget})...")
        t0 = time.time()
        try:
            comp = compare_methods(G, entry, crown, findings, budget)
            comp["source"] = "live"
            secs = time.time() - t0
            comp["solve_seconds"] = secs
            print(f"Comparison done in {secs:.2f}s")
            _print_table(comp["methods"], findings, budget)
        except Exception as e:
            print(f"ERROR in compare_methods: {e}", file=sys.stderr)
            traceback.print_exc()
            comp = {
                "source": "live",
                "budget": budget,
                "entry_count": len(entry),
                "crown_jewel_count": len(crown),
                "methods": [],
                "budget_sweep": [],
                "error": str(e),
            }

    # ---- Write comparison.json ----
    _COMPARISON_PATH.write_text(
        json.dumps(comp, indent=2, sort_keys=True, default=_json_default),
        encoding="utf-8",
    )
    print(f"\nWrote {_COMPARISON_PATH}")


def _json_default(obj):
    """JSON serialiser for sets and non-standard types."""
    if isinstance(obj, (set, frozenset)):
        return sorted(obj)
    if isinstance(obj, float) and math.isinf(obj):
        return None
    raise TypeError(f"Not JSON serialisable: {type(obj)}")


def _write_synthetic_comparison(budget):
    """Generate comparison.json from synthetic data when Neo4j is unreachable."""
    from prioritize.benchmark import synthetic_enterprise
    from prioritize.evaluate import compare_methods

    print("Generating synthetic comparison.json (seed=0)...")
    G, entry, crown, findings = synthetic_enterprise(seed=0)
    entry_g = [e for e in entry if e in G]
    crown_g = [c for c in crown if c in G]

    try:
        comp = compare_methods(G, entry_g, crown_g, findings, budget)
    except Exception as e:
        comp = {
            "budget": budget,
            "entry_count": len(entry_g),
            "crown_jewel_count": len(crown_g),
            "methods": [],
            "budget_sweep": [],
            "error": str(e),
        }

    comp["source"] = "synthetic"
    _COMPARISON_PATH.write_text(
        json.dumps(comp, indent=2, sort_keys=True, default=_json_default),
        encoding="utf-8",
    )
    print(f"Wrote synthetic {_COMPARISON_PATH}")


if __name__ == "__main__":
    run()
