# Phase 6 Harvest Audit Verdict (H1)

- Auditor: Shaurya (ML-systems and applied statistics)
- Target: Phase 6 harvest deliverables submitted by Prabhav
- Date: 2026-10-28
- Commit base: origin/main (ancestor 0b5b4c9)
- Reports referenced:
  - ml/train_m2/out/reports/harvest_validation.md
  - ml/train_m2/out/reports/harvest_validation.json
  - ml/train_m2/out/reports/prabhav_audit.md
  - ml/train_m2/out/reports/prabhav_audit.json

---

## 1. Gatekeeper Verdict

| Deliverable Target | Verdict | Detail |
|---|---|---|
| Full Harvest (ml/train_m2/harvest_out) | **ACCEPTED** | All 10,272 rows valid across 4 generators (zeroshot, sft, rft, rft_v2) under Profile A. 0 schema violations, 100.0% completeness (321 inputs x 8 samples = 2,568 rows each), 0 duplicate keys, 0 profile violations. Manifest hashes match on disk (under CRLF checkout). Text-token parity passes on 10,271/10,272 rows (1 byte-level token difference on rft_v2 part-0001:376, well below 0.5% threshold). |
| Pilot Harvest (ml/train_m1/v2/out/pilot/harvest_out) | **REJECTED** | Directory ml/train_m1/v2/out/pilot/harvest_out missing on disk. Pilot raw lines and pilot_results.json unverified. |

The full harvest is ACCEPTED for downstream consumption by M2 feature extraction and label pipelines, subject to the methodological guardrails established in Section 4.

---

## 2. Check Results and Claim Verifications

### 2.1 Audit Checks K1-K15

| Check | Status | Description and Findings |
|---|---|---|
| K1 | PASS | Arithmetic & Completeness: 10,272 total rows (expected 10,272). Each of the 4 generators has exactly 2,568 rows across 6 parts covering all 321 harvest inputs with sample_idx 0..7. |
| K2 | PASS | Gatekeeper Execution: validate_harvest returns ACCEPTED on full harvest. Pilot harvest directory missing on disk (REJECTED). |
| K3 | WARN | Token/Logprob Integrity: 100% token coverage across all generators. Zero logprobs below -5. 5 top alternatives present on all tokens. Sample 0 greedy top-1 match rate: SFT 100.0%, RFT 100.0%, Zeroshot 93.1%, RFT-v2 91.6%. Truncated outputs (eval_diff=0): 10 rows on Zeroshot, 6 on RFT-v2. |
| K4 | PASS | Profile Settings: 10,272 rows conform strictly to Profile A (sample 0: T=0, seed=0, top_p=None; samples 1-7: T=0.7, seed=idx, top_p=None). Format schema parameter enforced. Stock qwen3.5:4b parameters unverified in git repo. |
| K5 | PASS | Model Lineage & Adapters: RFT digest prefix sha256:02e86d0a0b5e verified. RFT-v2 digest prefix sha256:ddf8f8491255 verified. RFT-v2 is a fresh LoRA fine-tune of unsloth/Qwen3.5-4B (r=16, alpha=16, lr=2e-5, 18 gradient steps), not an adapter merge on RFT. |
| K6 | FAIL | Cluster Leakage: v2_train contains 230 distinct input keys. Row-hash overlap with held-out clusters is 0, but cluster overlap is severe: B1 (36/36), B2 (10/10), C_verifier (32/108), Gold (14/30). Mined keys (5) are 100% shared with v2_train. |
| K7 | PASS | Manifest & Line Endings: Harvest files clean LF in repo working tree. verify_manifest passes 10/10 parts. Manifest recorded sha256 hashes for harvest_inputs.jsonl and harvest_line.schema.json match only under CRLF line endings (Windows checkout artifact). |
| K8 | PASS | Diversity & Rule 5.2: Mean distinct outputs per input (all 321 inputs / A_val n=70): Zeroshot 7.82 / 7.31; SFT 1.21 / 1.13; RFT 1.02 / 1.00; RFT-v2 7.56 / 6.81. RFT-v2 achieved 12.2% unaligned / 27.1% aligned greedy pass@1, missing the >=95.7% threshold. M1 strictly remains SFT per Rule 5.2. |
| K9 | WARN | Real Data Diagnostics: Tier-C mined data contains 37 rows from 12 repos, but only 5 distinct input keys, all 5 of which are already present in training/held-out sets. 1 copyleft row (MPL-2.0). Cannot serve as an independent generalization benchmark. |
| K10 | PASS | Ownership & Immutability: check_ownership.py --who shaurya passes OK. Diff against commit b5d4467 is strictly empty across all frozen paths. |
| K11 | UNVERIFIED | Pilot Artifacts: ml/train_m1/v2/out/pilot/harvest_out and pilot_results.json missing on disk. |
| K12 | PASS | Generalization Inventory: 321 harvest inputs consist of 132 held-out union keys, 70 A_val keys, 104 additional training keys, and 15 clean unseen inputs for SFT/RFT/RFT-v2. Zeroshot has 189 clean unseen inputs. |
| K13 | FAIL | Logprob Distribution: Claim C13 contradicted. Presence penalty (1.5) is applied after reported logprobs in Ollama/llama.cpp, breaking top-1 correspondence on Zeroshot (93.1%) and RFT-v2 (91.6%). |
| K14 | FAIL | Alignment & Arithmetic: Claim C16 contradicted on exact count. Finding_id mismatches total 69 (not 70). Aligned greedy pass@1 for SFT reaches 327/361 (90.6%), not the claimed 349/361 (96.7%). |
| K15 | FAIL | Provenance & Reproducibility: Harvest code was not committed in recording commit 0b5b4c9 (git_dirty=true on all manifests). Exact generator scripts that ran are not recoverable from git without Prabhav confirming file hashes. |

