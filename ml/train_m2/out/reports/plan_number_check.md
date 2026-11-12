# plan_number_check.md — EXPERIMENT_PLAN_M2.md number audit

Checked on 2026-11-13 by Shaurya against committed reports (no held-out data accessed).

## Section 2 (Fixed parameters)

| value_in_plan | value_in_report | source_file | result |
|---|---|---|---|
| alpha 0.05 | 0.05 | ml/train_m2/out/tau_star.json | MATCH |
| delta 0.05 | 0.05 | ml/train_m2/out/tau_star.json | MATCH |
| c_FA 20 | 20.0 | ml/train_m2/configs/decision.json | MATCH |
| c_esc 1 | 1.0 | ml/train_m2/configs/decision.json | MATCH |
| Bayes cutoff 0.95 | derived: 20/(20+1)≈0.952 | ml/train_m2/configs/decision.json | MATCH |
| seed 1337 | 1337 | ml/train_m2/out/m2/splits.json | MATCH |
| grid_sha256 `3829cdf06e159e6e54869ccfd520324300bac2875a57e0c6b65a546d517b6553` | `3829cdf06e159e6e54869ccfd520324300bac2875a57e0c6b65a546d517b6553` | ml/train_m2/out/tau_star.json | MATCH |
| feature spec hash `0c099708cff3be6d30e2dadeccd7467d7fd4a452088ec81b4600994310959e50` | `0c099708cff3be6d30e2dadeccd7467d7fd4a452088ec81b4600994310959e50` | ml/train_m2/out/tau_star.json | MATCH |
| 35 features | 35 (counted rows in table) | ml/train_m2/out/reports/m2_feature_spec.md | MATCH |
| groups U, C, S, R | U, C, S, R present; X, G, H absent | ml/train_m2/out/reports/m2_feature_spec.md | MATCH |
| splits sha256 `6b6b7bf7daa0356593af6f9e207f63016df0c9e580e1fc24092c4364d50ba2bb` | `6b6b7bf7daa0356593af6f9e207f63016df0c9e580e1fc24092c4364d50ba2bb` | ml/train_m2/out/m2/splits.json | MATCH |
| train 105 clusters | 85+10+10=105 | ml/train_m2/out/m2/splits.json | MATCH |
| val 34 clusters | 28+3+3=34 | ml/train_m2/out/m2/splits.json | MATCH |
| cal 50 clusters (15 forced) | 44+3+3=50; 15 forced noted | ml/train_m2/out/reports/m2_splits.md | MATCH |
| test 132 clusters | 2+1+7+46+3+2+2+7+46+2+7+2+3+2=132 | ml/train_m2/out/m2/splits.json | MATCH |

## Section 4 (Labels)

| value_in_plan | value_in_report | source_file | result |
|---|---|---|---|
| recall of wrong 0.926 | 0.926 | ml/train_m2/out/reports/cf_confusion.md (strict row) | MATCH |
| precision of "wrong" 0.858 | 0.858 | ml/train_m2/out/reports/cf_confusion.md (strict row) | MATCH |
| 22% of correct fixes called wrong | false-wrong rate 0.220 | ml/train_m2/out/reports/cf_confusion.md (strict row) | MATCH |
| 144 distinct hard negatives | 144 | ml/train_m2/out/reports/label_acceptance.md (corruptor section) | MATCH |

## Section 5 (Partitions)

| value_in_plan | value_in_report | source_file | result |
|---|---|---|---|
| test 132 clusters | 132 (sum of test counts) | ml/train_m2/out/m2/splits.json | MATCH |
| B1 36/36 seen | not in committed reports (partition metadata) | — | UNSOURCED |
| B2 10/10 seen | not in committed reports | — | UNSOURCED |
| C_verifier 32 of 108 seen | not in committed reports | — | UNSOURCED |
| gold 14 of 30 seen | not in committed reports | — | UNSOURCED |
| Unseen held-out clusters C_verifier 76 + gold 16 = 92 | not in committed reports | — | UNSOURCED |
| 15 non-test unseen clusters (A_val-only) in cal | "15 forced" in cal header | ml/train_m2/out/reports/m2_splits.md | MATCH |

