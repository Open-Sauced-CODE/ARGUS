# OOF Greedy Predictions P3 Oracle Summary (Clean Clusters Only)

| Fold | Raw | Excluded (Heldout/A_val) | Clean Clusters | Gate-Pass | Minimal Correct | Gate-Pass-and-Wrong (k) | valid_not_minimal | unknown |
|---|---|---|---|---|---|---|---|---|
| 0 | 55 | 18 | 37 | 37 | 37 | 0 | 0 | 0 |
| 1 | 50 | 15 | 35 | 35 | 35 | 0 | 0 | 0 |
| 2 | 43 | 13 | 30 | 30 | 30 | 0 | 0 | 0 |
| 3 | 41 | 8 | 33 | 33 | 31 | 2 | 0 | 0 |
| **Total** | **189** | **54** | **135** | **135** | **133** | **2** | **0** | **0** |

## Certification Verdict (Partial-Fold Post-OOF)

- Clean OOF clusters: 135
- Existing clean clusters: 15
- Total clean clusters n: **150**
- Clean gate-pass-and-wrong count k: **2**
- Clopper-Pearson minimum n required (alpha=0.05, delta=0.05): **124**
- **Verdict: SUFFICIENT**
- Remaining folds: [4]
- Coverage: Available clean unseen clusters are SUFFICIENT for certification.
