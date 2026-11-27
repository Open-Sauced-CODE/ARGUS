# Near-Duplicate Check: Clean OOF Clusters vs Fold Training Sets

- Folds analyzed: [0, 1, 2, 3]
- Clean OOF clusters analyzed: **135**
- Identical normalized signature in training: **25** (18.5%)
- Near-duplicates (identical normalized sig OR Jaccard >= 0.80): **25** (18.5%)
- Remaining clean clusters after removing near-duplicates: **110**

> **WARNING:** OOF clusters are not independent of training; clean counts overstate unseen clusters
> Remaining independent clean clusters after removal: **110** / 135

## Per-Fold Breakdown (Counts Only)

| Fold | Clean Clusters | Identical Norm Sig | Near-Dups (Exact or >= thr) | Near-Dup Rate | Remaining |
|---|---|---|---|---|---|
| 0 | 37 | 9 | 9 | 24.3% | 28 |
| 1 | 35 | 8 | 8 | 22.9% | 27 |
| 2 | 30 | 3 | 3 | 10.0% | 27 |
| 3 | 33 | 5 | 5 | 15.2% | 28 |

## Max Jaccard Similarity Distribution (Token Shingles, Same Rule)

| Similarity Bin | Cluster Count |
|---|---|
| [0.0, 0.2) | 7 |
| [0.2, 0.4) | 54 |
| [0.4, 0.6) | 46 |
| [0.6, 0.8) | 3 |
| [0.8, 1.0) | 0 |
| 1.0 | 25 |

## OOF Gate Pass Rate Comparison (Counts Only)

| Subset | Clusters | Gate-Pass | Gate-Fail | Minimal Correct | Wrong (k) | Gate-Pass Rate |
|---|---|---|---|---|---|---|
| With Near-Duplicate | 25 | 25 | 0 | 25 | 0 | 100.0% |
| Without Near-Duplicate | 110 | 110 | 0 | 108 | 2 | 100.0% |

- Gate-pass rate difference (with - without): +0.0%