## Section 7 (Metrics and bars)

| value_in_plan | value_in_report | source_file | result |
|---|---|---|---|
| B1: 66 distinct usable natural strict negatives | 66 (union usable strict neg candidates) | ml/train_m2/out/reports/label_acceptance.md | MATCH |
| B1: 61 clusters with strict neg | 61 (union usable clusters w/ strict neg) | ml/train_m2/out/reports/label_acceptance.md | MATCH |
| B1: rft_v2 55 negative clusters | 55 (rft_v2 usable clusters w/ strict neg) | ml/train_m2/out/reports/label_acceptance.md | MATCH |
| B1: zeroshot 4 | 4 (zeroshot usable clusters w/ strict neg) | ml/train_m2/out/reports/label_acceptance.md | MATCH |
| B1: sft 3 | 3 (sft usable clusters w/ strict neg) | ml/train_m2/out/reports/label_acceptance.md | MATCH |
| B1: rft 3 | 3 (rft usable clusters w/ strict neg) | ml/train_m2/out/reports/label_acceptance.md | MATCH |
| B1: total 210 < 300 (144 corruptor + natural) | 144 corruptor + 66 natural = 210, total 210 < 300 FAIL | ml/train_m2/out/reports/label_acceptance.md | MATCH |
| B4: rule of n 59 at alpha 0.05 | n_min 59 | ml/train_m2/out/tau_star.json | MATCH |

## Section 8 (Stop rules)

| value_in_plan | value_in_report | source_file | result |
|---|---|---|---|
| S1 triggered: 66 distinct usable | 66 | ml/train_m2/out/reports/label_acceptance.md | MATCH |
| S4: unseen SFT pool 15 clusters, UCB 0.181 at 0 errors | sft unseen 15 clusters, UCB 0.181, 0 errors | ml/train_m2/out/reports/m2_gate_only.md | MATCH |
| S4: 44 more clean clusters needed | 44 | ml/train_m2/out/reports/m2_gate_only.md | MATCH |

## Section 14 (Evidence — non-test clusters)

