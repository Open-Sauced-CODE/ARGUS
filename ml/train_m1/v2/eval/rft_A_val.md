## rft on A_val

| Metric | Value |
|---|---|
| examples scored | 361 (without candidates: 0) |
| pass@1 (greedy) | 79.5% (287/361) |
| pass@8 | 80.6% |
| mean distinct canonical answers of 8 | 1.00 |
| unsafe candidates | 0 |
| escalate precision / recall | 0.0% / n/a (tp 0, fn 0, fp 44) |
| schema-valid rate | 100.0% |

| Rule | n | pass@1 | pass@8 | mean distinct | ESC route |
|---|---|---|---|---|---|
| cis.iam_no_full_admin | 15 | 100.0% | 100.0% | 1.00 | no |
| cis.s3_default_encryption | 20 | 100.0% | 100.0% | 1.00 | no |
| cis.s3_public_access_block | 53 | 84.9% | 84.9% | 1.00 | no |
| cis.sg_open_ingress | 53 | 100.0% | 100.0% | 1.00 | no |
| dpdp.rule15_region | 8 | 100.0% | 100.0% | 1.00 | no |
| dpdp.rule6_account_mfa | 8 | 100.0% | 100.0% | 1.00 | no |
| dpdp.rule6_logging | 20 | 0.0% | 0.0% | 1.00 | no |
| dpdp.rule6_public_exposure | 53 | 50.9% | 50.9% | 1.00 | no |
| dpdp.rule6_sg_open_ingress | 53 | 100.0% | 100.0% | 1.00 | no |
| dpdp.rule6a | 50 | 60.0% | 68.0% | 1.00 | no |
| dpdp.rule6a_rds | 20 | 100.0% | 100.0% | 1.00 | no |
| dpdp.rule7_detection | 8 | 100.0% | 100.0% | 1.00 | no |
