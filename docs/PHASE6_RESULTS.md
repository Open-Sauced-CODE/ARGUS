# Phase 6 Results Summary

## 1. Held-Out Evaluation Status

held-out: not yet run

> Per Hard Rule 5 and stop rule S4: held-out test sets remain sealed and un-opened.
> Held-out evaluation will be run only after OOF harvest ingestion is completed.

## 2. Baseline Test Verification

| Test Suite | Result |
|---|---|
| ml/tests | 124 passed |
| ml/train_m2/tests | 244 passed |

## 3. Cross-Fit Folds Package (P6f-1)

- Seed: 1337
- K: 5
- Total train inputs: 230

| Fold | Total Inputs | Heldout Overlap | In A_val |
|---|---|---|---|
| 0 | 55 | 17 | 16 |
| 1 | 50 | 15 | 13 |
| 2 | 43 | 12 | 11 |
| 3 | 41 | 6 | 7 |
| 4 | 41 | 6 | 8 |

## 4. Calibration & LTT Guarantee Status (tau_star.json)

- Certified: False
- Alpha: 0.05
- Delta: 0.05
- Calibration clusters available (n_total): 50
- Minimum clusters required (n_min): 59
- Tau threshold: None
- Message: only 50 calibration clusters; need >= 59 for alpha=0.05, delta=0.05: autonomy stays OFF (no certified threshold)

## 5. Monte Carlo Guarantee Simulation (mc_guarantee.json)

Regimes evaluated: 4  |  Reps per regime: 2000

| Regime | n_cal | true_err | certified_frac | LTT_coverage | CRC_coverage | CRC_exceeds_alpha | max_cond_error |
|---|---|---|---|---|---|---|---|
| exchangeable_low_error | 80 | 0.02 | 0.9715 | 1.0 | 1.0 | False | 0.02 |
| exchangeable_at_alpha | 80 | 0.05 | 0.6295 | 1.0 | 0.9965 | True | 0.0503 |
| label_shift_adversarial | 80 | 0.02 | 0.3755 | 1.0 | 1.0 | False | 0.0212 |
| covariate_shift_small_n | 30 | 0.08 | 0.0 | 0.0 | 0.9035 | True | 0.0754 |

## 6. Feature Parity Check (parity_500.json)

- Status: **PASS**
- Rows checked: 500
- Mismatches: 0

## 7. Licence Audit (licence_audit.json)

- Total declared packages: 264
  - Permissive: 250
  - Copyleft: 4
  - Unverified / Not Installed: 10
- Base model (Qwen3.5-4B / Qwen2.5): Apache-2.0 (APPROVED)
- C-mined dataset rows: 37 (Copyleft rows: 1)
