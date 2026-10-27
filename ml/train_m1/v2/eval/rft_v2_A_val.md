## rft_v2 on A_val

| Metric | Value |
|---|---|
| examples scored | 361 (without candidates: 0) |
| pass@1 (greedy) | 12.2% (44/361) |
| pass@8 | 51.2% |
| mean distinct canonical answers of 8 | 6.39 |
| unsafe candidates | 935 |
| escalate precision / recall | n/a / n/a (tp 0, fn 0, fp 0) |
| schema-valid rate | 100.0% |

| Rule | n | pass@1 | pass@8 | mean distinct | ESC route |
|---|---|---|---|---|---|
| cis.iam_no_full_admin | 15 | 0.0% | 60.0% | 7.93 | no |
| cis.s3_default_encryption | 20 | 100.0% | 100.0% | 7.00 | no |
| cis.s3_public_access_block | 53 | 0.0% | 15.1% | 4.91 | no |
| cis.sg_open_ingress | 53 | 0.0% | 100.0% | 7.17 | no |
| dpdp.rule15_region | 8 | 0.0% | 0.0% | 5.00 | no |
| dpdp.rule6_account_mfa | 8 | 0.0% | 100.0% | 8.00 | no |
| dpdp.rule6_logging | 20 | 0.0% | 0.0% | 7.00 | no |
| dpdp.rule6_public_exposure | 53 | 0.0% | 0.0% | 5.15 | no |
| dpdp.rule6_sg_open_ingress | 53 | 0.0% | 100.0% | 7.09 | no |
| dpdp.rule6a | 50 | 48.0% | 68.0% | 6.00 | no |
| dpdp.rule6a_rds | 20 | 0.0% | 0.0% | 7.50 | no |
| dpdp.rule7_detection | 8 | 0.0% | 0.0% | 7.88 | no |
