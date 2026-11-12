# EXPERIMENT_PLAN_M2: pre-registration for the ARGUS Trust Engine (Phase 6)

Status: written 2026-11-11 by Shaurya. **No held-out number has been computed** (there is no `ml/train_m2/eval/RUN_LOG_M2.md`).
This file is frozen at the commit that adds it. After that, only the change log (section 12) may grow, and **a bar is never lowered after the number it judges is known**.
It supersedes the one-page `PREREG_M2.md` (frozen at commit `1e2bd23`, kept as v0); nothing here contradicts v0, section 12 lists every change since.

## 1. Question

Can M2 plus a risk-controlled threshold let ARGUS auto-apply a useful share of gate-passing fixes while keeping the selective error rate below alpha, with confidence 1 - delta,
on inputs it never saw? Three scoped sub-questions, in the order the data allow them to be answered:

* **Q1, weak-generator trust layer.** For a generator with a realistic error rate (rft_v2: 60% of decisions strictly wrong), does a per-generator M2 rank correct above incorrect drafts
  better than a (generator, rule) base-rate predictor, on clusters it never saw?
* **Q2, deployment generator.** For the deployment generator (SFT, Rule 5.2), is the gate-passing draft the pipeline would apply wrong on at most alpha of unseen clusters? M2 adds nothing
  if SFT is essentially never wrong, so Q2 is answered with a gate-only certificate and M2 is reported as unused.
* **Q3, negative control.** Is a pooled M2 mostly a generator detector? (P6b already says yes; this is reported, not re-tested.)

## 2. Fixed parameters

