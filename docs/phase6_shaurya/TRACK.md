# ARGUS Phase 6 — Shaurya's Track (Trust Engine core)

*Two people, one phase, no collisions. This doc is yours; Prabhav has a matching doc. Part A is identical in both. · Sunday 25 Oct 2026 · builds on the Phase 6 Master Plan and its Addendum A*

---

## What you need to do today

1. Unzip `phase6_day0_pack.zip` (it came with this chat) into your repo root, follow its `DAY0_README.md`, and push the **Day-0 commit to main**. Everything else waits on this commit.
2. Message Prabhav (text in §B8): Day-0 is on main, branch from it.
3. Start your own track right away. You do **not** need to wait for his harvest: §B3 builds a first M2 on data you already have.
4. You do **not** need to install Ollama for Phase 6. Skip it until Phase 7.

---

# PART A — Shared rules (identical in both docs)

## A1. The split

|  | **Shaurya: Trust Engine core** | **Prabhav: Generator and Ollama side** |
| --- | --- | --- |
| Needs Ollama? | **No** | **Yes** (he already has it running on the LOQ) |
| Builds | Oracle and labels, hard-negative corruptor, feature store, M2 model and calibration, selective-risk control, decision engine, drift breaker, evaluation, CI, docs | Harvest tool (generations with logprobs), throughput pilot, full harvest, C-mined miner diagnosis, RFT-v2 repair run, escalate-router proposal |
| Hands to the other | `validate_harvest` verdicts, the frozen contract, labels and results | Harvest files (Drive), model files, run reports |
| Never touches | Ollama, GGUFs, model training | Labels, features, M2, risk control |

The two tracks meet at exactly one place: **the harvest file format** (section A4). If both sides honor that, nothing else can collide.

## A2. File ownership (canonical copy: `ml/train_m2/OWNERS.json`)

| Owner | Paths |
| --- | --- |
| **Shaurya** | `ml/train_m2/{labels,features,models,risk,monitor,eval,tests,configs}/`, `ml/train_m2/{common,intake,validate_harvest,splits,cal_data,decide,api_schemas,licence_audit}.py`, `ml/train_m2/{EXPERIMENT_PLAN_M2,MODEL_CARD,DATASHEET}.md`, `ml/real_data/select_cal.py`, `requirements-phase6.txt`, `.github/`, `docs/PHASE6_*`, `docs/PHASE7_HANDOFF.md`, `docs/SECURITY.md`, `docs/phase6_shaurya/`, `.env.example` |
| **Prabhav** | `ml/train_m2/harvest/`, `ml/train_m2/harvest_manifests/`, `ml/train_m1/v2/`, `ml/real_data/diagnostics/`, `ml/real_data/mine_history.py`, `ml/real_data/gitutil.py`, `requirements-m1v2.txt`, `docs/phase6_prabhav/`, `docs/proposals/` |
| **Shared** (either, with the rule shown) | `ml/train_m2/contract/` (PR reviewed by the other), `ml/train_m2/OWNERS.json` (PR reviewed by the other), `docs/decisions-log.md` (append only; concurrent appends merge cleanly), `.gitignore` and `.gitattributes` (only in the Day-0 commit), `ml/train_m2/README.md`, `ml/README_contracts_phase6.md` |
| **Frozen** (Phase 5) | `ml/README_contracts.md`, `remediate/local_model/__init__.py`, `remediate/templates/__init__.py`, `remediate/patch_ir/schema.json`, `privacy/airlock/*`, `policy/**/*.rego`, `ml/train_m1/eval/*`, `ml/mutation_engine/held_out/*`. A change needs both people to agree and a decisions-log entry |

The longest matching prefix decides the owner. A path nobody owns shows as a warning so we extend the map instead of guessing.

## A3. Git protocol

