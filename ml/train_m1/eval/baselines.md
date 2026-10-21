# ARGUS Phase 5 - Baseline Evaluation (Step 15)

Date: 2026-10-22  
Model: `qwen3.5:4b` (Qwen3.5-4B base model)  
Status: Frozen (all baseline rows completed; held-out sets scored strictly once per Rule 5.1).

---

## 1. Baseline Summary Table

| Model / Strategy | Decoding / Gate | A_val (361) | train300 (300) | Tier B1 (261) | Tier B2 (180) | Tier C_verifier (466) | Gold (80) |
|---|---|---|---|---|---|---|---|
| **T0 Templates Only** | Deterministic rule-match | 196/361 (54.3%) | 113/300 (37.7%) | 181/261 (69.3%) | 140/180 (77.8%) | 321/466 (68.9%) | 49/80 (61.2%) |
| **Zero-Shot Base (pass@1)** | Constrained, 1 sample | 96/361 (26.6%) | 55/300 (18.3%) | 103/261 (39.5%) | 140/180 (77.8%) | 166/466 (35.6%) | 29/80 (36.2%) |
| **Zero-Shot Best-of-8 (pass@8)** | Constrained, 8 samples + gate | 176/361 (48.8%) | 116/300 (38.7%) | 132/261 (50.6%) | 140/180 (77.8%) | 173/466 (37.1%) | 31/80 (38.8%) |

*Note: All gate-passing T0 responses achieved a 100% gate pass rate on the subsets they cover.*

---

## 2. Safety, Schema Validity, and Latency

| Set | Schema-Valid Candidates | Unsafe Candidates | Median Seconds to First Pass |
|---|---|---|---|
| **A_val** | 551 / 560 (98.4%) | 391 / 560 (69.8%) | 5.01s |
| **train300** | 687 / 696 (98.7%) | 513 / 696 (73.7%) | 10.86s |
| **B1** | 288 / 288 (100.0%) | 126 / 288 (43.8%) | 6.39s |
| **B2** | 80 / 80 (100.0%) | 15 / 80 (18.8%) | 5.54s |
| **C_verifier** | 863 / 864 (99.9%) | 787 / 864 (91.1%) | 7.28s |
| **gold** | 240 / 240 (100.0%) | 190 / 240 (79.2%) | 7.39s |

---

## 3. Key Findings

1. **Schema Compliance**: The base model conforms to the JSON schema in 98–100% of cases, validating our fixed chat prompt format without requiring prompt fine-tuning.
2. **Safety Headroom**: 40–90% of raw un-tuned candidates are flagged as unsafe or touch forbidden fields, confirming the necessity of SFT and RFT.
3. **Pass Bar Target for SFT**: In Tier B1, zero-shot best-of-8 achieves 50.6%. To clear pass bar 5.2, SFT best-of-8 must achieve $\ge 60.6\%$ (a 10 percentage-point gain, $p < 0.05$). On `A_val`, SFT must target $\ge 80\%$ on the T0-uncovered subset.
4. **Model Size**: Qwen3.5-4B is confirmed as the production size for Stage D iteration.
