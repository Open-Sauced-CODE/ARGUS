# ARGUS Phase 3 — Prioritization Engine (Network-Interdiction MILP + Baselines)

**Your one-line mission:** take the hacker-movement map from Phase 2 and answer one question: *"we can only fix a few things this cycle, which fixes make the attacker's best route into our crown jewels as hard as possible?"* Prove the answer is correct (against brute force), compare it honestly with two simpler methods, and freeze the function Phase 7 will call.

**Owner:** one person (the Phase 3 owner). Reviewer: someone from another track (suggested: P1 or P3 from Phase 2).
**Duration:** ~10 working days (≈ 2 calendar weeks), same pace as Phase 2.
**Depends on:** Phase 2 interfaces (frozen). You can start the learning and the scaffold *before* Phase 2 is fully merged, using the toy graph.

> **Note on sources.** This file is written from the design docs in the project (v3 design §7.4, Master Guide Phase 3, Phase 2 role files and the Phase 2 code). I could not open the GitHub repo while writing it, so every file path below that already exists in the repo (e.g. `risk/…`, `docs/…`) should be confirmed with `ls` on your branch. Anything marked `UNVERIFIED` must be checked on the real graph before it is trusted.

---

## What you deliver
1. `prioritize/` package: `findings.py`, `interdiction.py`, `naive.py`, `stackelberg_baseline.py`, `evaluate.py`, `run_live.py`
2. `prioritize/fix_catalogue.json` and `prioritize/config.json` (reviewed and frozen at a short team meeting)
3. `prioritize/tests/` (closed-form tests, brute-force cross-check, baseline tests, model-vs-simulator agreement test)
4. `prioritize/notebooks/interdiction_exploration.ipynb` (outputs stripped)
5. `prioritize/comparison.json` (the data behind the dashboard's three-bar budget panel)
6. Documentation: `docs/phase3_decisions.md`, `docs/phase3_validation.md`
7. A written case where the interdiction choice differs from the naive choice, with numbers
8. The frozen function signatures, announced to the team

## What you do NOT touch
- `risk/attack_graph.py` (P1), `risk/pagerank.py` and `risk/simulate.py` (owned by the Phase 2 PageRank owner; if *you* own those too, still treat them as frozen and log any change)
- `risk/*.json` weights (frozen)
- `requirements.txt`, `docker-compose.yml`, `.gitignore`, `.env.example` (P3 owns; PuLP and scipy are already pinned in `requirements.txt`, so you should not need anything new)
- Phase 4 files (`privacy/`, `policy/`)
- `docs/decisions-log.md` and `docs/api-contract.md` (P3 only, at the end; you write `docs/phase3_decisions.md` and hand it over)

---

# PART A — Context

## A1. Phase 3 in plain words
Phase 2 gave us a map where every line means "a hacker at this end can reach that end with probability `p`", and a risk score per node. That tells us **where the danger is**. It does not tell us **what to fix first**, because fixes cost effort and we only have a small budget per cycle.

Phase 3 turns each possible fix into a choice: **fix it or don't** (nothing in between: you can't patch a bucket "68%"). Then it picks the set of fixes, within the budget, that makes the attacker's *cheapest* route into a crown jewel as expensive as possible.

Three pieces of vocabulary:
- **Edge length:** `d = −ln(p)`. A path's probability is the product of its edge probabilities, so its length (sum of `−ln p`) is `−ln(path probability)`. **Short = easy for the attacker, long = hard.** Since `0 < p ≤ 1`, `d ≥ 0`, so shortest-path algorithms are legal.
- **Interdiction:** a fix lengthens one or more edges by an amount `Δ` (e.g. removing an edge makes it effectively infinitely long). The defender picks fixes; the attacker then takes the shortest remaining path. The defender wants to **maximize that shortest path**.
- **Budget:** each fix has a cost `c`; total cost must stay within `B`.

Why this beats "sort by risk score": two fixes with the same high score may sit on *parallel* routes. Fixing one leaves the other open, so the attacker's best route does not change. Interdiction sees the whole graph at once and picks a *cut*, not a list of high scorers.

## A2. Where Phase 3 plugs in
| Direction | What | Detail |
|---|---|---|
| Needs from Phase 2 | `build_attack_graph(session)`, `resolve_entry_nodes(G)`, `get_crown_jewels(G)`, `score_digraph`, `to_percent`, `apply_delta` | all frozen; see the signatures in the Phase 2 role files, A3 |
| Feeds Phase 7 | `prioritize(...)` returns an ordered list of finding IDs; Phase 7 remediates them in that order | Section E3 |
| Feeds Phase 8 | `comparison.json`: three bars (naive, Stackelberg, interdiction) | Section E4 |
| Feeds Phase 4 / 5 | each finding carries `fix_op` (matches Patch-IR op names) and `rule_family` | Section B2 |
| Feeds Phase 10 | the comparison metrics and the budget-sweep numbers | Section B6 |

## A3. The two traps behind the design
1. **Per-edge vs per-fix variables.** One real fix (removing a policy statement) hardens *several* edges at once. Variables must be per fix, not per edge, and no edge may be covered by two fixes (otherwise `Δ`s add up and exceed the cap). The catalogue in this file is built so each edge type has exactly one fix.
2. **Unbounded LP.** If the entry set cannot reach any crown jewel, the shortest-path dual is unbounded and the solver will fail or return garbage. Always check `nx.has_path` over the super-source and super-sink first and return an empty result.

## A4. Honest scope
- The attacker is a **rational single-path attacker** (takes the one most probable route). PPR in Phase 2 is a *flow* score over all routes. Both are heuristics; Phase 2 is for diagnosis, Phase 3 is for the decision. State that difference in the paper.
- Edge probabilities, `Δ` and `c` are heuristic and frozen after review.
- Fixes are assumed independent (no interactions beyond sharing an edge, which we forbid).
- All crown jewels count equally (the attacker picks the easiest one).
- One-shot decision per cycle, not a dynamic game.
- On the live graph the network branch is thin (no EC2 instances ingested), so network fixes will have zero gain. That is expected and correct, not a bug.

---

## A5. Files and ownership (Phase 3)
| Path | Owner |
|---|---|
| `prioritize/__init__.py`, `README.md`, `findings.py`, `interdiction.py`, `naive.py`, `stackelberg_baseline.py`, `evaluate.py`, `run_live.py` | **you** |
| `prioritize/fix_catalogue.json`, `prioritize/config.json` | **you** (team reviews and freezes, Section B3) |
| `prioritize/tests/*`, `prioritize/notebooks/*`, `prioritize/comparison.json` | **you** |
| `docs/phase3_decisions.md`, `docs/phase3_validation.md` | **you** |
| `docs/decisions-log.md`, `docs/api-contract.md` | **P3 only** (you hand over your entries) |
| everything under `risk/`, `privacy/`, `policy/`, `remediate/` | not yours; ask the owner |

## A6. Working rules
```powershell
git checkout main
git pull origin main
git checkout -b phase3/prioritize
# small commits, push at least daily
git fetch origin
git rebase origin/main          # conflicts: STOP and ask the file owner
pytest -q                       # must be green
git push -u origin phase3/prioritize
# open a Pull Request, another person approves, "Squash and merge"
```
- Never commit `.env`, `*.local.json`, keys, or notebook outputs (`nbstripout` should already be installed from Phase 2).
- Phase 3 code is **pure Python over a networkx graph**. Only `run_live.py` talks to Neo4j, and it is read-only.

## A7. Setup (about 20 minutes)
1. Docker Desktop running; Neo4j container up (needed only for Day 7).
2. Pull `main`, activate `.venv`, `pip install -r requirements.txt`.
3. Check the solver: `python -c "import pulp; print(pulp.__version__, pulp.listSolvers(onlyAvailable=True))"`. Use whichever solver is listed (CBC or HiGHS). If the list is empty, tell P3 before going further.
4. Confirm Phase 2 state: `python -c "from risk.pagerank import score_digraph; from risk.simulate import apply_delta; print('ok')"`.
5. Confirm the toy graph exists: `risk/tests/fixtures/toy_graph.py` (or whatever the Phase 2 scaffold named it).