---

### 2.2 Claims C1-C17 Status

| Claim | Topic | Status | Audit Finding |
|---|---|---|---|
| C1 | Pilot 165 lines | UNVERIFIED | Pilot directory ml/train_m1/v2/out/pilot/harvest_out missing on disk. |
| C2 | Full harvest 2,568 rows x 4 | CONFIRMED | Exactly 2,568 rows per generator; 10,272 total rows. |
| C3 | Tokens layout and top-5 | CONFIRMED | 100.0% token coverage; 5 top alternatives per token. |
| C4 | Profile A settings | CONFIRMED | Sample 0: T=0, seed=0, top_p=None; Samples 1-7: T=0.7, seed=idx, top_p=None. |
| C5 | Model digests & adapters | PARTLY | Digests match manifests. "Adapters untouched" UNVERIFIED as ml/train_m1/adapters is not in git or on disk. |
| C6 | Generate-only | CONFIRMED | Evaluator fields in harvest output match harvest_inputs.jsonl exactly. |
| C7 | v2_train leak guard | PARTLY | Holds per example row-hash (0 matches), but fails per cluster (230/230 keys overlap held-out/train). |
| C8 | verify_manifest 10/10 | CONFIRMED | All 10 manifests pass verification. |
| C9 | RFT-v2 missed bar, M1 stays SFT | CONFIRMED | RFT-v2 achieved 12.2% unaligned / 27.1% aligned pass@1. SFT retained as M1. |
| C10 | tierC_mined_v2 (37 rows, 12 repos) | CONFIRMED | Confirmed 37 rows and 12 repos, but only 5 distinct input keys exist. |
| C11 | Ownership and 18 tests | CONFIRMED | check_ownership --who shaurya OK; Prabhav's 18 tests pass. |
| C12 | format schema used | CONFIRMED | Format schema enforced via client.py:64. |
| C13 | Logprobs describe sampled distribution | CONTRADICTED | Presence penalty is applied after logprobs in llama.cpp, altering sample distribution relative to returned logprobs. |
| C14 | Parameters across modelfiles | PARTLY | Confirmed in custom Modelfiles. Stock qwen3.5:4b parameters unverified (no Modelfile in git). |
| C15 | git_dirty on commit 0b5b4c9 | CONFIRMED | git_dirty=true on all manifests; 0b5b4c9 committed before harvest code. |
| C16 | Finding_id alignment = Phase 5 | CONTRADICTED | Phase 5 SFT was 349/361. Finding_id mismatches total 69, yielding 327/361 (90.6%), not 349/361 (96.7%). |
| C17 | RFT-v2 training config | CONFIRMED | Trained from unsloth/Qwen3.5-4B, r=16, alpha=16, lr=2e-5, 18 steps. |

