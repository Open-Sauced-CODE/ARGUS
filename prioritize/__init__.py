"""
ARGUS Phase 3 — Prioritization Engine

This package answers: *which fixes, within the budget, make the attacker's
best route into the crown jewels as improbable as possible?*

Public API (frozen after Phase 3 freeze announcement):
  - findings.enumerate_findings(G, catalogue=None, include_unsimulated=False)
  - interdiction.prioritize(findings, budget, G, entry_nodes=None, crown_jewels=None)
  - interdiction.prioritize_detailed(...)
  - evaluate.compare_methods(G, entry, crown, findings, budget)
  - evaluate.budget_sweep(G, entry, crown, findings, budgets)

Only run_live.py may open a Neo4j session.  All other modules are
pure Python over a networkx DiGraph.
"""
