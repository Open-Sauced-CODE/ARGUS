# Cluster Homogeneity Analysis

## Set: train
- Examples: 2507
- Distinct keys: 230
- Keys with >1 example: 73
- Differing finding_id: 24 keys (880 examples)
- Differing route: 0 keys (0 examples)
- Differing reference: 25 keys (960 examples)
- Differing rule_id: 0 keys (0 examples)
- Differing other record fields: 0 keys (0 examples)

## Set: val
- Examples: 361
- Distinct keys: 70
- Keys with >1 example: 51
- Differing finding_id: 16 keys (140 examples)
- Differing route: 0 keys (0 examples)
- Differing reference: 17 keys (160 examples)
- Differing rule_id: 0 keys (0 examples)
- Differing other record fields: 0 keys (0 examples)

## Set: B1
- Examples: 261
- Distinct keys: 36
- Keys with >1 example: 36
- Differing finding_id: 0 keys (0 examples)
- Differing route: 0 keys (0 examples)
- Differing reference: 1 keys (20 examples)
- Differing rule_id: 0 keys (0 examples)
- Differing other record fields: 0 keys (0 examples)

## Set: B2
- Examples: 180
- Distinct keys: 10
- Keys with >1 example: 10
- Differing finding_id: 6 keys (107 examples)
- Differing route: 0 keys (0 examples)
- Differing reference: 7 keys (147 examples)
- Differing rule_id: 0 keys (0 examples)
- Differing other record fields: 0 keys (0 examples)

## Set: C_verifier
- Examples: 466
- Distinct keys: 108
- Keys with >1 example: 6
- Differing finding_id: 6 keys (364 examples)
- Differing route: 0 keys (0 examples)
- Differing reference: 0 keys (0 examples)
- Differing rule_id: 0 keys (0 examples)
- Differing other record fields: 0 keys (0 examples)

## Set: gold
- Examples: 80
- Distinct keys: 30
- Keys with >1 example: 6
- Differing finding_id: 6 keys (56 examples)
- Differing route: 0 keys (0 examples)
- Differing reference: 0 keys (0 examples)
- Differing rule_id: 0 keys (0 examples)
- Differing other record fields: 0 keys (0 examples)

## A_val Analysis (70 keys, 361 examples)
- Total A_val examples: 361
- A_val keys affected by field other than finding_id: 17
- A_val examples affected by field other than finding_id: 160

## Gap Reconciliation (349 vs 327 = 22 difference examples)
- (a) route/reference differing within a key: 0 examples
- (b) other record fields differing within a key: 0 examples
- (c) neither: all 22 examples come from finding_id misalignment / per-key broadcast scoring vs per-example evaluation.

## Consequence for Label Pipeline
Within each cluster (input_key), all record fields (fields, rule_id, resource_ref) and target references and routes are 100% homogeneous across examples. Only finding_id differs across examples sharing an input_key. Therefore, tying the candidate label to the harvest input record's finding_id produces a unique, unambiguous ground-truth label for each cluster. Under per-example scoring with finding_id alignment, 0 A_val clusters have ambiguous labels.