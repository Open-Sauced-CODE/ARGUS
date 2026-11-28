# Near-Duplicate Check: Clean OOF Clusters vs Fold Training Sets

- Folds analyzed: [0, 1, 3]
- Clean OOF clusters analyzed: **105**
- Identical normalized signature in training: **22** (21.0%)
- Near-duplicates (identical normalized sig OR Jaccard >= 0.80): **22** (21.0%)
- Remaining clean clusters after removing near-duplicates: **83**

> **WARNING:** OOF clusters are not independent of training; clean counts overstate unseen clusters
> Remaining independent clean clusters after removal: **83** / 105

## Per-Fold Breakdown (Counts Only)

| Fold | Clean Clusters | Identical Norm Sig | Near-Dups (Exact or >= thr) | Near-Dup Rate | Remaining |
|---|---|---|---|---|---|
| 0 | 37 | 9 | 9 | 24.3% | 28 |
| 1 | 35 | 8 | 8 | 22.9% | 27 |
| 3 | 33 | 5 | 5 | 15.2% | 28 |

## Max Jaccard Similarity Distribution (Token Shingles, Same Rule)

| Similarity Bin | Cluster Count |
|---|---|
| [0.0, 0.2) | 6 |
| [0.2, 0.4) | 40 |
| [0.4, 0.6) | 34 |
| [0.6, 0.8) | 3 |
| [0.8, 1.0) | 0 |
| 1.0 | 22 |

## OOF Gate Pass Rate Comparison (Counts Only)

| Subset | Clusters | Gate-Pass | Gate-Fail | Minimal Correct | Wrong (k) | Gate-Pass Rate |
|---|---|---|---|---|---|---|
| With Near-Duplicate | 22 | 22 | 0 | 22 | 0 | 100.0% |
| Without Near-Duplicate | 83 | 83 | 0 | 81 | 2 | 100.0% |

- Gate-pass rate difference (with - without): +0.0%

## Existing Clean Clusters vs All Training Folds (Counts Only)

- Existing pre-OOF clean clusters checked: **15**
- Exact normalized signature matches in training: **0**
- Near-duplicates in any training fold: **0** (NO)
- Remaining independent existing clusters: **15**

## Clopper-Pearson Certification Comparison (alpha=0.05, delta=0.05)

| Version | OOF Clean | Existing | Total n | k | cp_min_n | Margin | Verdict |
|---|---|---|---|---|---|---|---|
| (a) All clean clusters | 105 | 15 | 120 | 2 | 124 | -4 | NEED 4 MORE CLEAN CLUSTERS |
| (b) After removing near-duplicates | 83 | 15 | 98 | 2 | 124 | -26 | NEED 26 MORE CLEAN CLUSTERS |

> The certificate depends on accepted drafts at tau, so the effective n is smaller; do not estimate it.