- **Day 0:** Shaurya pushes the pack to `main`. Prabhav creates `phase6/m1-harvest` from that commit.
- **Shaurya works directly on `main`**, only inside his paths: small commits, `git pull --rebase origin main` before every push. (This skips review and CI; it is safe here only because the guard below blocks edits outside your paths. If you would rather use a branch, the rules are identical.)
- **Prabhav works on `phase6/m1-harvest`** and merges **into main at three agreed points** (H2, H3, H4 in A5), each as a pull request that Shaurya reviews for *contract adherence only* and merges with a normal merge commit. Several small merges beat one big merge at the end.
- **Prabhav keeps his branch current:** `git fetch origin && git merge origin/main` at least once a day (merge, not rebase, so he never needs a force-push).
- **The guard, before every push:** `python tools/check_ownership.py --who shaurya` (or `--who prabhav`). It fails if your commits touch a path the other owns. Shaurya adds it to CI in P12.
- **Commit messages:** `phase6(shaurya): ...` or `phase6(prabhav): ...`, plus `phase6(shared): ...` for shared files.
- **Data never goes through git.** Harvest files, models and GGUFs move through the Drive folder `argus/m2_harvest/`; only small manifests are committed.
- **If a conflict happens anyway:** stop, do not force-push, post in chat. The owner of the file resolves it.
- **Tags:** Prabhav tags `phase6-harvest-v1` after H2. Shaurya tags `phase6-complete` after the final merge.

I tested the guard (it blocks cross-ownership edits and warns on unowned paths) and the union-merge setting (two people appending to `decisions-log.md` at once merges cleanly; without the setting git reports a conflict).

## A4. The one interface: harvest format `m2.harvest.v1`

Canonical text: `ml/train_m2/contract/CONTRACT_HARVEST.md`; machine check: `harvest_line.schema.json`; example: `harvest_fixture.jsonl`; what to generate for: `harvest_inputs.jsonl` (**321 distinct inputs**, built from the real Phase 5 data; every input seen in the existing candidate logs is in it).

| Item | Rule |
| --- | --- |
| One line | One generation: `input_key`, `generator` (zeroshot, sft, rft, rft\_v2), `profile` (A or B), `sample_idx` 0–7, `temperature`, `top_p`, `seed`, `model`, `model_digest`, `ollama_version`, `content`, `error`, `eval_count`, `seconds`, `done_reason`, `tokens` |
| `tokens` | `[{t, lp, top}]`: token text, log-probability, optional top-k alternatives. The concatenated `t` must equal `content` |
| Failures | `error` is set, `content` is empty, `tokens` is empty. Never dropped |
| Profile A | Exactly Phase 5's call plus logprobs: sample 0 at T=0.0, samples 1–7 at T=0.7, seed = sample index |
| Profile B | More diverse: sample 0 at T=0.0, samples 1–7 at T=1.0, top\_p 0.95, seed = 1000 + index |
| Volume | 321 inputs × 8 samples = 2,568 lines per (generator, profile). Profile A for 3 generators = 7,704 lines |
| Files | `ml/train_m2/harvest_out/<generator>/<profile>/part-NNNN.jsonl` (git-ignored) plus a `MANIFEST.json` per folder (committed under `harvest_manifests/`) |
| Changes | Additive only; breaking change = new `schema_version`; either person can ask, both must approve |

**Producer** (Prabhav) generates and writes; he does not score, label or compute features. **Consumer** (Shaurya) validates, scores with the frozen Phase 5 scorer, labels, and builds features; he never calls Ollama.

## A5. Handoffs

| ID | Day (date) | Prabhav delivers | Shaurya does | Merge |
| --- | --- | --- | --- | --- |
| **H0** | 1 (Sun 25 Oct) | Branch created | Day-0 pack on main | — |
| **H1** | 3 (Tue 27 Oct) | Pilot: 20 inputs × 3 generators, profile A, plus throughput numbers | Run `validate_harvest`; reply "OK" or a problem list within a day | — |
| **H2** | 5 (Thu 29 Oct) | Full profile A, 3 generators (7,704 lines) on Drive + manifests | Validate, ingest | **Merge 1:** harvest tool |
| **H3** | 8 (Sun 1 Nov) | Profile B for SFT and RFT (5,136 lines); C-mined diagnostic result | Validate, add to training pool | **Merge 2:** diagnostics |
| **H4** | 11 (Wed 4 Nov) | RFT-v2 model, its eval report, GGUF on Drive, plus its harvest (profiles A and B, 5,136 lines) | Validate, include as a generator | **Merge 3:** v2 code |
| **H5** | 12 (Thu 5 Nov) | Freeze: no more merges | One-shot held-out evaluation | Tag `phase6-complete` on Day 13 |

