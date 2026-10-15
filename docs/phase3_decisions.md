# Phase 3 Decisions Log

**Owner:** Phase 3 Engineer  
**Date range:** 2026-10-04  
**Status:** FROZEN — changes require a new dated entry and team approval.

---

## 2026-10-04 — Interdiction MILP chosen as primary; Stackelberg as comparison-only baseline

**Decision:** The network-interdiction MILP (dual of the shortest-path LP with binary fix variables) is the production prioritization algorithm. The Stackelberg security game is kept as a labelled comparison-only baseline.

**Why:** Interdiction is provably optimal for the one-shot patching decision problem (choose a set of fixes within a budget to maximize the shortest attacker path). Stackelberg randomized coverage is designed for inspection schedules, not patching — a system cannot be patched "68%". The interdiction MILP is verified against brute force on >60 random instances with 0 mismatches.

**Alternatives considered:** Greedy by risk score (naive), Stackelberg mixed strategy, greedy by marginal gain. All dominated by the MILP on the parallel-paths example.

---

## 2026-10-04 — Variables per fix, edge-disjoint catalogue

**Decision:** MILP variables are one binary per *finding* (not per edge). No edge may be covered by two findings (edge-disjointness enforced at catalogue definition and validated at enumeration time).

**Why:** One real fix (removing a policy statement) hardens several edges simultaneously. Variables per edge would double-count Δ and could exceed the simulator's P_FLOOR cap. Edge-disjointness prevents Δ values from accumulating beyond Δ_max.

**Alternatives considered:** Per-edge binary variables — rejected because a single fix covers multiple edges and the disjointness invariant would require complex coupling constraints.

---

## 2026-10-04 — Δ_max = −ln(1e-6) matches the simulator floor

**Decision:** `Δ_max = −ln(1e-6) ≈ 13.8155`. This is the maximum delta applied to any edge when a fix removes it.

**Why:** `risk/simulate.py` clamps `p` to a minimum of `1e-6` (P_FLOOR). Using `Δ_max = −ln(1e-6)` means the MILP model and the simulator agree: a "removed" edge still has probability 1e-6 in the simulator, and the MILP models this as adding `Δ_max` to the edge length. The agreement test (`test_agreement.py`) verifies this.

**Alternatives considered:** Δ = ∞ (truly remove edge) — not possible with a finite MILP; the floor is the correct reconciliation.

---

## 2026-10-04 — MVP catalogue: two simulated, Patch-IR-aligned fixes; key/trust off by default

**Decision:** The MVP fix catalogue contains two entries: `remove_policy_statement` and `restrict_cidr`. Both are simulated by `risk.simulate.apply_delta` and present in the Patch-IR vocabulary. `deactivate_key` and `tighten_trust` are in the catalogue but `enabled: false`.

**Why:** Phase 7's execution gate re-scores using `apply_delta`. A recommended fix that `apply_delta` silently ignores would never pass the "risk decreased" gate check. Optional fixes are off by default until `simulate.py` is extended with their ops and the Patch-IR vocabulary is updated.

**Alternatives considered:** Include all four fix types — rejected because two are not simulatable and would produce findings that cannot be verified.

---

## 2026-10-04 — Super-source over entry set; super-sink over crown jewels

**Decision:** A virtual node `__S__` connects (with zero-length edges) to every entry node; a virtual `__T__` connects from every crown jewel. The MILP maximizes `π_T − π_S`.

**Why:** The attacker starts anywhere in the entry set and wins at any crown jewel. Using a super-source/super-sink handles the multi-entry, multi-crown case in a single shortest-path computation. The attacker takes the easiest crown jewel (minimum over crown nodes), which is correct.

**Alternatives considered:** Per-crown-jewel solves and take the minimum — correct but O(|C|) solver calls; the super-sink approach is equivalent and O(1) calls.

---

## 2026-10-04 — Ordering rule: solo gain for selected; gain/cost for unselected

**Decision:** Selected findings ordered by solo gain descending (then lower cost, then `finding_id`). Unselected findings ordered by solo gain per unit cost descending (then `finding_id`).

**Why:** The ordering is the primary interface Phase 7 uses to decide which fix to remediate first. Solo gain (objective with only that fix) is the most interpretable metric for selected fixes. Gain per cost (marginal efficiency) is the right metric for unselected fixes the operator may apply in future cycles.

**Alternatives considered:** Order by PPR of target node — same as the naive baseline, which the MILP dominates. Order by combined gain — ignores that selected fixes already interact.

---

## 2026-10-04 — prioritize() takes the graph as a required third argument

**Decision:** `prioritize(findings, budget, G, entry_nodes=None, crown_jewels=None)` — `G` is the third positional argument, not a keyword.

**Why:** The master guide listed `G` as optional-with-default, but Phase 3 cannot build a default graph without a Neo4j session. Requiring `G` makes the interface honest and forces callers (Phase 7) to pass the graph explicitly.

**Team notification required:** Phase 7 owner and Role D must be told that `G` is required; update their integration code.

---

## 2026-10-04 — Naive baseline: greedy by PPR score of target node, skip-and-continue

**Decision:** Naive baseline scores each finding by `score_digraph(G, entry)[target]`, sorts descending (ties: lower cost, then `finding_id`), walks the sorted list and takes each finding that fits the remaining budget (skips but continues).

**Why:** This is the simplest sensible policy and the natural comparison point. It is what an operator would do without a graph-level algorithm. The skip-and-continue rule (rather than stop-on-first-skip) makes it a fair comparison — it is as generous as possible to the naive approach.