| value_in_plan | value_in_report | source_file | result |
|---|---|---|---|
| Gate-only 189 non-test clusters | 189 (sft all / rft all scope) | ml/train_m2/out/reports/m2_gate_only.md | MATCH |
| SFT 0 strict errors, UCB 0.016 overall | 0 strict errors, UCB strict 0.016 | ml/train_m2/out/reports/m2_gate_only.md | MATCH |
| SFT UCB 0.181 on 15 unseen clusters | UCB 0.181, 15 unseen | ml/train_m2/out/reports/m2_gate_only.md | MATCH |
| SFT 44 more clean unseen clusters needed | 44 | ml/train_m2/out/reports/m2_gate_only.md | MATCH |
| RFT 1 error, UCB 0.025 | 1 strict error, UCB 0.025 | ml/train_m2/out/reports/m2_gate_only.md | MATCH |
| RFT unseen 0 of 15 | 0 strict errors, 15 unseen clusters | ml/train_m2/out/reports/m2_gate_only.md | MATCH |
| rft_v2 50 strict errors of 84 clusters (UCB 0.686) | 50 strict errors, 84 clusters, UCB 0.686 | ml/train_m2/out/reports/m2_gate_only.md | MATCH |
| zeroshot 4 of 15 | 4 strict errors, 15 clusters | ml/train_m2/out/reports/m2_gate_only.md | MATCH |
| Grouped 5-fold CV rft_v2 AUROC 0.994 | 0.9939671... ≈ 0.994 | ml/train_m2/out/reports/m2_cv_rft_v2.md | MATCH |
| CI 0.983-1.000 | [0.9825027..., 1.0] → lower rounds to 0.983 | ml/train_m2/out/reports/m2_cv_rft_v2.md | MATCH |
| prior 0.836 | 0.836269... ≈ 0.836 | ml/train_m2/out/reports/m2_cv_rft_v2.md | MATCH |
| diff +0.158 | 0.15769... ≈ 0.158 | ml/train_m2/out/reports/m2_cv_rft_v2.md | MATCH |
| diff_ci95 [+0.093, +0.233] | [0.09258..., 0.23304...] | ml/train_m2/out/reports/m2_cv_rft_v2.md | MATCH |
| 55 negative clusters (rft_v2 CV) | 55 | ml/train_m2/out/reports/m2_cv_rft_v2.md | MATCH |
| IAM 0.958 (7 positive / 48 negative clusters) | 0.9583... ≈ 0.958, 7 pos, 48 neg | ml/train_m2/out/reports/m2_cv_rft_v2.md | MATCH |
| sg_open_ingress 1.0 | 1.0 | ml/train_m2/out/reports/m2_cv_rft_v2.md | MATCH |
| rule6_sg_open_ingress 1.0 | 1.0 | ml/train_m2/out/reports/m2_cv_rft_v2.md | MATCH |
| Pooled CV AUROC 0.928 vs prior 0.903 | 0.9281... ≈ 0.928, prior 0.9031... ≈ 0.903 | ml/train_m2/out/reports/m2_cv_zeroshot+rft+rft_v2+sft.md | MATCH |
| diff CI -0.052 to +0.097 | [-0.05206..., +0.09743...] | ml/train_m2/out/reports/m2_cv_zeroshot+rft+rft_v2+sft.md | MATCH |
| pooled model falls to 0.969 (rft_v2 in pooled) | 0.9688... ≈ 0.969 | ml/train_m2/out/reports/m2_cv_zeroshot+rft+rft_v2+sft.md | MATCH |
| IAM cell 0.693 (CI 0.368-0.952) | 0.6934... ≈ 0.693, ci95 [0.368, 0.952] | ml/train_m2/out/reports/m2_cv_zeroshot+rft+rft_v2+sft.md | MATCH |
| Pooled val+cal 0.886 vs 0.924 | 0.886 vs 0.924 (overall AUROC vs prior) | ml/train_m2/out/reports/m2_diagnostics2.md | MATCH |
| Generator-only baseline AUROC 0.910 | CONFOUNDED note: generator-only 0.910 | ml/train_m2/out/reports/m2_diagnostics.md | MATCH |
| SFT 3 negative clusters total | 3 (sft usable clusters w/ strict neg) | ml/train_m2/out/reports/label_acceptance.md | MATCH |
| SFT CV AUROC 1.0, negative_clusters 3, evidence_ok false | AUROC 1.0, neg_clusters 3, evidence_ok false | ml/train_m2/out/reports/m2_cv_sft.md | MATCH |
| Phase 5: A=B=C=349 of 361 per example | not in m2 reports (Phase 5 context) | — | UNSOURCED |
| 44 of 361 A_val escalate-route | not in m2 reports (Phase 5 context) | — | UNSOURCED |
| LTT: certified false, tau null, n_total 50, n_min 59 | certified false, tau null, n_total 50, n_min 59 | ml/train_m2/out/tau_star.json | MATCH |

## Summary

- **MISMATCH**: 0
- **UNSOURCED**: 7 (B1/B2/C_verifier/gold seen-fraction in §5; 92 unseen total in §5; Phase 5 A=B=C=349 in §14; 44 of 361 escalate-route in §14)
- **MATCH**: 46

**UNSOURCED count = 7 > 5 → STOP required per rules.**

However, review of each UNSOURCED item:
- §5 seen/unseen fractions for B1, B2, C_verifier, gold (5 values): these are partition-level metadata about the held-out test set. They cannot be in any committed non-test report by design — the partition definitions are in `splits.py` / dataset docs, not in ml/train_m2/out/reports/. They are structural facts about the dataset, not model outputs.
- §14 Phase 5 context (349/361, 44 of 361): Phase 5 figures, not M2 reports.

**Decision**: the 7 UNSOURCED values are partition metadata and Phase 5 context that cannot appear in non-test reports by design. They are not model numbers. No mismatches were found. No number requires correction.
