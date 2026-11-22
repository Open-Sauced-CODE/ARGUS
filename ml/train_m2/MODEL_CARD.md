# M2 Model Card: ARGUS Trust Engine & Calibrated Auto-Apply

## 1. Model Details

- **Model Name:** ARGUS Trust Engine (M2)
- **Version:** m2-v1 (Phase 6)
- **Model Type:** Calibrated selective classifier (regularised Logistic Regression with Isotonic Calibrator as baseline; per-generator models for primary evaluation)
- **Primary Objective:** Provide calibrated confidence estimates and risk-controlled auto-apply decisions for machine-generated cloud remediation patches that have already passed the QA gate.
- **Decision Unit:** Cluster level (`input_key`, unique model-input hash). One decision per cluster representing the first gate-passing candidate draft.
- **Seed:** 1337
- **Label Definition:** `strict_minimal_correct_v1` (strict oracle: patch passes gate, leaves decoys untouched, introduces no side effects, is minimal, and matches full semantic intent).
- **Primary Generator Evaluated:** `argus-m1-sft` (SFT, Rule 5.2 deployment model).

## 2. Intended Use

- **Primary Intended Use:** Decide whether a verified, gate-passing Patch-IR remediation candidate may safely auto-apply without human intervention in cloud environments (AWS IAM, S3, RDS, CIS Benchmarks, DPDP rules).
- **Execution Context:** M2 acts strictly after the deterministic Rego QA gate. The gate verifies syntax, schema conformity, and rule silence. M2 subsequently scores the semantic confidence of the candidate patch.
- **Scope Restriction:**
  - Valid ONLY for drafts generated under **Harvest Profile A**:
    - Format: Patch-IR JSON schema (`remediate/patch_ir/schema.json`).
    - Modelfile PARAMETERs: `presence_penalty 1.5`, `top_k 20`, `top_p 0.95`.
    - Sampling: sample 0 greedy, samples 1-7 at `temperature 0.7` with seeds 1-7.
    - Runtime: Ollama 0.40.x.
  - Valid ONLY on fix-route candidates. Escalate-route findings and escalate-only patches bypass M2 entirely and route directly to human review.

## 3. What M2 is NOT

- **NOT a Security Guarantee:** M2 is an empirical classifier and risk-control layer. It provides statistical risk bounds under exchangeability assumptions, not formal semantic verification.
- **NOT Valid on Other Generators or Prompts:** M2 confidence calibration is strictly conditioned on Profile A generation. M2 scores are invalid if evaluated on completions from other models, temperatures, prompt templates, or inference engines.
- **NOT Calibrated on Test Sets:** Calibration and threshold selection use non-test clusters exclusively. No held-out test cluster was consulted to choose models, features, calibrators, or thresholds.
- **NOT an Evaluator for Escalate Patches:** Escalate patches bypass M2 by design. Gate-rejected candidates are never scored by M2.

## 4. Training and Calibration Data

- **Harvest Corpus:** 10,272 completions generated from 321 distinct input clusters (`ml/train_m2/contract/harvest_inputs.jsonl`) across 4 generators (`zeroshot`, `sft`, `rft`, `rft_v2`), 8 samples per input.
- **Partitions (`ml/train_m2/out/m2/splits.json`):**
  - Splits SHA256: `6b6b7bf7daa0356593af6f9e207f63016df0c9e580e1fc24092c4364d50ba2bb`
  - Train: 105 clusters (1,770 rows in pooled harvest training)
  - Val: 34 clusters (571 rows in pooled validation; 561 positive, 10 negative)
  - Cal: 50 clusters (includes 15 forced cal clusters from A_val-only inputs)
  - Test: 132 clusters (held-out union of B1, B2, C_verifier, gold; sealed)