| Item | Value |
|---|---|
| alpha, delta (headline) | 0.05, 0.05; sweep alpha in {0.01, 0.02, 0.05, 0.10} at delta 0.05 |
| c_FA / c_esc | 20 / 1 (Bayes cutoff 0.95), as in `configs/decision.json` |
| seed | 1337 |
| LTT grid | exactly as in `ml/train_m2/risk/ltt.py` (pasted verbatim from the Master Plan); grid sha256 `3829cdf06e159e6e54869ccfd520324300bac2875a57e0c6b65a546d517b6553` |
| generation configuration (part of M2's contract) | harvest profile A: greedy sample 0 then seeds 1-7 at temperature 0.7, N = 8, `format` = Patch-IR schema, Modelfile presence_penalty 1.5, top_k 20, top_p 0.95, Ollama 0.40.x. M2 is calibrated only for drafts produced this way |
| feature spec | version 1, 35 features in groups U, C, S, R; hash `0c099708cff3be6d30e2dadeccd7467d7fd4a452088ec81b4600994310959e50`. Groups X, G, H of the Master Plan are **not implemented** |
| splits | `ml/train_m2/out/m2/splits.json`, sha256 `6b6b7bf7daa0356593af6f9e207f63016df0c9e580e1fc24092c4364d50ba2bb`: train 105, val 34, cal 50 (15 forced), test 132 clusters. A re-split (e.g. after out-of-fold SFT drafts) writes a new hash into the change log before anything is scored |

## 3. Population and decision unit

* Candidates: natural FIX-route drafts that passed the gate. Escalate-route inputs and escalate-only patches bypass M2 and go to a human.
* Decision unit: one decision per cluster (`input_key`) = the first gate-passing draft in sample order (`risk/decisions.py`). Rows of the same cluster are never treated as independent.
* Route comes from the dataset `meta.route` ("fix" / "escalate"). The literal "ESC" is a README label and must never be compared with `meta.route` (a source-scan test enforces this).

## 4. Labels

* Target y = 1 iff `oracle_class == minimal_correct` (strict). Gate-pass is never the label. Reported alongside: *harmful* error = `wrong` or `fixed_should_escalate`; `valid_not_minimal`
  (harmless extra edits) is counted separately and is a strict negative but not a harmful one.
* Reference-free (counterfactual) labels are **weak** (strict rule: recall of wrong 0.926, precision of "wrong" 0.858, 22% of correct fixes called wrong) and are used for nothing that is evaluated.
* Corruptor rows (C1, C2, C3 kept; 144 distinct hard negatives) are train-only and are **not used in this version**.
* Human labels (C-human): **not built**. See sections 8 and 13.

## 5. Partitions and held-out sets

* Test-only: every input in B1, B2, C_verifier, gold (132 clusters). Any held-out input is excluded from train, val and cal by construction (`splits.py`, `leakguard.py`).
* Seen versus unseen (the generator was trained on the input): B1 36/36 seen, B2 10/10 seen, C_verifier 32 of 108 seen, gold 14 of 30 seen. **Unseen held-out clusters: C_verifier 76 + gold 16 = 92** for SFT, RFT and rft_v2 (zeroshot is unseen everywhere).
* Primary held-out analyses use **unseen clusters only**; seen clusters are reported separately and labelled in-sample.
* Non-test unseen clusters: 15 (the A_val-only inputs). They are in cal. M1 checkpoint selection used A_val, so drafts on those 15 are mildly optimistic.

## 6. Models and selection

* Primary M2 is **per-generator** (standardised logistic regression; monotone-constrained LightGBM as the alternative), because the pooled model is confounded (P6b: a generator-only model reaches AUROC 0.910; ablating any one feature group leaves AUROC at 0.996-1.000).
* The pooled P6a model (logistic + isotonic; val log-loss 0.0033 after calibration, but the calibrator was fitted and scored on the same VAL set, so that figure is in-sample) is kept as a labelled baseline; it carries no claim.
* Four calibrators (isotonic, Platt, Beta, Venn-Abers) are fitted on VAL (or inner folds) only; selection by log-loss then ECE. Nothing else touches VAL. Calibration quality is judged out of sample.
* Training seeds: one (logistic is deterministic; LightGBM deterministic with fixed seed). This is a stated limitation, not a robustness claim.

## 7. Metrics and bars

Cluster bootstrap (1,000 resamples of clusters, seed 1337) for every interval; Clopper-Pearson at the cluster level for risk bounds.

| # | Metric | Bar | Applies to | Honest note |
|---|---|---|---|---|
| B1 | Label independence | >= 300 gate-passing natural candidates where the oracle label differs from gate-pass | data | **Not met**: 66 distinct usable natural strict negatives (61 clusters, of which rft_v2 55, zeroshot 4, sft 3, rft 3); with 144 corruptor negatives the total is 210 < 300 |
| B2 | Discrimination vs base rate | model AUROC CI above 0.5, difference to the (generator, rule) base-rate predictor CI above 0, and >= 5 negative clusters | per-generator M2, unseen held-out | below 5 negative clusters the result is "insufficient evidence", never a pass |
| B3 | Calibration | ECE <= 0.05 with cluster-bootstrap CI | per-generator M2, unseen held-out | C-human was the Master Plan's set; replaced by unseen held-out clusters (change log). Needs >= 5 negative clusters |
| B4 | Risk control | realized P(wrong given auto-applied) <= alpha = 5% (and the Clopper-Pearson UCB reported) on every held-out set | SFT gate-only; any model with a certified tau | a set with fewer accepted clusters than the rule of n (59 at alpha 0.05) is reported "uninformative", not "pass" |
| B5 | Autonomy | auto-apply rate >= 50% of gate-passing clusters at alpha = 5% | SFT gate-only; rft_v2 M2 if certified | if below, report what blocks it (calibration clusters, not the model) |
| B6 | Guarantee proof | Monte-Carlo coverage of the LTT bound >= 1 - delta - 1% over 2,000 repetitions; the v3-CRC conditional error shown exceeding alpha in at least one regime | harness | **Not built yet** (section 13) |
| B7 | Shift | leave-one-family-out realized error reported | per-generator M2 | breaker simulation is Stretch and not a pass/fail bar |
| B8 | Parity | training and inference feature vectors bit-identical for 100% of a 500-row replay on real harvest rows | features | synthetic and 16-row real tests pass; the 500-row replay is **not run yet** |

## 8. Stop rules and their status (stated before any held-out run)

| Rule | Status on 2026-11-11 |
|---|---|
| S1. If gate-passing natural negatives < 300, stop and fix the data before modelling | **Triggered** (66 distinct usable). Modelling continued, on a reduced scope, because the input space is small (321 clusters in total) and cannot supply 300. Claims are scoped to what the evidence supports (section 1); this is a recorded deviation |
| S2. If oracle-vs-human agreement < 0.8 on C-human, stop and fix the oracle | **Not evaluable**: C-human does not exist. Mitigation: the counterfactual labeler is measured against the reference oracle on corrupted patches (P3c), and its labels are never used for evaluation |
| S3. If M2 does not beat the rule-prior baseline by a clear margin, report that its added value is small | **Applies and is reported**: pooled M2 does not beat it (P6c: AUROC 0.886 vs 0.924; pooled CV 0.928 vs 0.903, difference CI -0.052 to +0.097). Per-generator rft_v2 does (below) |
| S4 (new). If out-of-fold SFT drafts are not delivered by the date in the change log, Q2 is reported as "not certified" with the exact number of clean unseen clusters still needed | Active; the unseen SFT pool is 15 clusters (UCB 0.181 at 0 errors), 44 more clean clusters are needed |

## 9. Statistics

Cluster bootstrap everywhere; Wilson and Clopper-Pearson at the cluster level; paired decision comparisons with the McNemar test on clusters; one training seed (stated); no multiplicity
correction is claimed beyond the fixed-sequence structure of LTT, and exploratory analyses are labelled exploratory.

## 10. One-shot rule

Each (model, held-out set) pair is scored once through `ml/train_m2/eval/run_once.py`; every run appends one line to `RUN_LOG_M2.md`; a repeat needs a written reason in the log.
Per-generator models count as separate models. No held-out result may be used to choose a model, feature, calibrator, threshold or hyperparameter.

## 11. Held-out protocol

1. Verify the splits hash, the feature spec hash and that this file and `PREREG_M2.md` are on `origin/main`.
2. E-SFT: SFT gate-only, decision level, on (a) the 92 unseen held-out clusters (primary) and (b) all 132 (in-sample, secondary). Report errors (strict and harmful), Clopper-Pearson UCB, auto-apply rate.
3. E-v2: per-generator rft_v2 M2 on the unseen held-out clusters that have a gate-passing rft_v2 draft: AUROC, ECE, base-rate comparison, selective risk at tau only if tau is certified.
4. E-pooled: the pooled P6a model, reported as the confounded baseline.
5. Generate `PHASE6_RESULTS.md` from the run log and reports; no number is typed by hand.

## 12. Change log

| Date | Change | Reason | Held-out opened? |
|---|---|---|---|
| 2026-10-28 | `PREREG_M2.md` v0 frozen (`1e2bd23`) | Day-4 pre-registration, one page | no |
| 2026-11-06 | Route bug found and fixed in our tooling (meta.route is "fix"/"escalate"); Phase 5 SFT 349/361 holds per example | evidence | no |
| 2026-11-09 | Pooled M2 shown to be generator-confounded (P6b); compared with a base-rate predictor (P6c); `beats_prior` tightened | evidence | no |
| 2026-11-10 | Grouped CV and gate-only table (P6d): per-generator rft_v2 M2 beats the prior; SFT/RFT/zeroshot have too few negative clusters | evidence | no |
| 2026-11-11 | This plan written; primary M2 becomes per-generator; bars B3 and B5 re-scoped (C-human not built); B4 "uninformative" rule added; S4 added | the non-test numbers above were seen when these choices were made; **no held-out number was** | no |

## 13. Appendix A: status against the Definition of Done

| Item | Status |
|---|---|
| Day-0 pack, OPA, baselines, `validate_harvest`, harvest ACCEPTED | done |
| `EXPERIMENT_PLAN_M2.md` | this file |
| Oracle, counterfactual oracle (fixed), corruptor, hard-negative table | done; counterfactual labels weak |
| >= 300 labeled negatives, natural clusters separately | **not met** (210; natural usable 61 clusters, SFT 3) |
| >= 300 human-labeled candidates, kappa | **not started** (tooling in `labels/human.py`); plan: a smaller, stratified, blinded set with two labelers |
| C-cal real-data split >= 300 clusters (P5b) | **not started and probably infeasible**: only 321 distinct inputs exist and C-mined yields 5; replaced by out-of-fold SFT drafts (Prabhav) |
| Feature store, parity test | done for groups U, C, S, R; 500-row replay pending; groups X, G, H not built |
| M2 trained, VAL only, ablations | done (P6a-P6d) |
| `ltt.py` verbatim, Monte-Carlo, PROOF_NOTE | `ltt.py` done; Monte-Carlo harness, CRC baseline, Mondrian, PROOF_NOTE **pending** |
| `tau_star.json` | produced, `certified = false` (50 cal clusters < 59) |
| `decide()` / `confidence()` frozen with tests | code and tests done; `api_schemas.py` pending |
| Drift breaker (Stretch), Trust Console contract (Stretch), ARGUS-Bench (Moonshot) | not started |
| One-shot held-out evaluation, generated `PHASE6_RESULTS.md` | pending, after this file is on `origin/main` |
| Model card, datasheet, mentor report, Phase 7 handoff | pending |
| CI, licence audit, `.env.example` cleanup | CI exists (teammates); licence audit and cleanup pending |
| Emails E3-E5, decisions-log entries | status unknown; decisions-log entry for this plan pending |
| Tag `phase6-complete` | pending |

## 14. Appendix B: evidence behind the scoping (non-test clusters only)

* Gate-only, decision level (first gate-passing draft per cluster, 189 non-test clusters): SFT 0 strict errors, UCB 0.016 overall, **0.181 on the 15 unseen clusters**, 44 more clean unseen clusters needed; RFT 1 error, UCB 0.025, unseen 0 of 15; rft_v2 50 strict errors of 84 clusters (UCB 0.686); zeroshot 4 of 15.
* Grouped 5-fold CV, rft_v2 only: AUROC 0.994 (CI 0.983-1.000) vs prior 0.836; difference +0.158 (CI +0.093 to +0.233); 55 negative clusters; cells: IAM 0.958 (7 positive / 48 negative clusters), sg_open_ingress 1.0, rule6_sg_open_ingress 1.0.
* Pooled CV over all generators: AUROC 0.928 vs prior 0.903 (difference CI -0.052 to +0.097): no win. Inside rft_v2 the pooled model falls to 0.969, and in the IAM cell to 0.693 (CI 0.368-0.952), against 0.958 for the per-generator model.
* Pooled val+cal (P6c): 0.886 vs 0.924. Generator-only baseline AUROC 0.910 (P6b). SFT has 3 negative clusters in total, all `cis.iam_no_full_admin`; its only validation "negative" is a harmless no-op edit.
* Phase 5 context: A = B = C = 349 of 361 per example once finding_id is aligned; 44 of the 361 A_val examples are escalate-route.