### The safety block (paste at the top of EVERY Antigravity prompt)
```
RULES FOR THIS SESSION (apply to every command you run):
1. Work only inside the repo folder: <PASTE YOUR REPO PATH>. Work only on git branch: phase3/prioritize. Never commit to or push `main`.
2. Only edit or create files under these allowed paths: <PASTE ALLOWED PATHS FOR THIS PROMPT>.
3. AWS: do not run any aws command in this phase.
4. Docker: never run `docker compose down -v`, `docker volume rm`, `docker system prune`, or delete the neo4j_data volume.
5. Neo4j: only read queries (MATCH ... RETURN). Never run CREATE, MERGE, DELETE, SET, REMOVE or DETACH DELETE. Only prioritize/run_live.py may open a Neo4j session at all.
6. Never print, log, paste into files, or commit secrets: values from .env, AWS keys, passwords. Mask secrets as ****.
7. Never edit risk/*.py, risk/*.json, privacy/, policy/, requirements.txt, or any ground-truth file. If you think one needs a change, stop and tell me.
8. Never loosen a test tolerance, delete a test, or change a number in fix_catalogue.json / config.json to make a test pass. If a test fails, show me the failure and your diagnosis.
9. If a command fails, STOP. Show me the exact error and your proposed fix. No destructive fixes or workarounds.
10. Do not assume facts about the graph. If you need a fact, query it or read the code and report the real value.
11. At the end, report: (a) every command you ran, (b) every file created or changed, (c) every assumption you made, (d) anything you could not verify.
```

---

## A8. Team calendar (10 working days)
| Day | Work |
|---|---|
| 0 | Setup (A7); branch; confirm Phase 2 status |
| 1 | Learning (Part C) + paper exercises (B1) |
| 2 | Scaffold; fix catalogue draft; `findings.py` (B2); schedule the catalogue meeting |
| 3 | **Catalogue meeting (30 min, whole team)**; freeze catalogue; start `interdiction.py` (B4) |
| 4 | MILP finished; closed-form tests; no-path handling |
| 5 | Brute-force verifier + random-graph tests; break-a-line test (B5) |
| 6 | Naive + Stackelberg baselines and tests (B6) |
| 7 | `evaluate.py`, comparison, documented differing case, notebook (B7) |
| 8 | Live-graph run (needs Phase 2 merged and Neo4j up); model-vs-simulator check; PR (B8) |
| 9 | Review fixes; Phase 4 / Phase 7 / dashboard coordination; decisions + validation docs |
| 10 | Freeze announcement; buffer; practice Q&A |

**If you slip, cut in this order:** notebook polish → budget-sweep plot → `paths_cut_at_k` metric → extra fix types (key and trust fixes) → Stackelberg polish. **Never cut:** brute-force cross-check, the naive-vs-interdiction case with numbers, the model-vs-simulator agreement test, all tests, the interface freeze.

---

# PART B — Your work, block by block

## Summary: manual vs Antigravity
| Block | You do manually | Antigravity does |
|---|---|---|
| B1 Understand the math (Day 1) | Paper exercises; explain them aloud | Nothing |
| B2 Scaffold + findings + catalogue (Days 2–3) | Decide catalogue numbers; run the meeting | Scaffold, loader, enumeration code (Prompts 3-A, 3-B) |
| B3 Catalogue meeting (Day 3) | Lead it; make the decisions | Checks JSON validity |
| B4 The MILP (Days 3–4) | Review every constraint | Writes code and closed-form tests (Prompt 3-C) |
| B5 Brute-force verification (Day 5) | Interpret any mismatch | Writes the verifier and random tests (Prompt 3-D) |
| B6 Baselines (Day 6) | Decide payoffs; review | Writes code and tests (Prompt 3-E) |
| B7 Evaluation + notebook (Day 7) | Write the explanation of the differing case | Runs, tabulates (Prompt 3-F) |
| B8 Live run + PR (Day 8) | Read the real output | Runs script; audit and git hygiene (Prompts 3-G, 3-H) |
| B9 Docs and coordination (Day 9) | Write decisions; talk to owners | Formatting |
| B10 Freeze (Day 10) | Send the announcement | — |

No AWS work, no Cartography re-run in this phase.

---

## B1. Understand the math first (Day 1, ~3 hours, on paper)

Do the Part C learning first, then these exercises **before any code**.

**Exercise 1 — shortest path as a linear program.**
Graph: `s→a` (d=1), `a→t` (d=1), `s→t` (d=3).
- Shortest path = 2 (via `a`).
- The dual LP: `max π_t` with `π_s = 0`, `π_a − π_s ≤ 1`, `π_t − π_a ≤ 1`, `π_t − π_s ≤ 3`. Solution `π_t = 2`. Check it by hand.
- Now interdict `s→a` with `Δ = 5`: constraint becomes `π_a ≤ 6`, so `π_t ≤ min(7, 3) = 3`. Objective rises from 2 to 3 (attacker now takes the direct edge).
- Interdict both `s→a` and `s→t` with `Δ = 5`: `π_t = min(7, 8) = 7`.
- Write down why more fixes never make the objective worse.

**Exercise 2 — probabilities to lengths.**
Two edges with `p = 0.9` each. `d = −ln 0.9 = 0.1054` each; path length `0.2107`; `exp(−0.2107) = 0.81 = 0.9 × 0.9`. Do the same for a `p = 0.85` edge followed by `p = 0.8`.

**Exercise 3 — why parallel paths break the naive approach (this becomes your documented case).**
Graph (entry `S`, crown jewel `T`, every fix costs 1, every fix removes its edge, budget `B = 2`):
- Path A: `S→A1` (p=0.9, fix α), `A1→A2` (p=0.9, fix β), `A2→T` (p=0.9). Path probability 0.729.
- Path B: `S→B1` (p=0.5, fix γ), `B1→T` (p=0.5). Path probability 0.25.
- Naive picks the two highest-scoring fixes: α and β (both on path A). Path B stays open: attacker success **0.25**, shortest path `−ln 0.25 = 1.386`.
- Interdiction picks α and γ (one fix on each path). Both paths cut; the shortest path becomes about `0.316 + 13.82 = 14.13`; attacker success is about 1e-6.
- Check this by hand. If you can't reproduce the numbers, re-read the lecture before continuing.

**Plain-words glossary**
- `π_v` in the LP is the "distance label" of node `v` (the shortest distance from the source), not the PageRank score. Same Greek letter, different meaning. Call the PPR score `ppr` in code to avoid mixing them up.
- `x_f ∈ {0,1}`: 1 means "apply fix `f`".
- `Δ_f`: how much fix `f` lengthens each edge it covers. `Δ = ln(old p / new p)`; removal uses the cap `Δ_max = −ln(1e-6) = 13.8155` (matches the `1e-6` floor in `simulate.py`).
- Super-source `__S__`: connects to every entry node with length 0. Super-sink `__T__`: every crown jewel connects to it with length 0. The attacker starts anywhere in the entry set and wins at any crown jewel.

---

## B2. Scaffold, fixes and findings (Days 2–3)

### B2.1 What a "finding" is here
A finding = **one applicable fix on the current graph**. It is generated from the graph, not typed by hand.

| Fix | Covers (edges) | Target node | Patch-IR op | Simulated by `apply_delta`? | New p | Δ | Cost |
|---|---|---|---|---|---|---|---|
| Remove the policy statement's dangerous grant | all out-edges of a `stmt` node with etype `CAN_ESCALATE`, `DIRECT_ADMIN`, `CAN_ACCESS` | the `stmt` | `remove_policy_statement` | yes | removed | `delta_max` | 2 |
| Restrict the world-open CIDR on a security group | all in-edges of an `sg` node with etype `RULE_TO_SG` | the `sg` | `restrict_cidr` | yes (factor 0.1) | ×0.1 | `ln(10)` = 2.3026 | 1 |
| Deactivate / rotate an access key *(optional, off by default)* | the `USES_KEY` edge | the `key` | `deactivate_key` (not in Patch-IR yet) | **no** | removed | `delta_max` | 1 |
| Tighten a role's trust policy *(optional, off by default)* | the `CAN_ASSUME` edge into a `role` | the `role` | `tighten_trust` (not in Patch-IR yet) | **no** | ×0.1 | `ln(10)` | 2 |

