## rft_v2_step18 on A_val

| Metric | Value |
|---|---|
| examples scored | 361 (without candidates: 0) |
| pass@1 (greedy) | 0.0% (0/361) |
| pass@8 | 0.0% |
| mean distinct canonical answers of 8 | 1.00 |
| unsafe candidates | 0 |
| escalate precision / recall | n/a / n/a (tp 0, fn 0, fp 0) |
| schema-valid rate | 0.0% |

| Rule | n | pass@1 | pass@8 | mean distinct | ESC route |
|---|---|---|---|---|---|
| cis.iam_no_full_admin | 15 | 0.0% | 0.0% | 1.00 | no |
| cis.s3_default_encryption | 20 | 0.0% | 0.0% | 1.00 | no |
| cis.s3_public_access_block | 53 | 0.0% | 0.0% | 1.00 | no |
| cis.sg_open_ingress | 53 | 0.0% | 0.0% | 1.00 | no |
| dpdp.rule15_region | 8 | 0.0% | 0.0% | 1.00 | no |
| dpdp.rule6_account_mfa | 8 | 0.0% | 0.0% | 1.00 | no |
| dpdp.rule6_logging | 20 | 0.0% | 0.0% | 1.00 | no |
| dpdp.rule6_public_exposure | 53 | 0.0% | 0.0% | 1.00 | no |
| dpdp.rule6_sg_open_ingress | 53 | 0.0% | 0.0% | 1.00 | no |
| dpdp.rule6a | 50 | 0.0% | 0.0% | 1.00 | no |
| dpdp.rule6a_rds | 20 | 0.0% | 0.0% | 1.00 | no |
| dpdp.rule7_detection | 8 | 0.0% | 0.0% | 1.00 | no |
