# Cluster Homogeneity Analysis

## Set: train
- Examples: 2507
- Distinct keys: 230
- Keys with >1 example: 73
- Differing finding_id: 24 keys (880 examples)
- Differing route: 0 keys (0 examples)
- Differing reference: 1 keys (80 examples)
- Differing rule_id: 0 keys (0 examples)
- Differing other record fields: 0 keys (0 examples)

## Set: val
- Examples: 361
- Distinct keys: 70
- Keys with >1 example: 51
- Differing finding_id: 16 keys (140 examples)
- Differing route: 0 keys (0 examples)
- Differing reference: 1 keys (20 examples)
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
- Differing reference: 1 keys (40 examples)
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
- A_val keys affected by field other than finding_id: 1
- A_val examples affected by field other than finding_id: 20

## Reference Comparison and P3d Reconciliation
- Comparing targets with harvest_checks.reference_key (ignoring finding_id and resource_ref):
  - The earlier claim of '17 keys / 160 examples differing in A_val' was an artifact of comparing raw JSON targets including finding_id.
  - When evaluated via reference_key, only 1 key (20 examples) in A_val has differing reference ops (cis.s3_default_encryption, which admits two valid minimal variants: with and without encryption_algorithm KMS).
  - In dataset/train.jsonl, only 1 key differs via reference_key.

## Consequence for Label Pipeline
Clusters (input_keys) are homogeneous with respect to record rule_id, route, and resource fields. When ignoring finding_id, targets are essentially homogeneous (only 1 key has multi-op reference variants). Candidate labels must be evaluated against the finding_id of the input record itself, and downstream M2 scoring must be evaluated at the cluster (input_key) level to respect statistical independence.