If a handoff slips by a day, nothing blocks: Shaurya's track runs on existing data until harvest data arrives (B3), and Prabhav's v2 work does not depend on M2.

## A6. Five-line check before every push

1. `git status` shows only files in my paths.
2. `python tools/check_ownership.py --who <me>` prints OK.
3. My tests pass: `python -m pytest <my test folder> -q`.
4. No data files, models or secrets are staged.
5. If I touched `contract/` or `OWNERS.json`, I told the other person.

---

# PART B — Shaurya's track

## B1. Scope and deliverables

**Yours:** pillars T1 (oracle), T2 (corruptor), T4 (features), T5 (M2 and calibration), T6 (selective-risk control), T7 (decision engine), plus T8 (drift breaker), T10 (Trust Console contract) and T11 (release subset) as Stretch/Moonshot; the C-cal real-data split (P5b); CI, hygiene and the licence audit (P12); all documentation (P11); emails E3–E5 from the master plan §7.

**Not yours (Prabhav's doc):** the harvest tool, Ollama, GGUFs, RFT-v2, the C-mined diagnosis, emails E1–E2, the escalate-router proposal.

**Pre-registration still applies, with the Addendum A changes:** the "≥ 300 natural negatives" bar is reset to "≥ 300 labeled negatives, with natural clusters reported separately (currently 22)". Write `EXPERIMENT_PLAN_M2.md` on Day 4, before any held-out scoring.

## B2. Setup (no Ollama)

1. Python 3.12 virtual environment in the repo; `pip install -r requirements.txt -r requirements-phase5.txt` (and `requirements-phase6.txt` once P0-S creates it).
2. **OPA binary:** the frozen scorer calls OPA to run the Rego rules. Download the Windows OPA executable from openpolicyagent.org, rename it `opa.exe` and put it on PATH. Check with `opa version`. (`ml/real_data/rego_runner.py` shows exactly how it is called; read it before assuming.)
3. **Data into the repo:** from `ml.zip` copy the git-ignored files into the same paths: `ml/mutation_engine/dataset/*.jsonl`, `ml/train_m1/data/*.jsonl`, `ml/train_m1/eval/runs/*/*.candidates.jsonl`, `ml/real_data/out/`. Verify with `python -m ml.tools.verify_manifest` (I checked the same ten hashes and all matched).
4. Run the existing suite once and save the counts; that is your "we broke nothing" baseline.

## B3. Start today without waiting: M2 v0 on existing data

The 18 candidate files from Phase 5 (3 generators × 6 sets) already hold, per candidate: raw text, gate result, hidden-check result, escalation flag and safety flag. That is enough to build a first M2 **without logprobs**:

1. P0-S (below) and `intake.py`: reproduce my intake numbers (321 inputs; 22 natural-negative clusters; train overlap per set).
2. Labels: `strict_correct` from the existing scored fields (full equivalence, minimal patch, decoys untouched, no side effects, all four hidden checks). No new scoring needed for this v0.
3. Features available now: consensus (agreement, distinct answers), structure (op counts and types), route and rule prior, T0 agreement. The U (logprob) group stays empty until H1/H2.
4. Splits by input key across all sets (P5, with the Addendum A5 change).
5. Logistic regression plus a calibrator, one reliability diagram. It will be weak. That is the point: it proves the plumbing before the real data arrives, and shows you which features matter.

Expect the v0 numbers to be noisy: only 22 natural-negative clusters exist. Treat v0 as a **pipeline test**, not a result. Do not quote its numbers anywhere.

## B4. Which prompts to use (from the Master Plan)

Use the Master Plan prompts below with the new context pack (P0-S, in §B5, which replaces the old P0 rules block), then append the **amendment** shown. P2 and P13 are Prabhav's now.

| Prompt | Use | Amendment to append |
| --- | --- | --- |
| P0 | Replace with **P0-S** (§B5) | — |
| P1 | Replace with **P1-S** (§B5) | — |
| P2 harvest | **Prabhav** | — |
| P3 oracle, corruptor, labels | Master Plan P3 | "For natural candidates from Phase 5 profile A, take the gate and hidden results from the existing `scored` fields in `ml/train_m1/eval/runs/*/*.candidates.jsonl` and do not re-score. Newly harvested files (`m2.harvest.v1`) must be scored with the frozen scorer (`ml.train_m1.eval.score`), which needs the `opa` binary. The pre-registered natural-negative bar is now: 300 labeled negatives in total, natural clusters reported separately." |
| P4 features | Master Plan P4, plus **P4-U** (§B5) for the logprob group | "Build the U group against `ml/train_m2/contract/harvest_fixture.jsonl` first; it must work on real files with no code change." |
| P5 splits | Master Plan P5 | "Phase 5's B1 and B2 inputs are 100% in train, A\_val 79%, gold 47%, C\_verifier 30%. Treat any input in B1, B2, C\_verifier or gold as test-only for M2 regardless of its Phase 5 set name; the cleanest real-data test is the C\_verifier inputs not in train (76)." |
| P5b C-cal | Master Plan P5b | none |
| P6 models | Master Plan P6 | none |
| P7 risk | Master Plan P7 (paste `ltt.py` verbatim from the Master Plan) | none |
| P8 decide | Master Plan P8 | none |
| P9 drift | Master Plan P9 | "Use B2 (held-out encryption family, 13.9% hidden-check failures among gate-passing SFT candidates) as the first shift scenario." |
| P10 eval | Master Plan P10 | none |
| P11 docs | Master Plan P11 | "Add a Prabhav-section to the mentor report: his harvest, RFT-v2 and miner results come from his own `docs/phase6_prabhav/` report." |
| P12 CI | Master Plan P12 | "The CI workflow must also run `python tools/check_ownership.py --who shaurya --base origin/main` on pull requests and `--who prabhav` when the head branch is `phase6/m1-harvest`." |
| P13 RFT-v2 | **Prabhav** | — |

## B5. The three prompts that are new or changed

Paste **P0-S** at the start of every Antigravity task (it is the context pack for your track and replaces the rules block in the Master Plan's P0). Then run the task prompt.

### P0-S — Context pack and skeleton (your first task, and the preamble for every later one)

```text
ROLE
You are a senior ML-systems and applied-statistics engineer working in the ARGUS repo (Windows 11, PowerShell,
Python 3.12, pytest) AS SHAURYA. ARGUS is a privacy-first cloud remediation platform. Phase 5 delivered M1, a
local model that drafts Patch-IR fixes. Phase 6 builds M2: a calibrated confidence model plus a risk-controlled
auto-apply threshold under ml/train_m2/. M2 scores ONLY fix candidates that already passed the gate;
escalate-only patches bypass M2 and go to a human.

TWO PEOPLE WORK IN PARALLEL. Prabhav owns generation (Ollama, harvest, RFT-v2). Shaurya owns everything that
consumes harvest files. They meet only at ml/train_m2/contract/.

HARD RULES (violating any is a failed task)
1. OWNERSHIP. Before finishing run: python tools/check_ownership.py --who shaurya --base origin/main
   It must print OK. Never edit anything Prabhav owns: ml/train_m2/harvest/, harvest_manifests/, ml/train_m1/v2/,
   ml/real_data/diagnostics/, ml/real_data/mine_history.py, ml/real_data/gitutil.py, requirements-m1v2.txt,
   docs/phase6_prabhav/, docs/proposals/. Shared files (ml/train_m2/contract/*, ml/train_m2/OWNERS.json,
   docs/decisions-log.md, .gitignore, .gitattributes) are NOT edited by you; if one needs a change, stop and
   write the proposed diff in your report for the human to discuss.
2. FROZEN Phase 5 files: ml/README_contracts.md, remediate/local_model/__init__.py,
   remediate/templates/__init__.py, remediate/patch_ir/schema.json, privacy/airlock/*, policy/**/*.rego,
   ml/train_m1/eval/*, ml/mutation_engine/held_out/*. Import from them; never modify them.
   ml/tests/test_contracts_doc.py must keep passing.
3. Never add __init__.py inside ml/mutation_engine/phase1_skeleton/.
4. Every random operation takes a seed (default 1337). Every script writes a provenance JSON next to its
   output: git commit, python and package versions, sha256 of input files, seed, UTC time, argv.
5. You never call Ollama and never need to. No network except for explicitly named downloads. No secrets.
6. Held-out sets (B1, B2, C_verifier, gold, C-human) are NEVER used to choose models, features, thresholds,
   calibrators or hyperparameters. Held-out scoring goes only through ml/train_m2/eval/run_once.py, which
   appends one line per (model, set) to ml/train_m2/eval/RUN_LOG_M2.md and refuses repeats without
   --repeat-reason.
7. The statistical unit is the CLUSTER = the distinct model-input hash (ml.mutation_engine.dataset_io.input_key).
   Never split, bootstrap or test at row level.
8. M2's label is never gate-pass. Gate-pass may be a FEATURE, never the label.
9. Style: type hints; docstrings stating the contract; small pure functions; ASCII-only; logging not print in
   library code; tests in ml/train_m2/tests/; no heavy new dependencies beyond requirements-phase6.txt.

WORKFLOW
A. Read the files named in the task. Summarise what you found in 10 lines and list every assumption in the task
   that turned out false. Do this BEFORE coding.
B. Implement. Prefer boring, testable code.
C. Run python -m pytest ml/train_m2/tests -q and python -m pytest ml/tests -q; paste the last 15 lines of each.
   Fix failures; never skip or xfail to get green.
D. Finish with a report: files created, public functions with signatures, tests added, known limitations.

TASK P0-S (skeleton)
1. Read: ml/train_m2/OWNERS.json, ml/train_m2/contract/CONTRACT_HARVEST.md, harvest_line.schema.json,
   harvest_fixture.jsonl, ml/README_contracts.md, ml/train_m1/EXPERIMENT_PLAN.md,
   ml/mutation_engine/dataset_io.py, ml/train_m1/eval/score.py, ml/mutation_engine/qa/gate_stub.py,
   ml/mutation_engine/qa/hidden_checks.py, ml/real_data/rego_runner.py, docs/PHASE5_MENTOR_REPORT.md,
   requirements.txt, requirements-phase5.txt, .gitignore.
2. Create ONLY inside paths you own (see OWNERS.json): empty packages with __init__.py for
   ml/train_m2/{labels,features,models,risk,monitor,eval,tests}/ ; ml/train_m2/configs/ (no __init__);
   ml/train_m2/common.py; requirements-phase6.txt (lightgbm, scikit-learn, scipy, numpy, pandas, matplotlib,
   joblib, jsonschema, pytest; mapie as an OPTIONAL commented line).
   If ml/train_m2/__init__.py is missing, STOP and report it (it is a shared file from the Day-0 commit).
3. common.py: set_seed(seed); provenance(extra) -> dict; repo_root(); cluster_key(record) wrapping
   dataset_io.input_key; sha256_file(path); jsonl_iter(path); jsonl_write_atomic(path, rows) (write temp, fsync,
   rename); load_inputs() reading ml/train_m2/contract/harvest_inputs.jsonl.
4. tests/test_skeleton.py: imports every subpackage; set_seed determinism; atomic write keeps the old file if
   interrupted between temp write and rename; cluster_key stable across processes; harvest_inputs.jsonl has
   exactly 321 lines with unique input_key and every record's input_key equals cluster_key(record).
5. Baseline: run the whole existing suite BEFORE changing anything and store the counts in
   ml/train_m2/out/reports/baseline_tests.txt.
ACCEPTANCE: new tests green; existing suite counts unchanged; check_ownership prints OK; paste git diff --stat.
```

### P1-S — `validate_harvest.py` (the gatekeeper for everything Prabhav delivers)

```text
[Prepend P0-S.]

GOAL
Build the validator that decides whether a harvest delivery from Prabhav is accepted. It is the only thing
standing between his files and your training data, so it must be strict, fast and explain every failure.

READ FIRST: ml/train_m2/contract/CONTRACT_HARVEST.md, harvest_line.schema.json, harvest_fixture.jsonl,
harvest_inputs.jsonl, ml/train_m1/eval/run_eval.py (sample 0 greedy, samples 1-7 at temperature 0.7 with
seed = sample index), and one existing ml/train_m1/eval/runs/sft/A_val.candidates.jsonl (fields: input_key,
contents[8], scored.candidates[8], example_ids).

BUILD ml/train_m2/validate_harvest.py
  CLI: python -m ml.train_m2.validate_harvest --root ml/train_m2/harvest_out [--allow-partial]
       [--manifests ml/train_m2/harvest_manifests] --out ml/train_m2/out/reports/harvest_validation
  Checks, each reported with counts and the first 5 offending examples:
   1. SCHEMA: every line validates against harvest_line.schema.json (Draft 2020-12).
   2. COMPLETENESS: for every (generator, profile) folder found, every one of the 321 inputs has samples 0-7.
      Without --allow-partial a gap is a failure; with it, print the coverage table instead.
   3. DUPLICATES: exactly one line per (input_key, generator, profile, sample_idx).
   4. KEYS: every input_key exists in harvest_inputs.jsonl.
   5. TEXT EQUALS TOKENS: ''.join(token.t) == content for every success line. Report the mismatch rate; fail
      above 0.5% and show examples (tokenizer byte pieces can legitimately differ; say so in the message).
   6. PROFILE CONFORMITY: profile A: sample 0 has temperature 0.0 and seed 0, samples 1-7 temperature 0.7 and
      seed = sample_idx, top_p null. Profile B: sample 0 temperature 0.0, samples 1-7 temperature 1.0,
      top_p 0.95, seed = 1000 + sample_idx.
   7. LOGPROB SANITY: every lp <= 0; mean lp per line between -5 and 0; report the share of lines whose
      mean lp is above -0.001 (a collapsed generator looks like this) per generator and profile.
   8. ERRORS: error-line rate per (generator, profile); warn above 2%, fail above 10%.
   9. VERSIONS: one ollama_version and one model_digest per (generator, profile); mixed values are a failure.
  10. MANIFESTS: if a MANIFEST.json exists for a folder, its sha256 and line counts must match the files.
  11. REPLICATION (information only, never a failure): for profile A, compare content with the Phase 5
      candidate logs (ml/train_m1/eval/runs/<generator>/<set>.candidates.jsonl: contents[sample_idx] for the
      matching input_key). Report the exact-match rate per generator and per sample index. Sample 0 (greedy)
      should match very often; seeded samples may not.
  Output: validation_report.md and validation_report.json (+ provenance), exit code 0 only if every hard check
  passes. The report must end with one line a human can paste into chat: ACCEPTED or REJECTED plus the reasons.
TESTS (ml/train_m2/tests/test_validate_harvest.py): the fixture passes; then mutate a copy of the fixture to
trigger each check separately (bad schema, missing sample, duplicate, unknown input_key, text/tokens mismatch,
wrong temperature for the profile, positive logprob, error rate, mixed versions, wrong manifest hash) and
assert the right check fails and the others still pass.
ACCEPTANCE: run on the fixture and show ACCEPTED (with --allow-partial); run on the mutated copies and show
REJECTED with the correct reasons.
```

### P4-U — Logprob feature group (add to Master Plan P4)

```text
[Prepend P0-S, then the Master Plan P4 prompt, then this.]

GOAL
Implement feature group U (generator uncertainty) from the contract's token list. It must work on
harvest_fixture.jsonl today and on real harvest files later with no code change.

DEFINITIONS (all computed from one candidate's tokens; None if tokens are missing)
  Reconstruct character offsets by cumulating token.t; map tokens to character spans.
  Parse content as JSON with a small offset-tracking scanner (do not use regex on JSON) to find the character
  spans of: the values of every key named op, every key named attr, every key named value, and rationale_ref.
  u_lp_mean, u_lp_min, u_lp_p10 (10th percentile), u_lp_std, u_seq_logprob (sum), u_n_tokens.
  u_lp_op_min, u_lp_attr_min, u_lp_value_min: minimum lp over tokens overlapping the respective spans
      (the 'value' span is the actual fix value, the most informative one).
  u_top_margin_mean: mean over tokens with top-k of (lp of rank 1 minus lp of rank 2), None if top is null.
  u_entropy_mean: mean over tokens with top-k of the entropy of the renormalised top-k distribution, else None.
  Cohort features (over the 8 samples of the same input, same generator and profile):
  u_cohort_lp_mean_std, u_cohort_value_lp_min_min, u_cohort_n_valid.
  Register each in features/registry.py with group 'U', dtype float, a monotone hint (higher lp = more
  trustworthy: +1; std and entropy: -1), source 'harvest', version 1.
TESTS: hand-built token lists with known answers (a 3-token example where the value token has lp -2.0 gives
u_lp_value_min == -2.0); span mapping on a JSON with escaped quotes; a content where op appears inside a string
value does not confuse the scanner; None handling; parity test (batch equals single-row) still green; the group
works on every non-error line of harvest_fixture.jsonl.
ACCEPTANCE: print u_* for each fixture line.
```

## B6. Your fourteen days

| Day | Date | You do | Needs from Prabhav |
| --- | --- | --- | --- |
| 1 | Sun 25 Oct | Day-0 pack pushed (H0); kickoff message sent; OPA installed; data copied in; baseline tests saved; P0-S | nothing |
| 2 | Mon 26 | P1-S `validate_harvest` built and tested on the fixture; `intake.py` reproduces my intake numbers | nothing |
| 3 | Tue 27 | **H1:** validate his pilot; reply OK or a problem list. Start P3 (oracle) | pilot files |
| 4 | Wed 28 | **Write and commit `EXPERIMENT_PLAN_M2.md`** (before any held-out look); P3 corruptor; P5 splits | nothing |
| 5 | Thu 29 | **H2:** validate and ingest the full profile A harvest; review his Merge 1 for contract adherence; labeling sprint 1 (150 candidates) | full profile A |
| 6 | Fri 30 | P4 features including P4-U on real data; P5b C-cal started (needs network and disk; run it in the daytime) | nothing |
| 7 | Sat 31 | **Midpoint review**: M2 v0 on real harvest features; one honest reliability diagram | nothing |
| 8 | Sun 1 Nov | **H3:** ingest profile B; P6 model zoo and calibration | profile B, C-mined result |
| 9 | Mon 2 | P7 risk control and the Monte-Carlo proof; labeling sprint 2 | nothing |
| 10 | Tue 3 | P8 decision engine; P9 drift breaker | nothing |
| 11 | Wed 4 | **H4:** ingest RFT-v2 harvest; P10 evaluation harness and ablations | v2 harvest |
| 12 | Thu 5 | **H5:** freeze; one-shot held-out evaluation (run-once log); nothing else that day | freeze |
| 13 | Fri 6 | P11 docs, P12 CI and licence audit; tag `phase6-complete` | final merge done |
| 14 | Sat 7 | Buffer, mentor review, Phase 7 handoff note | nothing |

**If Prabhav is late:** the work on Days 2–4 and 8–10 does not depend on him. Only Days 5 and 11 do. If H2 slips past Day 6, train on the Phase 5 profile A scored logs (no logprob group) and add group U when the files arrive; the feature registry's spec hash makes that safe.

## B7. Code plan (honest version of "push more code than Prabhav")

Prabhav's repo has about 16.5K lines of real Python; the "80K lines" figure counts data files and a notebook. A fair target for your side is **about 8–10K lines of real, tested code**, roughly half of it tests. Do not pad it: padding shows in review, and generated reports and figures are not code.

| Module | Approx. lines | Notes |
| --- | --- | --- |
| `labels/` (oracle, counterfactual oracle, corruptor, human labels, build) | 1,200 | The counterfactual oracle is the hardest and most original piece |
| `features/` (registry, compute, context, U group) | 1,100 | One code path for train and inference |
| `models/` (zoo, calibrators, metrics, ablation, train) | 900 | Cluster bootstrap everywhere |
| `risk/` (LTT given, decisions, calibrate\_tau, Mondrian, bootstrap, Monte-Carlo, selection) | 900 | `ltt.py` is pasted, not written |
| `decide.py`, `api_schemas.py` | 450 | The frozen interface Phase 7 calls |
| `monitor/` (drift, audit, breaker, simulate) | 650 | Stretch |
| `eval/` (run-once, report generator) | 800 | Every number generated, none typed |
| `validate_harvest.py`, `intake.py`, `splits.py`, `cal_data.py`, `licence_audit.py`, CI | 1,100 |  |
| Tests | 3,500 | Property tests, mutated-fixture tests, parity test |

The thing worth competing on is not line count: it is that your half carries the guarantee (certified selective risk) that makes the project distinctive.

## B8. Messages and emails you send

**M-B. Kickoff message to Prabhav (send after the Day-0 push)**

> Day-0 is on main (`phase6(shared): ownership map, harvest contract, input list, guard script`). Please branch `phase6/m1-harvest` from it. Your doc has everything: the contract is `ml/train_m2/contract/`, you own `ml/train_m2/harvest/`, `ml/train_m1/v2/`, `ml/real_data/diagnostics/`, and the miner files. Before each push run `python tools/check_ownership.py --who prabhav`. First deliverable (H1) is a 20-input pilot on Tuesday, then the full profile A harvest on Thursday. If you want to change the contract, tell me first. I don't need Ollama for any of my part, so I'm leaving that entirely to you. Thank you for taking it.

**Emails (full drafts are in the Master Plan §7):** E3 mentor design review (with the statistics-review request), E4 IPR cell, E5 statistics reviewer. **E1 and E2** (TerraFormer and Reyes et al.) are Prabhav's; he already has drafts. Send E3 and E4 on Day 1 or 2; send E5 only after `PROOF_NOTE.md` exists (Day 9).

## B9. Definition of done (your half)

- [ ] Day-0 pack on main; guard script passes on every push
- [ ] OPA installed; baseline test counts saved
- [ ] `validate_harvest` built; every delivery from Prabhav validated with a written ACCEPTED or REJECTED
- [ ] `EXPERIMENT_PLAN_M2.md` committed on Day 4, before any held-out scoring
- [ ] Oracle, counterfactual oracle and corruptor built; hard-negative table produced; ≥ 300 labeled negatives, natural clusters reported separately
- [ ] ≥ 300 human-labeled candidates; κ and oracle-vs-human agreement reported
- [ ] C-cal real-data split built (≥ 300 clusters) and disjoint from existing buckets
- [ ] Feature store with parity test green (including group U on real files)
- [ ] M2 trained and calibrated on validation only; ablations done
- [ ] `ltt.py` pasted verbatim; Monte-Carlo table reproduces the pattern; `PROOF_NOTE.md` sent for review
- [ ] `tau_star.json` produced (or `certified=false` explained)
- [ ] `decide()` and `confidence()` frozen with tests; explanations audited for leaks
- [ ] Drift breaker simulated (Stretch)
- [ ] One-shot held-out evaluation logged; results report generated, not typed
- [ ] Model card, datasheet, mentor report, Phase 7 handoff written; CI green on a clean clone including the ownership guard
- [ ] Tag `phase6-complete`