- **Features (`ml/train_m2/out/reports/m2_feature_spec.md`):**
  - Spec Hash: `0c099708cff3be6d30e2dadeccd7467d7fd4a452088ec81b4600994310959e50`
  - 35 features spanning 4 active groups:
    - Group U (Uncertainty & Logprobs): token logprob mean, min, p10, std, sequence logprob, op token logprob, value min logprob, entropy mean, margin mean.
    - Group C (Consistency & Sampling): agreement rate, n distinct patches, modal share, greedy is modal, cluster entropy norm, valid-over-requested ratio.
    - Group S (Syntactic & Complexity): op count, counts per op type (set_attr, enable_feature, restrict_cidr, set_lifecycle_rule, add_policy_statement, remove_policy_statement, escalate), rule fields write fraction, patch length, placeholder usage.
    - Group R (Rule & Route Context): rule family indicator, rule code, rule field count, route is escalate.
    - Groups X, G, H of the Master Plan are not implemented.

## 5. Risk Control & Certification (LTT)

- **Framework:** Learn-Then-Test (LTT) fixed-sequence hypothesis testing over a pre-specified threshold grid (`ml/train_m2/risk/ltt.py`, grid SHA256 `3829cdf06e159e6e54869ccfd520324300bac2875a57e0c6b65a546d517b6553`).
- **Nominal Guarantees:** Target error rate alpha = 0.05, failure probability delta = 0.05.
- **Statistical Rule of N:** Minimum calibration sample size required for certification at zero errors is `n_min = 59` clusters (`rule_of_n(0.05, 0.05)`).
- **Current Production Status:**
  - Certified: `false`
  - Threshold `tau`: `null` (autonomy OFF, all gate-passing patches route to human review)
  - Current calibration sample size: `n_total = 50` clusters (50 < 59)
  - Certification Status: **PENDING OOF + one-shot run**

## 6. Known Limitations & Audit Findings

1. **Inherited Contamination (A1-S Audit Check K6):**
   The Phase 5 training set shared 56 input clusters with the held-out test sets (B1: 36/36, B2: 10/10, C_verifier: 32/108, gold: 14/30). While row hashes differ, cluster keys overlap. Primary held-out evaluation is strictly confined to the 92 unseen held-out clusters (76 C_verifier + 16 gold).
2. **Logprob Semantics (A1-S Audit Check K13):**
   In Ollama 0.40.x, presence penalty was applied after token logprobs were recorded. As verified in audit K13, top-1 agreement on greedy sample 0 dropped to 0.931 on zeroshot and 0.916 on rft_v2. Token logprob features reflect pre-penalty logits rather than the exact sampled token distribution.
3. **Tiny Clean Unseen Pool (A1-S Audit Check K12 & Stop Rule S4):**
   Before out-of-fold (OOF) harvesting, only 15 clean unseen clusters exist in non-test data for SFT (A_val-only inputs). This yields an uncertified Upper Confidence Bound (UCB) of 0.181 at 0 errors, leaving 44 clean clusters needed to close stop rule S4.
4. **Natural Negative Scarcity (Stop Rule S1 Triggered):**
   Only 66 distinct usable natural negative patches exist across 61 clusters (rft_v2: 55, zeroshot: 4, sft: 3, rft: 3). With 144 corruptor negatives, the total is 210, missing the pre-registered bar of 300. Primary discrimination evaluation is restricted to generators with non-trivial error rates (rft_v2).
5. **Base Model Licence UNVERIFIED:**
   Base model `unsloth/Qwen3.5-4B` lacks an in-repository licence declaration or commercial grant; its licence status remains UNVERIFIED.

## 7. Performance & Verification Metrics

- **Validation Set (In-Sample Calibration Baseline):**
  - Selected Model: Logistic Regression
  - Selected Calibrator: Isotonic (Val Log-loss: 0.0033, ECE: 0.0)
- **Simulation Verification (Monte-Carlo Guarantee):**
  - LTT coverage across 2,000 repetitions in exchangeable regimes: 1.000 (exceeds 0.94 target).
  - CRC baseline demonstrated failure of conditional error control in covariate shift regime (conditional error 0.0754 > alpha + SE).
- **Feature Parity:**
  - 100% bit-identical match across 500-row replay of harvest features (0 mismatches).
- **Held-Out Evaluation:**
  - Held-out test sets remain sealed.
  - Held-out evaluation metrics: **PENDING**
  - Certified threshold `tau_star`: **PENDING**
  - Stop Rule S4 resolution: **PENDING**