Why the optional rows are off by default: Phase 7's gate re-scores using `apply_delta`, which ignores ops it does not know, and the Patch-IR vocabulary has no op for them. A recommended fix the gate cannot simulate would never pass the "risk decreased" check. MVP therefore ships the **two rows that are both simulated and in the Patch-IR vocabulary**. If time allows, extending `simulate.py` with two more ops is a small, optional job for its owner (add tests, log it, tell the team; the function signature does not change).

**Cost units** are relative effort: 1 = a single config toggle, 2 = needs review or touches several things. Heuristic, frozen after the meeting. Keep coarse integers.

**Edge-disjointness rule:** each edge etype is covered by at most one fix type, so no edge is covered twice. Add a test that asserts this on every graph you build.

### B2.2 Finding record (frozen shape)
```json
{
  "finding_id": "F-3fa9c2d1",
  "fix_op": "remove_policy_statement",
  "target": "<real node id>",
  "target_label": "<label>",
  "covers": [["<u>", "<v>", "CAN_ESCALATE"]],
  "delta": 13.8155,
  "cost": 2,
  "rule_family": "iam_privilege_escalation",
  "simulated": true
}
```
- `finding_id` = `"F-" + first 8 hex of sha1(fix_op + "|" + target)`. Deterministic across runs (never use counters or Python's `hash`).
- `rule_family` values: `iam_privilege_escalation`, `iam_data_access`, `net_open_ingress`, `key_active`, `trust_overbroad`. Phase 4 owner maps these to real Rego rule IDs (the mutation engine already uses `cis.sg_open_ingress`; confirm names with them). Do not invent Rego rule IDs yourself.
- Real node ids appear here. That is fine locally; anything sent to a model must go through the Phase 4 airlock first.

### B2.3 Files to create
```
prioritize/
├── __init__.py
├── README.md                  # one paragraph
├── config.json                # budget default, Stackelberg parameters, k for critical paths
├── fix_catalogue.json         # Section E1
├── findings.py                # load catalogue, enumerate_findings(G)
├── interdiction.py            # build_milp, solve, prioritize, prioritize_detailed
├── naive.py                   # greedy by PPR score
├── stackelberg_baseline.py    # multiple-LP baseline
├── evaluate.py                # shared evaluator, brute force, comparison
├── run_live.py                # read-only Neo4j run, writes comparison.json
├── notebooks/interdiction_exploration.ipynb
└── tests/
    ├── __init__.py
    ├── fixtures/graphs.py     # toy, parallel-paths, diamond, random generator
    ├── test_catalogue.py
    ├── test_findings.py
    ├── test_interdiction.py
    ├── test_bruteforce.py
    ├── test_naive.py
    ├── test_stackelberg.py
    ├── test_agreement.py
    └── test_no_neo4j_outside_run_live.py
```

### Prompt 3-A — scaffold
Allowed paths: `prioritize/`
```
[PASTE SAFETY BLOCK]

TASK: Create the empty skeleton of the prioritize/ package so the rest of Phase 3 can be built file by file.
Create exactly the files listed in "B2.3 Files to create" of docs/ARGUS_Phase3_Prioritization_Engine.md (copy that file into docs/ first if it is not there; do not edit any other doc).
- Every .py file gets a module docstring and stubs only (raise NotImplementedError).
- fix_catalogue.json and config.json: copy the JSON from Section E1 and E2 of that document exactly.
- tests/fixtures/graphs.py: implement these builders using raw networkx only, every node with kind and label, every edge with p and etype:
  a) parallel_paths(): the Exercise 3 graph from section B1 (entry S, crown jewel T; edges S->A1 p=0.9, A1->A2 p=0.9, A2->T p=0.9, S->B1 p=0.5, B1->T p=0.5) with a list of fixes given as dicts in the finding shape from B2.2: alpha covers (S,A1), beta covers (A1,A2), gamma covers (S,B1); each cost 1, delta 13.8155.
  b) exercise1(): s->a d=1, a->t d=1, s->t d=3 expressed as p = exp(-d) edges.
  c) random_graph(seed, n_nodes, n_edges, n_fixes): reproducible random DAG with p in [0.2, 0.95], one entry, one or two crown jewels, fixes covering disjoint edges with costs in {1,2,3} and delta in {2.3026, 13.8155}.
Then run: python -c "import prioritize.findings, prioritize.interdiction, prioritize.naive, prioritize.stackelberg_baseline, prioritize.evaluate", validate both JSON files parse, and run pytest -q (zero tests must collect without error).
Commit on phase3/prioritize with message "phase3: scaffold prioritize/ package". Do not push main.
```

### Prompt 3-B — findings enumeration
Allowed paths: `prioritize/findings.py`, `prioritize/tests/test_catalogue.py`, `prioritize/tests/test_findings.py`
```
[PASTE SAFETY BLOCK]

TASK: Implement prioritize/findings.py from sections B2.1 and B2.2 of docs/ARGUS_Phase3_Prioritization_Engine.md.
- load_catalogue(path=None) reads prioritize/fix_catalogue.json (no numbers hard-coded in Python except default fallbacks documented in a comment).
- enumerate_findings(G, catalogue=None, include_unsimulated=False) -> list[dict] in the finding shape from B2.2. Rules: for every node of kind "stmt" with at least one out-edge whose etype is CAN_ESCALATE, DIRECT_ADMIN or CAN_ACCESS, create one remove_policy_statement finding covering ALL such out-edges. For every node of kind "sg" with at least one in-edge of etype RULE_TO_SG, create one restrict_cidr finding covering all those in-edges. Key and trust fixes only if include_unsimulated=True and the catalogue marks them enabled.
- finding_id is "F-" + first 8 hex chars of sha1(fix_op + "|" + target). Sorted output (by finding_id) so results are deterministic.
- Never mutate G.
Tests:
- test_catalogue.py: JSON parses; every delta > 0; every cost is a positive integer; delta_max equals -ln(1e-6) within 1e-3; no etype appears in two different fixes (edge-disjointness); every fix with simulated=true has fix_op in {remove_policy_statement, restrict_cidr}.
- test_findings.py: on risk/tests/fixtures/toy_graph.py the output contains exactly one finding (the STM statement) covering both STM->ADMIN_EQUIV and STM->BUCKET; ids are stable across two calls; no edge appears in two findings; the input graph is unchanged.
Run pytest and show output. Do not touch files outside the allowed paths.
```

---

## B3. The catalogue meeting (Day 3, 30 minutes) — you lead it

**Why:** `Δ` and `c` are judgement, like the Phase 2 weights. They must be justified, reviewed and frozen so nobody tunes them to make a demo look good.

**Before the meeting (Day 2):** send everyone `fix_catalogue.json` and the table in B2.1. Ask each person to pick two numbers to challenge.

**Agenda**
1. (5 min) Recap: Δ and cost are heuristic; we say so in the paper.
2. (15 min) Each person challenges two numbers. Anything nobody can justify becomes a coarse value (cost 1/2/3, factor 0.1) with the note "heuristic".
3. (5 min) Confirm the default catalogue contains only the two simulated, Patch-IR-aligned fixes. Decide whether the optional rows stay off.
4. (5 min) **Freeze.** After this, a change needs an entry in `docs/phase3_decisions.md` with the reason and who approved it.

**Also agree at the meeting:** the default budget in `config.json` (suggested `B = 3`, about one to two fixes), and the Phase 4 owner's `rule_family` → Rego rule mapping.

Watch out: AI tools propose fake-precise numbers and fake citations. Keep coarse values. Never cite a paper you haven't read.

---

## B4. The MILP (Days 3–4)

### Formulation (what the code must do)
Given graph `G` (edges with `p`), entry set `E`, crown-jewel set `C`, findings `F` (each with `covers`, `delta`, `cost`), budget `B`:

- Variables: `π_v ≥ 0` continuous for every node plus `__S__` and `__T__`; `x_f ∈ {0,1}` for every finding.
- Objective: **maximize `π_T − π_S`**.
- `π_S = 0`.
- For every graph edge `(i,j)`: `π_j − π_i ≤ −ln(p_ij) + Σ_{f covers (i,j)} Δ_f · x_f`.
- For every entry `e ∈ E`: `π_e − π_S ≤ 0`. For every crown jewel `c ∈ C`: `π_T − π_c ≤ 0`.
- Budget: `Σ_f cost_f · x_f ≤ B`.

Why it works: for fixed `x` the max over `π` is exactly the shortest-path length from `__S__` to `__T__` under the modified edge lengths (LP duality). Maximizing over `x` as well gives the best set of fixes.

Why `π ≥ 0` is safe: distances from the source are ≥ 0 because edge lengths are ≥ 0. It also stops the solver wandering off to −∞ for nodes that don't matter.

### Outputs
- `build_and_solve(G, entry, crown, findings, budget) -> dict` with `selected` (set of finding ids), `objective` (shortest path length after fixes), `baseline_objective` (budget-0 shortest path), `status`, `solve_seconds`.
- `prioritize(findings, budget, G, entry_nodes=None, crown_jewels=None) -> list[str]` ordered finding ids (frozen, Section E3).
- `prioritize_detailed(...) -> dict` the richer record for the dashboard and Phase 7.

### Ordering rule (a MILP returns a set, not an order)
1. Selected fixes first, ordered by **solo gain** (objective with only that fix applied minus the baseline objective), descending; ties broken by lower cost, then by finding id.
2. Unselected fixes after them, ordered by solo gain per unit cost, descending, ties by finding id.
Document this in the decisions file; reviewers always ask.

### Edge cases the code must handle
- No path from entry to crown jewels: return empty `selected`, `objective = inf` (or `None`), and do **not** call the solver.
- Entry nodes not in `G`: filter them out (like `score_digraph` does); if none remain, raise `ValueError`.
- A crown jewel equal to an entry: objective 0; no fix can help; return empty selection.
- Budget 0: empty selection, objective equals the baseline.
- Findings that cover edges not in `G`: raise `ValueError` (stale finding).
- Two findings covering the same edge: raise `ValueError` (edge-disjointness).
- Never mutate `G`.

### Prompt 3-C — the MILP
Allowed paths: `prioritize/interdiction.py`, `prioritize/evaluate.py` (only the function `attack_length`), `prioritize/tests/test_interdiction.py`
```
[PASTE SAFETY BLOCK]

TASK: Implement prioritize/interdiction.py using sections B4 and E3 of docs/ARGUS_Phase3_Prioritization_Engine.md as the specification, with PuLP.
Hard requirements:
- Edge length is -ln(p). Never use p directly as a length.
- Variables: pi (continuous, lowBound=0) for every node plus "__S__" and "__T__"; x binary per finding. Variable names must be index-based (no ARNs in names).
- Objective: maximize pi["__T__"] - pi["__S__"]; constraint pi["__S__"] == 0.
- One constraint per graph edge: pi[v] - pi[u] <= -ln(p) + sum(delta_f * x_f for findings f covering (u,v)).
- Zero-length edges __S__ -> each entry node and each crown jewel -> __T__ (as constraints).
- Budget constraint sum(cost * x) <= budget.
- Before solving, check nx.has_path from any entry to any crown jewel on G; if none, return empty selection with objective None and do not call the solver.
- Raise ValueError for: findings covering edges not in G, two findings covering the same edge, no valid entry nodes.
- G is never mutated. No Neo4j, no file writes.
- Implement attack_length(G, entry, crown, selected_ids, findings) in prioritize/evaluate.py: networkx Dijkstra on a copy where each covered edge length is -ln(p) + delta for selected findings; returns the shortest S->T length (use a temporary super-source/sink); do not use PuLP in this function. This is the independent evaluator.
- Implement prioritize(findings, budget, G, entry_nodes=None, crown_jewels=None) and prioritize_detailed(...) with the ordering rule from section B4. Entry and crown defaults come from risk.attack_graph.resolve_entry_nodes and get_crown_jewels.
Tests (prioritize/tests/test_interdiction.py), all using tests/fixtures/graphs.py:
1. Budget 0 -> selected empty and objective equals nx dijkstra shortest path (tolerance 1e-9).
2. exercise1(): with one fix on s->a (delta 5, cost 1) and budget 1, objective == 3.0 (tolerance 1e-9); with a second fix on s->t (delta 5) and budget 2, objective == 7.0.
3. parallel_paths(), budget 2: selected set contains gamma and exactly one of alpha/beta; objective is about 14.13 (assert > 14.0 and < 14.2). Naive-style choice {alpha, beta} gives attack_length about 1.386 (assert abs(value - (-ln 0.25)) < 1e-6).
4. Objective is non-decreasing as budget goes 0,1,2,3.
5. No path: returns empty selection, no exception, objective None.
6. Input graph unchanged (compare edges with data before and after).
7. Findings covering an unknown edge or the same edge twice raise ValueError.
Run pytest and show output. Do not change any number in a test to make it pass; if a test fails, report it.
```

### Your mandatory code review (~45 min)
☐ Edge length uses `−ln(p)` everywhere (search for `math.log` and check the sign)
☐ `π` variables are continuous; `x` variables are `Binary` (not `Continuous`)
☐ Objective is **maximize** `π_T − π_S`; `π_S` pinned to 0
☐ Constraint direction is `π_j − π_i ≤ length + Δ·x` (not `≥`)
☐ Super-source and super-sink constraints present and of length 0
☐ Budget constraint uses cost-weighted sum and `≤`
☐ No-path check happens **before** the solver is called
☐ Each edge covered by at most one finding, enforced with an error
☐ `Δ` and costs come from the catalogue, not literals in code
☐ `G` is never mutated; no Neo4j import in this file
☐ You can explain, for Exercise 1, why the answer is 3 with one fix and 7 with two
If you can't explain the last one, do not sign off.

**What Antigravity is likely to get wrong here:** uses `p` as a length, flips the constraint direction, forgets the super-source and super-sink, leaves `x` continuous, skips the no-path check (unbounded LP), adds `Δ`s of two findings on one edge, hard-codes `Δ`, or loosens a tolerance to make a test pass.

---

## B5. Brute-force verification (Day 5, ~2 hours) — your strongest evidence

**Why:** a MILP that "returns something" proves nothing. For small instances you can try *every* subset of fixes and take the best. If the MILP's objective equals the brute-force optimum on many random graphs, the formulation is right.

**Algorithm (independent of PuLP):** for every subset `S` of findings with total cost ≤ `B`, compute `attack_length(G, entry, crown, S, findings)` with Dijkstra; the optimum is the maximum. With ≤ 14 findings that is ≤ 16,384 subsets, fast.

### Prompt 3-D — brute force and random tests
Allowed paths: `prioritize/evaluate.py` (add `brute_force_best`), `prioritize/tests/test_bruteforce.py`
```
[PASTE SAFETY BLOCK]

TASK: In prioritize/evaluate.py add brute_force_best(G, entry, crown, findings, budget) -> (best_objective, list_of_optimal_sets). It enumerates every subset of findings with total cost <= budget (itertools), evaluates each with attack_length (Dijkstra, no PuLP), and returns the max objective and all subsets achieving it (within 1e-9). Refuse (raise ValueError) if there are more than 16 findings.
Write prioritize/tests/test_bruteforce.py:
1. For 50 seeds (0..49) of random_graph(seed, n_nodes=9, n_edges=16, n_fixes=8): the MILP objective from interdiction.build_and_solve equals brute_force_best objective within 1e-6 for budgets 1, 3 and 5. Compare OBJECTIVE VALUES, not the chosen sets (ties are normal). Skip seeds where there is no entry->crown path (but count and assert that at least 40 of 50 seeds were not skipped).
2. The MILP's chosen set, evaluated with attack_length, reproduces the MILP objective within 1e-6.
3. The MILP's chosen set has total cost <= budget.
Then do this: in a scratch copy of interdiction.py, flip the budget constraint to ">=" and then, separately, remove the super-sink constraints; show that at least one test fails each time; restore the file. Do not leave any scratch change in the repo.
Report any seed where the MILP and brute force disagree, with the seed number and both objective values. Do not change tolerances.
```

**Your checks**
- Run the random test, read one failing-by-design case from the break-a-line step with your own eyes.
- If MILP and brute force disagree on any seed, **do not loosen anything.** Debug order: (1) is `attack_length` modelling the same edge lengths as the MILP, (2) edge-disjointness violated in the random generator, (3) a crown jewel or entry node missing from the graph, (4) solver tolerance (try a tighter tolerance only if values differ by ~1e-6 scale), (5) the constraint direction.

---

## B6. Baselines (Day 6)

Three methods are compared on the same graph, same budget, same evaluator.

### B6.1 Naive baseline — `naive.py`
- Score of a finding = PPR score of its target node, `score_digraph(G, entry)[target]` (or `to_percent`).
- Sort findings by score descending (ties: lower cost, then id). Walk down the list; take a finding if it still fits in the remaining budget, otherwise skip it and continue.
- Returns the chosen set and the ordered list.

### B6.2 Stackelberg baseline — `stackelberg_baseline.py` (comparison only; never production)
The v2 design's randomized-coverage game, kept as a labelled baseline.
- Targets = findings. Coverage `x_i ∈ [0,1]` with `Σ cost_i x_i ≤ B`.
- Attacker payoff if target `i` is uncovered: `Ra_i = ppr_percent[target_i]`. If covered: `Pa_i = −pa_ratio · Ra_i` (`pa_ratio` in `config.json`, suggested 0.2).
- Defender payoffs (zero-sum): covered `Rd_i = −Pa_i`; uncovered `Pd_i = −Ra_i`.
- Attacker utility `Ua(i) = (1−x_i)·Ra_i + x_i·Pa_i`. Defender utility `Ud(i) = x_i·Rd_i + (1−x_i)·Pd_i`.
- **Multiple-LP method:** for each candidate attacker target `i*`: maximize `Ud(i*)` subject to `Ua(i*) ≥ Ua(i)` for all `i`, `0 ≤ x ≤ 1`, `Σ cost·x ≤ B`. Skip infeasible LPs. Take the best across all `i*`.
- To compare with the binary methods, **round** the fractional solution: sort by `x_i` descending and take findings that fit in the budget (same greedy rule as naive). State clearly in the dashboard and paper that this rounding is for comparison only; the fractional `x` itself has no operational meaning for a patch.

**Hand-check examples (use them as tests):**
- Two targets `R = (10, 10)`, unit costs, `B = 1`: symmetric, so `x = (0.5, 0.5)`.
- Two targets `R = (10, 5)`, `Pa = 0`, unit costs, `B = 1`: equalize `10(1−x1) = 5(1−x2)` with `x1 + x2 = 1`, giving `x1 = 2/3`, `x2 = 1/3`, attacker utility `10/3`.

### Prompt 3-E — baselines
Allowed paths: `prioritize/naive.py`, `prioritize/stackelberg_baseline.py`, `prioritize/tests/test_naive.py`, `prioritize/tests/test_stackelberg.py`
```
[PASTE SAFETY BLOCK]

TASK: Implement prioritize/naive.py and prioritize/stackelberg_baseline.py from section B6 of docs/ARGUS_Phase3_Prioritization_Engine.md.
Hard requirements:
- naive: score = risk.pagerank.score_digraph(G, entry)[finding["target"]]; sort descending (ties: lower cost, then finding_id); greedy fill; skip a finding that does not fit and continue. Returns {"selected": [...], "ordered": [...]}.
- stackelberg_baseline: the multiple-LP method with PuLP exactly as in B6.2 (one LP per candidate attacker target; skip infeasible LPs; pick best defender utility). Payoffs and pa_ratio come from prioritize/config.json. Provide solve_stackelberg(findings, ra, budget, pa_ratio) -> dict with fractional "x" per finding_id and "best_target", plus round_to_binary(x, findings, budget) using the same greedy rule as naive. The module docstring must say: COMPARISON BASELINE ONLY, not for production.
Tests:
- naive: respects budget; skips an unaffordable finding and still takes a later affordable one; deterministic tie-breaking; does not mutate G.
- stackelberg: for ra = (10,10), unit costs, B=1 -> x = (0.5, 0.5) within 1e-6; for ra = (10,5), pa_ratio = 0 -> x = (2/3, 1/3) within 1e-6; every x in [0,1]; sum(cost*x) <= B + 1e-9; at the returned solution the attacker's best response (max Ua) is attained at best_target within 1e-6.
Run pytest and show output. Do not change tolerances or expected values.
```

---

## B7. Evaluation, the differing case, notebook (Day 7)

### B7.1 The shared evaluator (`evaluate.py`)
For any method's selected set (same graph, same budget):
- `objective` = `attack_length(...)`.
- `residual_attack_prob` = `exp(−objective)` (the most probable remaining attack route; floors near 1e-6 for fully cut routes).
- `ppr_check`: apply the set with `risk.simulate.apply_delta` (only for simulated fix types), re-run `score_digraph`, and report the change in score of each crown jewel. Interdiction should not make any crown jewel *worse*.
- `paths_cut_at_k` (optional, k from `config.json`, default 5): take the top-k most probable simple paths (`nx.shortest_simple_paths` on `−ln p` lengths from the super-source to the super-sink) and count how many are cut by the set (a path is cut if it uses an edge covered by a selected finding). Good evidence for the "time-to-remediate top-k critical paths" metric in Phase 10.

### B7.2 The documented differing case (required)
1. **Synthetic case (guaranteed):** the Exercise 3 graph. Budget 2. Naive picks `{α, β}` → residual 0.25. Interdiction picks `{α, γ}` (or `{β, γ}`) → residual about 1e-6. Put the numbers in the notebook and in `docs/phase3_validation.md`, with the reason in your own words (parallel routes: the second fix on the same route buys nothing).
2. **Live-graph case (if one exists):** run all three on the real graph. If they agree, say so honestly. Do **not** edit weights or the catalogue to manufacture a difference.

### B7.3 Budget sweep (recommended, cheap)
Run interdiction and naive for `B = 0,1,2,3,4,5,6` and record the objective and residual probability per budget. This gives the paper a curve ("how much risk reduction per unit of effort") and shows where adding budget stops helping.

### B7.4 `comparison.json` shape (for the dashboard's three-bar panel; frozen in Section E4)

### Prompt 3-F — comparison runner and notebook
Allowed paths: `prioritize/evaluate.py`, `prioritize/notebooks/`, `prioritize/tests/test_agreement.py`
```
[PASTE SAFETY BLOCK]

TASK: Implement the comparison utilities in prioritize/evaluate.py from section B7 and E4 of docs/ARGUS_Phase3_Prioritization_Engine.md, then build the notebook.
1. compare_methods(G, entry, crown, findings, budget) -> dict following the comparison.json shape in section E4: for methods "naive", "stackelberg" (rounded, with the fractional x also included under "fractional_x"), and "interdiction", record selected ids, objective (attack_length), residual_attack_prob, ppr_crown_jewel_delta (via risk.simulate.apply_delta + risk.pagerank.score_digraph; only apply findings whose simulated flag is true), and paths_cut_at_k.
2. budget_sweep(G, entry, crown, findings, budgets) -> list of dicts for naive and interdiction.
3. tests/test_agreement.py (model vs simulator): for every simulated fix type, build a tiny graph with one covered edge of known p; apply risk.simulate.apply_delta with the matching op; assert the new p equals exp(-(-ln(p) + delta)) within 1e-9 for restrict_cidr, and that the edge is gone for remove_policy_statement. This proves the MILP's delta model matches what the Phase 7 gate will actually simulate.
4. Notebook prioritize/notebooks/interdiction_exploration.ipynb on the parallel_paths() graph: show the three methods side by side at budget 2, a budget sweep table, and markdown cells explaining each result in plain words. Do not store outputs in the committed notebook (nbstripout handles it).
Run pytest and show output. Do not edit risk/. If test_agreement fails because risk/simulate.py behaves differently from the spec, STOP and report; do not edit simulate.py.
```

---

## B8. Live-graph run and the pull request (Day 8)

### B8.1 `run_live.py` (read-only)
- Uses `risk.graph_loader.get_driver()` and `risk.attack_graph.build_attack_graph(session)` (read-only).
- Resolves entry and crown jewels, enumerates findings, runs the three methods at the default budget, writes `prioritize/comparison.json` and prints the table.
- Prints the number of findings, the solve time, and the baseline vs after objective.
- Must not write to Neo4j or print secrets.

### B8.2 What you should see on the CloudGoat account (`UNVERIFIED` until you run it)
- A `remove_policy_statement` finding for Raynor's escalation statement, with a large solo gain.
- Possibly findings for the test-bucket access statements (`CAN_ACCESS`) if Phase 2's builder created them.
- Network findings (if any) with zero solo gain, because nothing valuable sits behind the security groups. They rank last; that is correct.
- After applying the chosen set with `apply_delta`, `ADMIN_EQUIV`'s PPR score drops (cross-check with Phase 2).
If the Raynor finding is missing, the cause is upstream: check that `CAN_ESCALATE` edges exist in the Phase 2 graph (P1's edge-count report) before touching Phase 3.

### Prompt 3-G — consistency audit (before every PR)
Allowed paths: none (read-only)
```
[PASTE SAFETY BLOCK]

TASK: Read-only audit. Do not edit anything.
1. Search prioritize/*.py for any import of neo4j or risk.graph_loader outside prioritize/run_live.py; report any.
2. Search prioritize/*.py for CREATE, MERGE, DELETE, SET, REMOVE inside strings; report any.
3. Search prioritize/*.py for hard-coded ARNs, 12-digit account ids and the CloudGoat suffix; report any.
4. Search prioritize/*.py for numeric literals used as delta, cost or budget that are not read from fix_catalogue.json / config.json (allow documented defaults); report any.
5. Confirm every edge length uses math.log(p) with a negative sign (list each occurrence).
6. Compare prioritize/fix_catalogue.json against the table in docs/ARGUS_Phase3_Prioritization_Engine.md section B2.1; report any difference.
7. Run pytest -q and report pass/fail counts.
8. Report git status: files changed, and whether any file outside prioritize/ and docs/phase3_*.md changed.
```

### Prompt 3-H — git hygiene before the PR
```
[PASTE SAFETY BLOCK]

TASK: Prepare my branch for a pull request.
1. Show `git status` and `git diff --stat`. If any file outside prioritize/ and docs/phase3_*.md changed, stop and tell me.
2. `git fetch origin` then `git rebase origin/main`. If there are conflicts, STOP and show me the conflicting files; do not resolve automatically.
3. Run pytest -q; must be green.
4. Make sure no .env, *.local.json, key, or notebook output is staged (git diff --cached --name-only).
5. Commit with message "phase3/prioritize: <what>", push the branch (never main), and print the URL where I can open a pull request.
```
Open PR `phase3/prioritize` → `main`. Another person reviews it (checklist in B8.3).

### B8.3 Reviewer checklist (for the person who reviews your PR)
☐ Edge length is `−ln(p)`, constraint directions correct
☐ `x` binary, budget constraint present, no-path handled before solving
☐ Catalogue numbers come from JSON, not code; JSON matches the frozen table
☐ Brute-force cross-check test exists and passes on 50 seeds
☐ Naive-vs-interdiction case documented with numbers
☐ `test_agreement.py` passes (model matches `apply_delta`)
☐ No Neo4j outside `run_live.py`; no write Cypher
☐ No file outside `prioritize/` and `docs/phase3_*.md` changed
☐ Tests assert behaviour (not just "no exception")

---

## B9. Docs and coordination (Day 9)

1. **`docs/phase3_decisions.md`:** minimum entries, each with date, decision, why, alternatives:
   - Interdiction MILP primary; Stackelberg kept as labelled comparison-only baseline
   - Variables per fix, edge-disjoint catalogue (why)
   - `Δ_max = −ln(1e-6)` to match the simulator floor
   - MVP catalogue = fixes both simulated by `apply_delta` and in the Patch-IR vocabulary; optional fixes off by default
   - Super-source over entry set, super-sink over crown jewels; attacker picks the easiest crown jewel
   - Ordering rule (solo gain, then gain per cost)
   - `prioritize()` takes the graph as a required third argument (extends the master-guide signature; tell the team)
   - Naive baseline = greedy by PPR of target node with skip-if-unaffordable
   - Stackelberg payoffs, `pa_ratio`, rounding rule
   - Catalogue frozen after the meeting; coarse integer costs
   - Anything that surprised you on the live graph
2. **Phase 4 owner:** agree the `rule_family` → Rego rule ID mapping; give them the finding shape (B2.2).
3. **Phase 7 / dashboard owner (Role D):** show them `prioritize_detailed()` output and `comparison.json`; ask them to confirm the field names against the dashboard's mock data (P3 puts the final shape into `docs/api-contract.md`, marked "PROPOSED — pending Role D" until confirmed).
4. Hand your decisions entries to P3 for `docs/decisions-log.md`.
5. **`docs/phase3_validation.md`:** PASS/FAIL line for each acceptance check in Part D, plus the Exercise 3 numbers, the live-graph table, the budget-sweep table and the solve time.

## B10. Freeze and announce (Day 10)
Post in the team channel:
> **Phase 3 interface FROZEN.** `prioritize.interdiction.prioritize(findings, budget, G, entry_nodes=None, crown_jewels=None) -> list[str]` and `prioritize_detailed(...)`, `prioritize.findings.enumerate_findings(G, catalogue=None, include_unsimulated=False) -> list[dict]` (shape in `docs/phase3_decisions.md`) will not change without a team message. `prioritize/fix_catalogue.json` and `prioritize/config.json` are frozen; changes need a decisions entry. Results are in `docs/phase3_validation.md`. Phase 7 can build against these.

---

# PART C — What to learn (and be able to explain)

## C1. Minimum (~4 hours)
| Topic | Where | Time |
|---|---|---|
| Shortest paths and Dijkstra with non-negative lengths | any algorithms text (CLRS ch. 24) or a Dijkstra lecture; you probably know this already | 20 min |
| Linear programming basics and duality | MIT 6.251J / a university LP lecture on duality; search "shortest path linear program dual" | 60–90 min |
| Integer programming and branch and bound, in words | one intro lecture; PuLP docs explain `Binary` variables | 40 min |
| PuLP | PuLP "Case Studies" tutorial (a blending problem is enough for `LpProblem`, `LpVariable`, `+=`) | 40 min |
| Network interdiction | Israeli and Wood, "Shortest-path network interdiction" (Networks, 2002); and a survey such as Smith and Song, "A survey of network interdiction models and algorithms" (EJOR, 2020). **Verify exact titles and years before citing.** | 60 min |
| Stackelberg security games | Conitzer and Sandholm, "Computing the optimal strategy to commit to" (EC 2006, the multiple-LP method); Tambe, *Security and Game Theory* (intro chapters). **Verify citations before using them in the paper.** | 40 min |

(Search the titles; I could not confirm current links.)

## C2. Your deeper part (~2 hours)
- Why a binary decision needs integer programming, and what the LP relaxation would give you (fractional fixes, no operational meaning).
- Why the interdiction MILP is solved fast here (tens of fixes, small graph) and where it would stop scaling.
- Why Stackelberg suits randomized inspection problems but not patching.
- Read `risk/simulate.py` and the Phase 2 decisions note so the Δ model matches what the gate will simulate.

## C3. Explain it in 60 seconds
"Phase 3 decides what to fix first. We turn every edge probability into a length, minus log p, so the attacker's most probable route is the shortest path. Each fix lengthens some edges. We pick the budget-limited set of fixes that makes the attacker's shortest route as long as possible, which is a mixed-integer program built from the dual of the shortest-path LP. I checked it against brute force on 50 random graphs, and compared it with sorting by risk score and with a Stackelberg game."

## C4. Questions you must be able to answer
| Question | Short answer |
|---|---|
| Why not just sort by risk score? | High-scoring fixes can sit on parallel routes; fixing one leaves the other open. Interdiction optimizes the cut, not the list. |
| Why `−ln p` for the length? | Path probability is a product; logs turn it into a sum; the minus sign turns "most probable" into "shortest". Lengths are ≥ 0 so Dijkstra is valid. |
| Why binary, not fractional, fixes? | A finding is either patched or not; "68% patched" has no meaning, so the Stackelberg fractional coverage is a mismatch. |
| What is the dual of the shortest-path LP? | Maximize `π_t − π_s` subject to `π_j − π_i ≤ d_ij`; at the optimum `π_t` equals the shortest-path length. |
| What does `Δ` mean? | How much a fix lengthens an edge, `ln(old p / new p)`; removal is capped at `−ln(1e-6)`. |
| What if no attack path exists? | The LP is unbounded, so we check reachability first and return an empty result. |
| How do you know the MILP is right? | Closed-form hand examples, plus equality with brute-force enumeration on 50 random graphs, plus an independent Dijkstra evaluator. |
| Why is Stackelberg still in the project? | As a labelled baseline so the dashboard can show where it agrees and diverges; its rounded output is for comparison only. |
| Why keep PPR if you have interdiction? | PPR gives a flow score over all routes for diagnosis and for the gate's regression check; interdiction assumes one rational attacker route and gives the decision. |
| What are the limitations? | Heuristic p, Δ and cost; single-route attacker; independent fixes; equal crown-jewel weights; one-shot not dynamic. |
| How does this connect to Phases 4 and 7? | Each finding carries the Patch-IR op and a rule family; Phase 7 remediates in the returned order and re-scores with `apply_delta`. |
| Runtime? | Milliseconds at this scale (tens of fixes); the MILP is NP-hard in general but trivial here. |

---

# PART D — Acceptance criteria and checklist (Definition of Done)

## D1. Acceptance criteria (all must hold)
1. MILP objective equals brute-force optimum within 1e-6 on at least 40 usable random graphs for budgets 1, 3 and 5.
2. Closed-form examples (Exercise 1: 3.0 and 7.0; Exercise 3: about 14.13 vs 1.386) pass as tests.
3. Budget monotonicity: objective never decreases as budget grows.
4. A documented case where interdiction beats naive, with numbers and a plain-words explanation.
5. `test_agreement.py` passes: the Δ model matches `apply_delta` for every simulated fix type.
6. On the live graph: the Raynor escalation finding is selected when the budget covers its cost, and after `apply_delta` the `ADMIN_EQUIV` PPR score drops (or the live-graph result is honestly reported if different). Solve time well under a second.
7. All tests green and shown to fail when the formulation is deliberately broken (budget flipped, super-sink removed).
8. No Neo4j outside `run_live.py`; no write Cypher; no hard-coded ARNs, suffix, Δ or costs.
9. Frozen signatures announced; Phase 4 and Role D acknowledged the finding shape and `comparison.json`.

## D2. Checklist
☐ Both paper exercises reproduced (Exercise 1 and Exercise 3 numbers)
☐ Solver availability confirmed (`pulp.listSolvers`)
☐ Catalogue and config drafted, reviewed at the meeting, frozen, outcome recorded
☐ `findings.py`: deterministic ids, edge-disjoint, tests green
☐ `interdiction.py` implemented; review checklist B4 all ticked
☐ Closed-form tests pass
☐ Brute-force cross-check passes on random graphs; break-a-line test shows tests fail when the code is broken
☐ `naive.py` and `stackelberg_baseline.py` implemented, labelled comparison-only where relevant, hand-check tests pass
☐ `evaluate.py` comparison and budget sweep working; `comparison.json` generated
☐ `test_agreement.py` passes
☐ Differing case documented with numbers
☐ Live-graph run done; results recorded; Raynor finding checked
☐ Notebook committed (outputs stripped)
☐ PR merged after another person's review
☐ `docs/phase3_decisions.md` and `docs/phase3_validation.md` written; entries handed to P3
☐ Phase 4 owner and Role D confirmed shapes
☐ Freeze announcement sent
☐ You can answer the questions in C4 without notes

---

# PART E — Reference material

> Reference only. Property names and graph shapes depend on the Phase 2 graph; confirm against `docs/phase2_verified_facts.md` and the real output before trusting anything.

## E1. `prioritize/fix_catalogue.json` (initial values; reviewed and frozen at the meeting)
```json
{
  "delta_max": 13.8155,
  "notes": "delta = ln(old_p / new_p). delta_max = -ln(1e-6), matching the P_FLOOR in risk/simulate.py. Costs are relative effort units: 1 = config toggle, 2 = needs review. Heuristic; frozen after review.",
  "fixes": {
    "remove_policy_statement": {
      "scope": "stmt",
      "covers_etypes": ["CAN_ESCALATE", "DIRECT_ADMIN", "CAN_ACCESS"],
      "direction": "out",
      "new_p_factor": 0.0,
      "delta": "delta_max",
      "cost": 2,
      "rule_family": "iam_privilege_escalation",
      "simulated": true,
      "enabled": true
    },
    "restrict_cidr": {
      "scope": "sg",
      "covers_etypes": ["RULE_TO_SG"],
      "direction": "in",
      "new_p_factor": 0.1,
      "delta": 2.3026,
      "cost": 1,
      "rule_family": "net_open_ingress",
      "simulated": true,
      "enabled": true
    },
    "deactivate_key": {
      "scope": "key",
      "covers_etypes": ["USES_KEY"],
      "direction": "out",
      "new_p_factor": 0.0,
      "delta": "delta_max",
      "cost": 1,
      "rule_family": "key_active",
      "simulated": false,
      "enabled": false
    },
    "tighten_trust": {
      "scope": "role",
      "covers_etypes": ["CAN_ASSUME"],
      "direction": "in",
      "new_p_factor": 0.1,
      "delta": 2.3026,
      "cost": 2,
      "rule_family": "trust_overbroad",
      "simulated": false,
      "enabled": false
    }
  }
}
```
Note: the `remove_policy_statement` row covers `CAN_ACCESS` because that is what `apply_delta` removes. If the team decides data-access statements deserve a gentler fix (for example scoping the resource), change both the catalogue and the simulator together and log it.

## E2. `prioritize/config.json`
```json
{
  "default_budget": 3,
  "critical_paths_k": 5,
  "stackelberg": { "pa_ratio": 0.2 },
  "notes": "Budget is in the same cost units as fix_catalogue.json. Suggested default fits one or two fixes."
}
```

## E3. Frozen signatures
```
prioritize.findings.enumerate_findings(G, catalogue=None, include_unsimulated=False) -> list[dict]
    finding shape: see section B2.2
prioritize.interdiction.prioritize(findings, budget, G, entry_nodes=None, crown_jewels=None) -> list[str]
    ordered finding ids; ordering rule in section B4
prioritize.interdiction.prioritize_detailed(findings, budget, G, entry_nodes=None, crown_jewels=None) -> dict
    {
      "budget": 3,
      "selected": ["F-..."],
      "ranked": ["F-...", "..."],
      "objective": 14.13,
      "baseline_objective": 0.32,
      "residual_attack_prob_before": 0.729,
      "residual_attack_prob_after": 1e-06,
      "solve_seconds": 0.02,
      "status": "Optimal"
    }
```
Note: the master guide wrote `prioritize(findings, budget)`. The graph is a required third argument because the MILP needs it. Log this in `docs/phase3_decisions.md` and tell the team before the freeze.

## E4. `prioritize/comparison.json` (for the dashboard's three-bar panel; PROPOSED until Role D confirms)
```json
{
  "budget": 3,
  "entry_count": 2,
  "crown_jewel_count": 3,
  "methods": [
    {
      "name": "naive",
      "selected": ["F-..."],
      "objective": 1.386,
      "residual_attack_prob": 0.25,
      "ppr_crown_jewel_delta": { "ADMIN_EQUIV": -0.01 },
      "paths_cut_at_k": 1
    },
    {
      "name": "stackelberg_rounded",
      "fractional_x": { "F-...": 0.62 },
      "selected": ["F-..."],
      "objective": 1.386,
      "residual_attack_prob": 0.25,
      "ppr_crown_jewel_delta": { "ADMIN_EQUIV": -0.01 },
      "paths_cut_at_k": 1,
      "note": "comparison only; fractional coverage has no operational meaning"
    },
    {
      "name": "interdiction",
      "selected": ["F-...", "F-..."],
      "objective": 14.13,
      "residual_attack_prob": 1e-06,
      "ppr_crown_jewel_delta": { "ADMIN_EQUIV": -0.2 },
      "paths_cut_at_k": 2
    }
  ],
  "budget_sweep": [
    { "budget": 0, "naive_objective": 0.32, "interdiction_objective": 0.32 }
  ]
}
```
The dashboard bar height is most naturally `1 − residual_attack_prob` ("risk reduced") or `objective`; Role D decides the display. Your job is to provide both.

## E5. Reference code (verify before trusting; adapt names to the real graph)

### `prioritize/interdiction.py` (core)
```python
import math
import time

import networkx as nx
import pulp

S_NODE = "__S__"
T_NODE = "__T__"


def _check_findings(G, findings):
    seen = {}
    for f in findings:
        for (u, v, _) in f["covers"]:
            if not G.has_edge(u, v):
                raise ValueError("finding %s covers unknown edge (%r, %r)" % (f["finding_id"], u, v))
            if (u, v) in seen:
                raise ValueError("edge (%r, %r) covered by both %s and %s"
                                 % (u, v, seen[(u, v)], f["finding_id"]))
            seen[(u, v)] = f["finding_id"]
    return seen


def build_and_solve(G, entry, crown, findings, budget):
    entry = [e for e in entry if e in G]
    crown = [c for c in crown if c in G]
    if not entry:
        raise ValueError("No valid entry nodes")
    cover = {}
    _check_findings(G, findings)
    for f in findings:
        for (u, v, _) in f["covers"]:
            cover.setdefault((u, v), []).append((f["finding_id"], f["delta"]))

    # reachability check BEFORE building the LP (otherwise the dual is unbounded)
    H = nx.DiGraph(G)
    for e in entry:
        H.add_edge(S_NODE, e)
    for c in crown:
        H.add_edge(c, T_NODE)
    if T_NODE not in H or not nx.has_path(H, S_NODE, T_NODE):
        return {"selected": set(), "objective": None, "baseline_objective": None,
                "status": "NoPath", "solve_seconds": 0.0}

    nodes = list(G.nodes) + [S_NODE, T_NODE]
    idx = {n: i for i, n in enumerate(nodes)}
    prob = pulp.LpProblem("interdiction", pulp.LpMaximize)
    pi = {n: pulp.LpVariable("pi_%d" % idx[n], lowBound=0) for n in nodes}
    x = {f["finding_id"]: pulp.LpVariable("x_%d" % k, cat="Binary")
         for k, f in enumerate(findings)}

    prob += pi[T_NODE] - pi[S_NODE]
    prob += pi[S_NODE] == 0
    for u, v, d in G.edges(data=True):
        length = -math.log(d["p"])
        extra = pulp.lpSum(dl * x[fid] for fid, dl in cover.get((u, v), []))
        prob += pi[v] - pi[u] <= length + extra
    for e in entry:
        prob += pi[e] - pi[S_NODE] <= 0
    for c in crown:
        prob += pi[T_NODE] - pi[c] <= 0
    prob += pulp.lpSum(f["cost"] * x[f["finding_id"]] for f in findings) <= budget

    t0 = time.time()
    prob.solve(pulp.PULP_CBC_CMD(msg=False))     # or the solver listed by pulp.listSolvers(onlyAvailable=True)
    secs = time.time() - t0
    selected = {fid for fid, var in x.items() if (var.value() or 0) > 0.5}
    return {"selected": selected,
            "objective": pulp.value(prob.objective),
            "status": pulp.LpStatus[prob.status],
            "solve_seconds": secs}
```
Remember: the baseline objective (budget 0) comes from `evaluate.attack_length(G, entry, crown, set(), findings)`, not from a second solve.

### `prioritize/evaluate.py` (independent evaluator and brute force)
```python
import itertools
import math

import networkx as nx


def attack_length(G, entry, crown, selected_ids, findings):
    """Shortest S->T length under -ln(p) edge lengths with selected fixes applied.
    Independent of PuLP on purpose: this is the checker."""
    add = {}
    for f in findings:
        if f["finding_id"] in selected_ids:
            for (u, v, _) in f["covers"]:
                add[(u, v)] = add.get((u, v), 0.0) + f["delta"]
    H = nx.DiGraph()
    for u, v, d in G.edges(data=True):
        H.add_edge(u, v, w=-math.log(d["p"]) + add.get((u, v), 0.0))
    for e in entry:
        if e in G:
            H.add_edge("__S__", e, w=0.0)
    for c in crown:
        if c in G:
            H.add_edge(c, "__T__", w=0.0)
    if "__T__" not in H or "__S__" not in H or not nx.has_path(H, "__S__", "__T__"):
        return math.inf
    return nx.dijkstra_path_length(H, "__S__", "__T__", weight="w")


def brute_force_best(G, entry, crown, findings, budget):
    if len(findings) > 16:
        raise ValueError("too many findings for brute force")
    best, best_sets = -math.inf, []
    ids = [f["finding_id"] for f in findings]
    cost = {f["finding_id"]: f["cost"] for f in findings}
    for r in range(len(ids) + 1):
        for combo in itertools.combinations(ids, r):
            if sum(cost[i] for i in combo) > budget:
                continue
            val = attack_length(G, entry, crown, set(combo), findings)
            if val > best + 1e-9:
                best, best_sets = val, [set(combo)]
            elif abs(val - best) <= 1e-9:
                best_sets.append(set(combo))
    return best, best_sets
```

### Stackelberg (one LP per candidate attacker target)
```python
import pulp

def solve_stackelberg(findings, ra, budget, pa_ratio=0.2):
    ids = [f["finding_id"] for f in findings]
    Ra = {i: ra[i] for i in ids}
    Pa = {i: -pa_ratio * Ra[i] for i in ids}
    Rd = {i: -Pa[i] for i in ids}
    Pd = {i: -Ra[i] for i in ids}
    cost = {f["finding_id"]: f["cost"] for f in findings}
    best = None
    for k, ts in enumerate(ids):
        lp = pulp.LpProblem("ssg_%d" % k, pulp.LpMaximize)
        x = {i: pulp.LpVariable("x_%d_%d" % (k, j), 0, 1) for j, i in enumerate(ids)}
        lp += x[ts] * Rd[ts] + (1 - x[ts]) * Pd[ts]
        ua = lambda i: (1 - x[i]) * Ra[i] + x[i] * Pa[i]
        for i in ids:
            lp += ua(ts) >= ua(i)
        lp += pulp.lpSum(cost[i] * x[i] for i in ids) <= budget
        lp.solve(pulp.PULP_CBC_CMD(msg=False))
        if pulp.LpStatus[lp.status] != "Optimal":
            continue                      # infeasible for this attacker target
        val = pulp.value(lp.objective)
        if best is None or val > best["value"]:
            best = {"value": val, "best_target": ts,
                    "x": {i: x[i].value() for i in ids}}
    return best
```
Hand-checks: `ra = (10,10)`, `B = 1`, unit costs gives `x = (0.5, 0.5)`; `ra = (10,5)`, `pa_ratio = 0` gives `x = (2/3, 1/3)`.

## E6. Optional extras (not required; only after the freeze)
- **Extend `simulate.py`** with `deactivate_key` and `tighten_trust` so the optional catalogue rows become simulated. Small, tested, and logged; the function signature does not change.
- **Weighted crown jewels:** give each crown jewel a different cost-to-attacker in the super-sink edge length (e.g. an admin takeover counts more than one bucket). Report it as an extension, not the baseline.
- **Sensitivity:** vary `pa_ratio`, the `Δ` of the restrict-CIDR fix, and the damping used by the naive baseline; report whether the interdiction choice changes.
- **Interview talking points you will have after this:** "I formulated the dual of the shortest-path LP with binary interdiction variables, verified it against brute force on 50 random graphs, and showed on a parallel-routes case where sorting by risk score wastes the budget." and "I know why Stackelberg randomized coverage is the wrong model for patching and kept it as a labelled baseline."

## E7. What Antigravity is likely to get wrong (summary)
| Mistake | How to catch it |
|---|---|
| Uses `p` (not `−ln p`) as a length, or loses the minus sign | review item in B4; closed-form tests |
| Flips a constraint direction or leaves `x` continuous | brute-force cross-check; break-a-line test |
| Forgets super-source or super-sink | Exercise 3 test; code review |
| Skips the no-path check, so the LP is unbounded | no-path test |
| Lets two findings cover one edge, so `Δ` adds up | edge-disjointness test and error |
| Hard-codes `Δ`, costs or the budget | audit prompt 3-G, item 4 |
| Tunes the catalogue until the demo looks better | diff the JSON on every PR; decisions entry required |
| Presents the Stackelberg fractional output as a recommendation | docstring and dashboard note "comparison only" |
| Compares methods using different evaluators or budgets | one shared `compare_methods` function |
| Edits `risk/` files to make a test pass | safety block rule 7; audit item 8 |
| Loosens test tolerances | safety block rule 8 |
