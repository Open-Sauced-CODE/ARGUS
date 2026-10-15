# Phase 3 Handoff Notes

**Phase 3 → Phase 7 (Execution Gate) handoff**  
**Status:** Ready for Phase 7 integration  
**Author:** Phase 3 Engineer  
**Date:** 2026-10-04

---

## Summary

Phase 3 delivers the **Prioritization Engine**: given the Phase 2 attack graph
and a budget, it chooses which IAM/network fixes to apply so the shortest
attacker path to the crown jewels becomes as unlikely as possible.

The primary output is `prioritize.interdiction.prioritize(findings, budget, G,
entry_nodes=None, crown_jewels=None)`, which returns an ordered list of
`finding_id` strings (selected first, then unselected by marginal efficiency).

---

## What Phase 7 Must Do

### Required integration steps

1. **Import** `prioritize.interdiction.prioritize_detailed` (not the simplified
   `prioritize`). The `_detailed` variant returns the full dict including the
   selected set, the objective, and the ranked list.

2. **Pass the attack graph** explicitly. Phase 7 must build the graph via
   `risk.attack_graph.build_attack_graph(session)` and pass it as `G`. There is
   no default graph.

3. **Read `comparison.json`** for the dashboard summary. The JSON is written by
   `python -m prioritize.run_live` (or populated with synthetic data).

4. **Apply the selected fixes** using `risk.simulate.apply_delta` on a copy of
   the graph, then re-score. This is the Phase 7 "risk decreased" gate.

5. **Call `attack_length`** on both the original and the patched graph to verify
   the objective increased. Use `prioritize.evaluate.attack_length`.

6. **Check `rule_gap` flags.** Findings with `rule_gap=True` have no
   corresponding Phase 4 Rego rule. The execution gate must warn the operator
   that these cannot be automatically policy-checked.

---

## API Reference

### Production call (Phase 7 integration)

```python
from prioritize.interdiction import prioritize_detailed
from prioritize.findings import enumerate_findings

findings = enumerate_findings(G)
result = prioritize_detailed(
    findings,
    budget=3,           # from config.json default_budget
    G=G,
    entry_nodes=resolve_entry_nodes(G),
    crown_jewels=get_crown_jewels(G),
)

# result keys:
# "ranked":    list[dict] — all findings, selected first then by efficiency
# "selected":  list[str]  — finding_ids chosen by the MILP
# "objective": float      — attack_length after the selected fixes are applied
# "status":    str        — "Optimal", "NoPath", etc.
```

### Evaluation helpers

```python
from prioritize.evaluate import (
    compare_methods,    # naive vs Stackelberg vs interdiction comparison
    budget_sweep,       # objective at budgets 0..K
    attack_length,      # re-evaluate any selected set
    residual_prob,      # exp(-objective)
)
```

---

## Changed interface vs spec v1

- `prioritize(findings, budget, G, ...)` — **`G` is required** (was optional in
  the master guide). Phase 7 must always pass the graph.

---

## Files Phase 7 Should Read

| File | Purpose |
|------|---------|
| `prioritize/__init__.py` | Public API exports |
| `prioritize/interdiction.py` | Solver implementation |
| `prioritize/findings.py` | Findings enumeration |
| `prioritize/evaluate.py` | Evaluation helpers |
| `prioritize/fix_catalogue.json` | Fix types and costs |
| `prioritize/config.json` | Default budget, PPR config |
| `prioritize/comparison.json` | Latest run output (written by run_live.py) |
| `docs/phase3_decisions.md` | All design decisions |

---

## Outstanding Human Action Items

1. **Catalogue review** (30 min, with security lead): validate the heuristic
   cost values in `fix_catalogue.json` and the budget in `config.json`.

2. **`deactivate_key` and `tighten_trust` activation** (future): extend
   `risk/simulate.py` to handle these ops, then flip `enabled: true` in the
   catalogue and add tests.

3. **Phase 4 Rego gaps**: create Rego rules for all findings where
   `rule_gap: true`. Current gaps: `iam_privilege_escalation`, `iam_data_access`.

4. **`restrict_cidr` remediation script**: the fix is simulated; Phase 7 must
   implement the actual API call to update the security group ingress rule.

5. **Production budget tuning**: the current `default_budget: 3` is a
   placeholder. Run `budget_sweep` on the live graph at each sprint to calibrate.

---

## Running Phase 3 Live

```powershell
# From repo root, on phase3/prioritize branch:

# 1. Install Phase 3 dependencies
pip install -r requirements-phase3.txt

# 2. Run live (requires NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD in .env or environment)
python -m prioritize.run_live

# 3. Run all acceptance checks
python -m prioritize.run_all_checks

# 4. Run synthetic benchmark (200 seeds)
python -m prioritize.benchmark
```

---

## Benchmark Summary (Synthetic, 200 seeds, budget 4)

Generated: 2026-10-04 (see `prioritize/benchmark_results.json` after running `run_benchmark()`)

- Brute-force mismatches: 0
- MILP strictly better than naive: documented in benchmark_results.json
- Median solve time: < 0.5 s per instance (scipy backend)
- Scale probe (≥40 findings): < 5 s

---

## Test Coverage

```
prioritize/tests/
├── test_catalogue.py        # fix_catalogue.json schema
├── test_evaluate.py         # attack_length, brute_force_best
├── test_findings.py         # enumerate_findings
├── test_interdiction.py     # build_and_solve, prioritize, prioritize_detailed
├── test_bruteforce.py       # MILP vs brute-force (60 seeds × 3 budgets)
├── test_mutation_sanity.py  # textual source mutations caught by brute-force
├── test_naive.py            # greedy PPR baseline + optimality property
├── test_stackelberg.py      # Stackelberg baseline + hand-check cases
├── test_agreement.py        # MILP model vs risk.simulate.apply_delta
├── test_compare.py          # compare_methods, budget_sweep
├── test_benchmark.py        # synthetic enterprise benchmark
└── test_hygiene.py          # code hygiene, allowed paths, no notebook outputs
```

Total test count (all backends where available): ~120 tests.
