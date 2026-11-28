# OOF Greedy Predictions P3 Oracle Summary (Clean Clusters Only)

| Fold | Raw | Excluded (Heldout/A_val) | Clean Clusters | Gate-Pass | Minimal Correct | Gate-Pass-and-Wrong (k) | valid_not_minimal | unknown |
|---|---|---|---|---|---|---|---|---|
| 0 | 55 | 18 | 37 | 37 | 37 | 0 | 0 | 0 |
| 1 | 50 | 15 | 35 | 35 | 35 | 0 | 0 | 0 |
| 3 | 41 | 8 | 33 | 33 | 31 | 2 | 0 | 0 |
| **Total** | **146** | **41** | **105** | **105** | **103** | **2** | **0** | **0** |

## Certification Verdict (Partial-Fold Post-OOF)

- Clean OOF clusters: 105
- Existing clean clusters: 15
- Total clean clusters n: **120**
- Clean gate-pass-and-wrong count k: **2**
- Clopper-Pearson minimum n required (alpha=0.05, delta=0.05): **124**
- Margin (n - cp_min_n): **-4**
- **Verdict: NEED 4 MORE CLEAN CLUSTERS**
- Remaining folds: [2, 4]
- Coverage: Remaining fold(s) [2] provide 30 clean clusters, covering the deficit of 4.
- Note: the certificate depends on accepted drafts at tau, so the effective n is smaller; do not estimate it.
