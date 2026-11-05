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

## Gap Reconciliation and P3c Findings
- In Phase 5 evaluation, broadcast scoring (scoring only the first example per key and weighting by example count) yielded 349/361.
- Under strict per-example evaluation with finding_id aligned to each example:
  - Phase 5 candidate text yields 317/361 passes (74 differing examples).
  - Cause breakdown among differing examples: 41 'neither' (intrinsic finding_id sensitivity), 33 'reference' (differing references across examples sharing a key).
  - 17 keys in A_val (160 examples) have differing target references across examples sharing an input_key.

## Consequence for Label Pipeline
Clusters (input_keys) are homogeneous with respect to record rule_id and resource fields, but NOT 100% homogeneous with respect to target references (17 keys / 160 examples differ in A_val). Candidate labels must be evaluated against the finding_id of the input record itself, and downstream M2 scoring must be evaluated at the cluster (input_key) level to respect statistical independence.