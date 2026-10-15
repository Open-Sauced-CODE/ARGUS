# ARGUS Phase 3 — Prioritization Engine

## Mission

Take the Phase 2 attack graph and answer: **which fixes, within the budget, make the attacker's most probable route into the crown jewels as unlikely as possible?**

The answer comes from a Mixed-Integer Linear Program (MILP) that is the dual of the shortest-path LP with binary fix-selection variables. Two baselines (naive PPR-sort and Stackelberg security game) are provided for comparison only.

---

## How to run

### Tests
```powershell
# From repo root, activate the venv first
.venv\Scripts\Activate.ps1
python -m pytest -q prioritize
python -m pytest -q          # whole repo
```

### Acceptance checks (generates docs/phase3_validation.md)
```powershell
.venv\Scripts\python.exe -m prioritize.run_all_checks
```

### Live Neo4j run (read-only; Neo4j container must be up)
```powershell
.venv\Scripts\python.exe -m prioritize.run_live
```
Output: `prioritize/comparison.json`

---

## File map

| File | Purpose |
|---|---|
| `findings.py` | Enumerate fix-findings from the attack graph |
| `interdiction.py` | MILP solver (PuLP+HiGHS or scipy fallback) + `prioritize()` |
| `naive.py` | Greedy-PPR baseline (comparison only) |
| `stackelberg_baseline.py` | Stackelberg security-game baseline (comparison only) |
| `evaluate.py` | Independent Dijkstra evaluator, brute-force checker, compare_methods, budget_sweep |
| `benchmark.py` | Synthetic enterprise graph generator + aggregate benchmark |
| `run_live.py` | Read-only Neo4j session → comparison.json |
| `run_all_checks.py` | Automated acceptance runner → docs/phase3_validation.md |
| `fix_catalogue.json` | Fix types, deltas, costs (frozen after team review) |
| `config.json` | Budget, Stackelberg params, k for critical paths |
| `comparison.json` | Latest method comparison (generated; source: live or synthetic) |
| `benchmark_results.json` | Benchmark run results (generated) |
| `notebooks/interdiction_exploration.ipynb` | Exploration notebook (outputs stripped) |

---

## Frozen Phase 2 interface

This package **reads** from `risk/` but **never writes** to it:

- `risk.attack_graph.build_attack_graph(session)` → `nx.DiGraph`
- `risk.attack_graph.resolve_entry_nodes(G, cfg=None)` → `list[node_id]`
- `risk.attack_graph.get_crown_jewels(G, cfg=None)` → `list[node_id]`
- `risk.pagerank.score_digraph(G, entry_nodes=None, damping=None)` → `dict`
- `risk.pagerank.to_percent(pi, exclude=())` → `dict`
- `risk.simulate.apply_delta(G, delta)` → copy of G with ops applied
- `risk.paths.most_probable_path(G, source, target)` → `(path, prob)`

Only `run_live.py` imports `risk.graph_loader`.

---

## Extra dependency

Install alongside `requirements.txt`:
```powershell
pip install -r requirements-phase3.txt   # adds highspy for PuLP 4 HiGHS solver
```
If `highspy` is unavailable, `interdiction.py` automatically falls back to `scipy.optimize.milp`.
