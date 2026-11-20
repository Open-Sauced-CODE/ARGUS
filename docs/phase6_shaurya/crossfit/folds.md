# Cross-fit folds (counts only, no content)

Seed: 1337  K: 5  Total train inputs: 230

## Per-fold summary

| Fold | Total | Heldout overlap | In A_val |
|---|---|---|---|
| 0 | 55 | 17 | 16 |
| 1 | 50 | 15 | 13 |
| 2 | 43 | 12 | 11 |
| 3 | 41 | 6 | 7 |
| 4 | 41 | 6 | 8 |

## Rule-id distribution across all folds

| rule_id | total | fold 0 | fold 1 | fold 2 | fold 3 | fold 4 |
|---|---|---|---|---|---|---|
| cis.iam_no_full_admin | 142 | 29 | 29 | 28 | 28 | 28 |
| cis.s3_default_encryption | 1 | 1 | 0 | 0 | 0 | 0 |
| cis.s3_public_access_block | 6 | 2 | 1 | 1 | 1 | 1 |
| cis.sg_open_ingress | 26 | 6 | 5 | 5 | 5 | 5 |
| dpdp.rule15_region | 3 | 1 | 1 | 1 | 0 | 0 |
| dpdp.rule6_account_mfa | 2 | 1 | 1 | 0 | 0 | 0 |
| dpdp.rule6_logging | 2 | 1 | 1 | 0 | 0 | 0 |
| dpdp.rule6_public_exposure | 6 | 2 | 1 | 1 | 1 | 1 |
| dpdp.rule6_sg_open_ingress | 26 | 6 | 5 | 5 | 5 | 5 |
| dpdp.rule6_versioning | 2 | 1 | 1 | 0 | 0 | 0 |
| dpdp.rule6a | 7 | 2 | 2 | 1 | 1 | 1 |
| dpdp.rule6a_rds | 2 | 1 | 1 | 0 | 0 | 0 |
| dpdp.rule7_detection | 3 | 1 | 1 | 1 | 0 | 0 |
| dpdp.rule8_lifecycle | 2 | 1 | 1 | 0 | 0 | 0 |

## Heldout-overlap rule

OOF drafts for inputs in the heldout_overlap list are labelled `heldout_overlap=true`.
They are NEVER used to train or calibrate M2; they are test-side only.

## OOF drafts that count toward SFT certificate

Only OOF drafts where `heldout_overlap=false` AND the input is NOT in A_val
contribute to the unseen-clean cluster count for the SFT gate-only certificate.
Per S4: 44 more clean unseen clusters needed beyond the current 15.
