# DIAGNOSTIC ESTIMATE, folds 2 and 4 truncated at first JSON; not evidence for certification; replace with regenerated preds

| Fold | Diagnostic Truncated | Raw | Excluded (Heldout/A_val) | Clean Clusters | Gate-Pass | Minimal Correct | Gate-Pass-and-Wrong (k) | valid_not_minimal | unknown | Near-Dups | Remaining Clean |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | False | 55 | 18 | 37 | 37 | 37 | 0 | 0 | 0 | 9 | 28 |
| 1 | False | 50 | 15 | 35 | 35 | 35 | 0 | 0 | 0 | 8 | 27 |
| 2 | True | 43 | 13 | 30 | 30 | 30 | 0 | 0 | 0 | 3 | 27 |
| 3 | False | 41 | 8 | 33 | 33 | 31 | 2 | 0 | 0 | 5 | 28 |
| 4 | True | 41 | 8 | 33 | 33 | 33 | 0 | 0 | 0 | 5 | 28 |
| **Total** | **True** | **230** | **62** | **168** | **168** | **166** | **2** | **0** | **0** | **30** | **138** |

## Diagnostic Clopper-Pearson Estimate (alpha=0.05, delta=0.05, NOT for certification)

| Version | OOF Clean | Existing | Total n | k | cp_min_n | Margin | Verdict |
|---|---|---|---|---|---|---|---|
| (a) All clean clusters | 168 | 15 | 183 | 2 | 124 | +59 | SUFFICIENT |
| (b) After removing near-duplicates | 138 | 15 | 153 | 2 | 124 | +29 | SUFFICIENT |

> The certificate depends on accepted drafts at tau, so the effective n is smaller; do not estimate it.