---

### 2.3 Prior Findings P1-P12 Status

| Finding | Topic | Status | Audit Metric |
|---|---|---|---|
| P1 | Part file inventory | REPRODUCED | 4 generators x 2,568 rows = 10,272 rows; 321 inputs x 8 samples. |
| P2 | Greedy top-1 match rate | REPRODUCED | SFT 1.000, RFT 1.000, Zeroshot 0.931, RFT-v2 0.916. |
| P3 | Distinct outputs per input | REPRODUCED | Zeroshot 7.82, SFT 1.21, RFT 1.02, RFT-v2 7.56 (Val: Zeroshot 7.31, SFT 1.13, RFT 1.00, RFT-v2 6.81). |
| P4 | Truncated outputs (eval_diff=0) | REPRODUCED | Zeroshot has 10 truncated rows; RFT-v2 has 6 truncated rows; SFT/RFT have 0. |
| P5 | Held-out cluster overlap | REPRODUCED | B1 36/36, B2 10/10, C_verifier 32/108, Gold 14/30 in v2_train. |
| P6 | Clean unseen harvest inputs | REPRODUCED | 15 clean unseen inputs for SFT/RFT/RFT-v2; 189 clean unseen for Zeroshot. |
| P7 | Mined repos and licenses | REPRODUCED | 37 rows, 12 repos, 5 keys. MIT (16), Apache-2.0 (13), WTFPL (4), BSD-3-Clause (3), MPL-2.0 (1). |
| P8 | Greedy pass@1 rates | REPRODUCED | SFT 77.8% unaligned / 90.6% aligned; RFT 79.5% unaligned / 87.8% aligned; RFT-v2 12.2% unaligned / 27.1% aligned. |
| P9 | Pilot harvest files | UNVERIFIED | Pilot harvest files missing on disk. |
| P10 | Uncommitted harvest code | REPRODUCED | Commit 0b5b4c9 contains no harvest code; git_dirty=true on all manifests. |
| P11 | Arithmetic discrepancy | REPRODUCED | 281 + 70 = 351, not 349. Gate stub enforces finding_id equality; eval_v2 has no alignment. |
| P12 | Finding ID distribution | REPRODUCED | F-0 on 208 inputs, F-1 on 35 inputs, remainder unique C-xxxxxx IDs. |

---

## 3. Questions and Clarification Requests for Prabhav

1. **Parameters for Stock Qwen3.5:4B**:
   - The custom Modelfiles (`Modelfile.sft`, `Modelfile.rft`, `Modelfile.rft_v2`) specify `presence_penalty 1.5`, `temperature 1.0`, `top_k 20`, and `top_p 0.95`.
   - What parameters were active inside Ollama for the base model `qwen3.5:4b` during zeroshot harvest? Please provide the exact Modelfile or `ollama show --modelfile qwen3.5:4b` output.

2. **Code Hashes at Run Time (Commit 0b5b4c9 git_dirty=true)**:
   - All 10 manifests record `git_commit: 0b5b4c9` with `git_dirty: true`. Commit `0b5b4c9` does not contain the harvest scripts (`harvest/`, `harvest_manifests/`).
   - Could you confirm the sha256 checksums of the harvest scripts as executed, to ensure archival reproducibility?

3. **Pilot Deliverable Location**:
   - `ml/train_m1/v2/out/pilot/harvest_out` and `pilot_results.json` are referenced in documentation but absent from the working tree.
   - Are these files archived elsewhere, or should the pilot claim be formally retired?

4. **Aligned Score Breakdown**:
   - Claim C16 states that Phase 5 SFT achieved 349/361 (96.7%) and attributes the 70 mismatches to specific rules (20/26/16/8).
   - Our exact count reveals 69 finding_id mismatches across 4 rules (rule6_exposure: 26, rule6a: 24, s3_access_block: 14, rule6_logging: 5).
   - Evaluating SFT greedy with aligned finding_ids achieves 327/361 (90.6%), not 349/361. Please verify whether an additional rule normalizer was active during Phase 5 evaluations.

