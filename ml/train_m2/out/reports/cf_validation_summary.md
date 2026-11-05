# Counterfactual Validation Summary (F8 fix)

- Total examples with references: 2868
- Agreed: 2868
- Disagreed: 0
- Overall agreement rate: 1.0000
- Wall time: 731.7s

## Per-rule agreement

| rule_id | n | agree | disagree | rate |
| --- | --- | --- | --- | --- |
| cis.iam_no_full_admin | 166 | 166 | 0 | 1.000 |
| cis.s3_default_encryption | 100 | 100 | 0 | 1.000 |
| cis.s3_public_access_block | 293 | 293 | 0 | 1.000 |
| cis.sg_open_ingress | 551 | 551 | 0 | 1.000 |
| dpdp.rule15_region | 108 | 108 | 0 | 1.000 |
| dpdp.rule6_account_mfa | 88 | 88 | 0 | 1.000 |
| dpdp.rule6_logging | 100 | 100 | 0 | 1.000 |
| dpdp.rule6_public_exposure | 293 | 293 | 0 | 1.000 |
| dpdp.rule6_sg_open_ingress | 551 | 551 | 0 | 1.000 |
| dpdp.rule6_versioning | 80 | 80 | 0 | 1.000 |
| dpdp.rule6a | 250 | 250 | 0 | 1.000 |
| dpdp.rule6a_rds | 100 | 100 | 0 | 1.000 |
| dpdp.rule7_detection | 108 | 108 | 0 | 1.000 |
| dpdp.rule8_lifecycle | 80 | 80 | 0 | 1.000 |

## Root causes for known disagreements

### dpdp.rule6_public_exposure (0 disagreements)
The CF oracle's BFS domain for 'public_access_block' fields covers only True/False. public_exposure rules may fire on combinations of ACL + bucket-policy + public-block flags. When the reference disables public access via a multi-field change the CF oracle may find a 1-edit solution that differs from the reference route, producing a label mismatch. Conclusion: CF oracle under-enumerates the domain for compound public-access rules.

### cis.s3_public_access_block (0 disagreements)
s3_public_access_block fires when block_public_acls or block_public_policy is False. The reference sets all four block_* fields to True. The CF oracle's BFS (max_edits=3) finds a 1-edit fix (set any one field to True), classifying the candidate as 'valid_not_minimal' when the reference sets all four. This is a known CF oracle limitation: it cannot distinguish 'required' multi-field writes from 'sufficient' single-field writes without explicit rule semantics. Conclusion: reference is correct; CF oracle is permissive for this rule.