---

## 2026-10-04 — Stackelberg payoffs, pa_ratio, and rounding

**Decision:** Attacker payoff when uncovered = `Ra_i = ppr_percent[target_i]`. Attacker payoff when covered = `Pa_i = −pa_ratio × Ra_i` with `pa_ratio = 0.2` (from `config.json`). Defender payoffs zero-sum. Fractional solution rounded by the same greedy rule as naive.

**Why:** `pa_ratio = 0.2` means the attacker still gains 20% of their target value even when the fix is applied (e.g., detection cost). This is conservative and clearly labelled as heuristic. The rounding note is shown explicitly in `comparison.json` and the dashboard.

**Alternatives considered:** `pa_ratio = 0` (pure deterrence) — special case tested as a hand check. `pa_ratio = 1` would make the game trivial.

---

## 2026-10-04 — Catalogue/config numbers are heuristic; pending team review

**Decision:** All values in `fix_catalogue.json` and `config.json` (Δ values, costs, budget, `pa_ratio`) are heuristic placeholders frozen after the catalogue meeting.

**Why:** These numbers are judgement, like the Phase 2 edge weights. They must not be tuned post-hoc to improve a demo. Any change requires a dated entry in this file with who approved it.

**Action required (human):** 30-minute catalogue review meeting. See `docs/phase3_handoff.md` for the agenda.

---

## 2026-10-04 — PuLP 4.0.0 API; highspy required; scipy as fallback

**Decision:** PuLP 4.0.0 (pinned in `requirements.txt`) uses a different API: variables must be created via `prob.add_variable(...)`, not `pulp.LpVariable(...)`. The bundled solver was removed; `highspy` (in `requirements-phase3.txt`) provides HiGHS. `scipy.optimize.milp` (already in `requirements.txt` via scipy) is the automatic fallback and second independent backend.

**Why:** Discovered during Stage 0 preflight. The spec required both backends; using scipy as the fallback means the package works even without `highspy` installed.

**Files changed:** `requirements-phase3.txt` (new file; `highspy` pin). `requirements.txt` not touched.

---

## 2026-10-04 — Self-check: re-evaluate solver answer with independent Dijkstra

**Decision:** After every solve, `build_and_solve` re-evaluates the selected set using `evaluate.attack_length` (pure Dijkstra, no solver). If the difference exceeds 1e-6, `SolverMismatchError` is raised.

**Why:** The solver status object is unreliable across solver versions. The independent Dijkstra check makes the verification solver-agnostic and is the strongest correctness guarantee we have.

---

## 2026-10-04 — AWS-managed policy statements excluded as non-actionable

**Decision:** Statement node ids starting with `arn:aws:iam::aws:policy/` are excluded from `enumerate_findings()` by default and returned separately by `list_non_actionable()`.

**Why:** Operators cannot edit AWS-managed policies. The real fix is to detach the policy from the principal. Including AWS-managed statements in the actionable list would produce findings that cannot be executed by Phase 7.

---

## 2026-10-04 — rule_ids only from Phase 4's real list; rule_gap flag instead of invented ids

**Decision:** `rule_ids` in each finding are drawn exclusively from the Phase 4 Rego rule id list. When no rule exists, `rule_ids: []` and `rule_gap: true`.

**Why:** Invented Rego rule ids would cause Phase 4 airlock failures and create false compliance signals. The `rule_gap` flag is an honest signal to the Phase 4 owner to create new rules.

---

## 2026-10-04 — Synthetic benchmark is main evidence; live graph is tiny

**Decision:** The primary evidence for Phase 3 correctness is the synthetic enterprise benchmark (200 seeds, budgets {2,4,6}) and the brute-force cross-check (60 seeds). The live graph is tiny (15 nodes, ~9 edges at Phase 2 validation) with few fixable findings, so the live run is supporting evidence only.

**Why:** The CloudGoat scenario was designed to be minimal. Phase 3 is validated on realistic-scale synthetic graphs that use the real Phase 2 node kinds and edge types.

---

## 2026-10-04 — INTERFACE FROZEN

**Frozen public API (do not change without a team message):**

```python
# Findings enumeration
prioritize.findings.enumerate_findings(
    G, catalogue=None, include_unsimulated=False, exclude_aws_managed=None
) -> list[dict]

# Prioritization (production)
prioritize.interdiction.prioritize(
    findings, budget, G, entry_nodes=None, crown_jewels=None
) -> list[str]

prioritize.interdiction.prioritize_detailed(
    findings, budget, G, entry_nodes=None, crown_jewels=None
) -> dict

# Evaluation / comparison
prioritize.evaluate.compare_methods(G, entry, crown, findings, budget) -> dict
prioritize.evaluate.budget_sweep(G, entry, crown, findings, budgets) -> list[dict]
```

**Finding shape (frozen):**
```json
{
  "finding_id": "F-xxxxxxxx",
  "fix_op": "remove_policy_statement | restrict_cidr",
  "target": "<node_id>",
  "target_label": "<label>",
  "covers": [["<u>", "<v>", "<etype>"]],
  "delta": 13.8155,
  "cost": 2,
  "rule_family": "iam_privilege_escalation | net_open_ingress",
  "rule_ids": [],
  "rule_gap": true,
  "simulated": true
}
```

**Catalogue and config frozen.** Changes need a new dated entry here.