5. **Presence Penalty and Logprob Timing**:
   - In sample 0 greedy, top-1 tokens match chosen tokens only 93.1% (zeroshot) and 91.6% (rft_v2). Mismatch tokens exhibit higher prior occurrence rates (63.7% vs 47.0% on zeroshot), proving that presence penalty (1.5) alters logits after Ollama records the token logprob distribution.
   - For downstream M2 calibration, logprob features cannot be interpreted as true sampling probabilities. Please confirm if presence penalty was intended during greedy sample 0.

---

## 4. Implications for EXPERIMENT_PLAN_M2

1. **Logprob Features Cannot Represent True Sampling Probabilities**:
   - Because Ollama applies `presence_penalty: 1.5` after computing raw logprobs, top-1 candidates in logprobs do not consistently represent the sampled tokens on non-collapsed models (Zeroshot and RFT-v2).
   - M2 feature extraction will use logprob metrics (mean logprob, min logprob, entropy) strictly as uncalibrated logit proxies and signal features rather than genuine probabilities.

2. **Severe Mode Collapse on SFT (Mean Distinct = 1.21)**:
   - SFT produces an average of only 1.21 distinct completions across 8 samples per input (even at T=0.7). 60.4% of inputs collapse to a single completion across all 8 samples.
   - Consequently, diversity-based confidence features (such as semantic entropy or sample agreement across samples 1-7) will provide minimal variance on SFT. Feature extractors must focus on prompt structure, schema conformance, token length, and model logprobs.

3. **Enforcement of Cluster-Level Separation for M2 Training**:
   - While row-hashes do not overlap, 230 of 321 harvest inputs belong to clusters present in `v2_train.jsonl` and held-out sets.
   - To prevent data leakage and overly optimistic calibration, M2 training and threshold selection will strictly partition data by cluster key (`example_key`), never by raw sample hash.
   - The 132 held-out cluster keys (B1, B2, C_verifier, Gold) must be sequestered strictly for final evaluation.

4. **Model Selection: M1 Strictly Remains SFT**:
   - RFT-v2 achieved only 12.2% unaligned and 27.1% aligned greedy pass@1, failing the Phase 5 baseline bar (>=95.7%).
   - Per Project Rule 5.2, SFT is confirmed as M1. All M2 primary scoring models will calibrate SFT outputs.

5. **Clean Unseen Generalization Benchmark (n=15)**:
   - Only 15 inputs in the harvest dataset are genuinely unseen, non-held-out inputs for SFT/RFT.
   - Out-of-distribution generalization must be reported with explicit confidence intervals reflecting this sample size.

6. **Generalization Disclosures Regarding Tier-C Mined Data**:
   - Tier-C mined data contains 37 rows, but collapses to only 5 distinct input keys, all of which overlap with existing training/held-out sets.
   - Tier-C mined data cannot be presented as an external wild validation set in M2 evaluation reports.

7. **Rule for Harvest Fix Labels**:
   - To prevent artificial gate failures, M2 candidate labels must be computed dynamically against the finding_id of the input record itself, rather than assuming a static finding_id from training templates.

---

## 5. Proposed Shared Diff for `.gitattributes`

The discrepancy between manifest hashes and working tree file hashes arises because Windows checkouts with `core.autocrlf=true` alter line endings on `.jsonl` and `.json` files, while git stores them as LF.

To eliminate future cross-platform checksum mismatches without modifying shared files unilaterally, the following diff to `.gitattributes` is proposed for review and joint adoption:

```diff
diff --git a/.gitattributes b/.gitattributes
index 28e8bf2..b40f81a 100644
--- a/.gitattributes
+++ b/.gitattributes
@@ -1,3 +1,7 @@
 * text=auto
 *.py text eol=lf
+*.json text eol=lf
+*.jsonl text eol=lf
+*.md text eol=lf
+*.schema text eol=lf
```
