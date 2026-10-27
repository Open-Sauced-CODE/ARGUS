# Independent Audit of Phase 6 Harvest Deliverables (A1-S)

## Executive Summary

- Full Harvest Delivery: **ACCEPTED** by validate_harvest gatekeeper (all 10,272 lines schema-valid, 100% coverage).
- Scientific & Contamination Verdict: **SIGNIFICANT FINDINGS** across contamination, logprob semantics, and scoring.

## Checks K1 to K15

| Check | Name | Status | Detail |
|---|---|---|---|
| K1 | Inventory / Arithmetic | **PASS** | total rows 10272 (expected 10,272); zeroshot: 2568 rows, 321/321 inputs (all-8: 321); sft: 2568 rows, 321/321 inputs (all-8: 321); rft: 2568 rows, 321/321 inputs (all-8: 321); rft_v2: 2568 rows, 321/321 inputs (all-8: 321) |
| K2 | Validator Verdicts | **PASS** | full harvest: ACCEPTED; pilot: REJECTED (missing on disk) |
| K3 | Tokens / Logprobs Integrity | **WARN** | zeroshot: tok_frac=100.0%, bad_lp=0, min_top=5, s0_top1=0.931, text_mismatch=0/2568, mean_tok=126.6, eval_diff={1: 2558, 0: 10}; sft: tok_frac=100.0%, bad_lp=0, min_top=5, s0_top1=1.000, text_mismatch=0/2568, mean_tok=66.0, eval_diff={1: 2568}; rft: tok_frac=100.0%, bad_lp=0, min_top=5, s0_top1=1.000, text_mismatch=0/2568, mean_tok=65.8, eval_diff={1: 2568}; rft_v2: tok_frac=100.0%, bad_lp=0, min_top=5, s0_top1=0.916, text_mismatch=1/2568, mean_tok=108.8, eval_diff={1: 2562, 0: 6} |
| K4 | Sampling & Parameters Conformance | **PASS** | all 10,272 rows conform to profile A settings; C12 confirmed: True; Modelfiles found: 3 (stock qwen3.5:4b UNVERIFIED - no Modelfile in repo) |
| K5 | Checkpoint Identity & Adapters | **PASS** | rft digest prefix 02e86d0a0b5e present: True; rft_v2 prefix ddf8f8491255 present: True; rft_v2 is a fresh fine-tune of base unsloth/Qwen3.5-4B (r=16 alpha=16 lr=2e-5, 18 steps), not a refinement of rft; UNVERIFIED (ml/train_m1/adapters not on disk / git-ignored) |
| K6 | Contamination Audit (Cluster Level) | **FAIL** | v2_train distinct keys: 230; overlap with B1: 36/36, B2: 10/10, C_verifier: 32/108, gold: 14/30 (inherited from Phase 5); row-hash overlap: 0 (C7 holds per example but not per cluster); mined keys (5) shared with v2_train: 5, with held-out: 5 |
| K7 | Line Endings & File Integrity | **PASS** | harvest files CRLF count: 0; verify_manifest: 10/10 PASS; manifest recorded CRLF hashes for inputs/schema due to Windows core.autocrlf |
| K8 | Numeric Claims & Diversity | **PASS** | mean distinct (all 321 / A_val n=70): zeroshot=7.82/7.31, sft=1.21/1.13, rft=1.02/1.0, rft_v2=7.56/6.81; PLAN_V2.md numbers (sft 1.45, rft_v2 6.39) were A_val/pilot; Rule 5.2 follows since rft_v2 missed >=95.7% bar (got 12.2% unaligned, 27.1% aligned) |
| K9 | Tier C Mined V2 Dataset | **WARN** | rows: 37, distinct keys: 5, repos: 12, copyleft: 1 rows in 1 repos (MPL-2.0); C-mined cannot serve as an independent real-world test set (only 5 distinct inputs, all seen in train/held-out) |
| K10 | Ownership & Frozen Boundaries | **PASS** | ownership OK: True; frozen diff against b5d4467 empty: True |
| K11 | Pilot Verification | **UNVERIFIED** | pilot raw files in ml/train_m1/v2/out/pilot/harvest_out and pilot_results.json missing on disk |
| K12 | Generator-Seen Inputs Breakdown | **PASS** | 321 harvest inputs: held-out union=132, A_val=70; zeroshot: seen=0, unseen=321, clean_unseen=168; sft: seen=230, unseen=91, clean_unseen=0; rft: seen=230, unseen=91, clean_unseen=0; rft_v2: seen=230, unseen=91, clean_unseen=0; for sft/rft/rft_v2, 15 unseen inputs are not held-out and not in train; zeroshot has 189 |
| K13 | Logprob Semantics (Claim C13) | **FAIL** | Claim C13 CONTRADICTED: greedy sample 0 top-1 rate is 0.931 for zeroshot and 0.916 for rft_v2 (< 0.99); mismatch seen share is higher than match (zeroshot: 63.7% vs 47.0%, rft_v2: 58.5% vs 39.5%), showing presence penalty applied AFTER logprobs. Logprob features on zeroshot and rft_v2 reflect raw logits before penalty. |
| K14 | Scoring Protocol & Finding-ID (Claim C16) | **FAIL** | Claim C16 PARTLY confirmed on mechanism but CONTRADICTED on exact match: Phase 5 SFT 349/361 (96.7%) reproduced; finding_id mismatches total 69 (not 70): {'dpdp.rule6_public_exposure': 26, '_total': 69, 'dpdp.rule6_logging': 5, 'cis.s3_public_access_block': 14, 'dpdp.rule6a': 24}; aligned greedy pass@1 for SFT reaches 327/361 (90.6%), not 349/361. Harvest labels must be computed against harvest input's own finding_id. |
| K15 | Harvest Code Provenance | **FAIL** | Harvest code not in recorded commit 0b5b4c9 (git_dirty=true on all manifests); code that ran is NOT recoverable from git without explicit file hashes from Prabhav; inputs/schema manifest hashes match files only with CRLF line endings. |
