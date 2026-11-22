# Phase 6 Mentor Report: ARGUS Trust Engine & Safe Auto-Apply

## 1. Executive Summary & Research Question

Phase 5 delivered M1, a fine-tuned local language model that drafts Patch-IR fixes for cloud security misconfigurations. Phase 6 addresses the core safety question for Phase 7 deployment:

> **Core Question:** Can a calibrated confidence model (M2) paired with a statistical risk-controlled threshold allow ARGUS to safely auto-apply a meaningful fraction of remediation patches while guaranteeing that the error rate among auto-applied patches does not exceed 5% (alpha = 0.05) with 95% confidence (1 - delta = 0.95) on inputs the model has never seen?

Our findings confirm that statistical risk control is theoretically sound and empirically validated in simulation. However, in production, autonomy remains safely OFF (all patches route to human review) because the non-test calibration pool currently contains only 50 clusters, falling short of the statistical minimum of 59 clusters required for finite-sample certification.

## 2. Approach & Architecture

We implemented a defense-in-depth pipeline that strictly isolates validation from decision-making:

1. **Gate Pre-Filter:** The deterministic Rego QA gate checks syntax, schema conformance, and policy silence. Only gate-passing fix candidates reach M2. Escalate-route inputs bypass M2 and route to human operators.
2. **Cluster-Level Statistical Unit:** All data splitting, cross-validation, bootstrapping, and calibration operate on unique input hashes (`input_key`). Rows sharing an input key never cross partition boundaries.
3. **Learn-Then-Test (LTT) Risk Control:** Rather than relying on heuristic confidence cutoffs, we implemented LTT fixed-sequence hypothesis testing over a pre-registered threshold grid.
4. **Per-Generator Trust Modeling:** Initial investigations revealed that a pooled M2 model functioned primarily as a generator detector. Consequently, M2 was re-scoped to per-generator classifiers, using SFT as the primary deployment generator and rft_v2 as a weak-generator benchmark.

## 3. What Was Built

Across Phase 6, we delivered an end-to-end trust architecture:
- **Feature Store:** 35 features across uncertainty/logprobs, sampling consistency, syntactic complexity, and rule context (spec hash `0c099708cff3be6d30e2dadeccd7467d7fd4a452088ec81b4600994310959e50`).
- **Leak-Proof Partitions:** Seeded cluster-level splits ensuring complete test isolation (splits hash `6b6b7bf7daa0356593af6f9e207f63016df0c9e580e1fc24092c4364d50ba2bb`).
- **Risk Calibration Engine:** Fixed-sequence LTT implementation in `ml/train_m2/risk/ltt.py` and threshold certification in `ml/train_m2/risk/calibrate_tau.py`.
- **Inference & Auditing API:** `confidence()` and `decide()` entry points in `ml/train_m2/decide.py` and strict Pydantic schemas in `ml/train_m2/api_schemas.py`.
- **Cross-Fit OOF Protocol:** Complete 5-fold cross-fit specification (`docs/phase6_shaurya/crossfit/`) to generate out-of-fold completions.
- **Automated Post-OOF Pipeline:** Dry-run runner (`ml/train_m2/eval/post_oof.py`) chaining OOF ingestion, re-split proposals, model retraining, and tau re-calibration.

## 4. What Is Proven

1. **Theoretical Guarantee (`docs/phase6_shaurya/PROOF_NOTE.md`):** Under exchangeability and cluster-level decisions, LTT guarantees that the selective error rate P(wrong | auto-applied) <= alpha with probability at least 1 - delta over calibration draws.
2. **Monte-Carlo Validation (`ml/train_m2/out/reports/mc_guarantee.md`):** Over 2,000 repetitions across four distributional regimes, empirical LTT coverage reached 1.000 in exchangeable regimes (exceeding the 0.94 target). Crucially, the alternative CRC joint-error baseline failed conditional error control, yielding a conditional error rate of 0.0754 (exceeding alpha = 0.05 by more than standard error).
3. **Feature Parity (`ml/train_m2/out/reports/parity_500.md`):** Training and inference feature generation demonstrated 100% bit-identical parity across a 500-row real harvest replay with zero mismatches.

## 5. Data Limitations & Honest Caveats

- **Stop Rule S1 Triggered:** Only 66 distinct usable natural negative patches exist in non-test data (rft_v2: 55, zeroshot: 4, sft: 3, rft: 3). SFT is essentially never wrong on seen inputs (pass@1 of 96.7%), preventing discrimination evaluation on SFT alone.
- **Stop Rule S4 Active:** Pre-OOF non-test data provides only 15 clean unseen clusters for SFT. With 50 total calibration clusters, the calibration pool is below the rule of 59 (`n_min = 59`). Autonomy is therefore OFF (`certified = false`, `tau = null`).
- **Inherited Contamination:** 56 training inputs overlap with held-out test clusters from Phase 5. Primary held-out evaluation is strictly limited to the 92 unseen held-out clusters.
- **Ollama Logprob Semantics:** Presence penalty was applied after logprob computation, decoupling raw token logprobs from the final sampled tokens.
- **Base Model Licence:** Foundation model `unsloth/Qwen3.5-4B` licence remains UNVERIFIED.

## 6. What Is Pending

Held-out test sets (`B1`, `B2`, `C_verifier`, `gold`) remain strictly sealed under Hard Rule 5. The following components remain **PENDING**:
- Delivery and validation of Prabhav's 5-fold SFT out-of-fold harvest.
- Post-OOF re-split and threshold re-calibration via `post_oof.py`.
- One-shot evaluation execution on unseen held-out clusters.
- Final held-out metrics and certification status: **PENDING**.
