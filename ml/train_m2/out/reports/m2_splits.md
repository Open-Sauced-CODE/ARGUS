# M2 splits (sha256 6b6b7bf7daa03565)

| family | train | val | cal | test |
|---|---|---|---|---|
| cis.iam_no_full_admin | 85 | 28* | 44* | 2* |
| cis.s3_default_encryption | 0* | 0* | 0* | 1* |
| cis.s3_public_access_block | 0* | 0* | 0* | 7* |
| cis.sg_open_ingress | 10* | 3* | 3* | 46* |
| dpdp.rule15_region | 0* | 0* | 0* | 3* |
| dpdp.rule6_account_mfa | 0* | 0* | 0* | 2* |
| dpdp.rule6_logging | 0* | 0* | 0* | 2* |
| dpdp.rule6_public_exposure | 0* | 0* | 0* | 7* |
| dpdp.rule6_sg_open_ingress | 10* | 3* | 3* | 46* |
| dpdp.rule6_versioning | 0* | 0* | 0* | 2* |
| dpdp.rule6a | 0* | 0* | 0* | 7* |
| dpdp.rule6a_rds | 0* | 0* | 0* | 2* |
| dpdp.rule7_detection | 0* | 0* | 0* | 3* |
| dpdp.rule8_lifecycle | 0* | 0* | 0* | 2* |

(* = fewer than 59 clusters: the rule of 59 cannot be met in that cell)
