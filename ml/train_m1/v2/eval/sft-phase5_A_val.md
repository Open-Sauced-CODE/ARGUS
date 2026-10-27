## sft-phase5 on A_val

| Metric | Value |
|---|---|
| examples scored | 361 (without candidates: 0) |
| pass@1 (greedy) | 96.7% (349/361) |
| pass@8 | 99.4% |
| mean distinct canonical answers of 8 | 1.22 |
| unsafe candidates | 9 |
| escalate precision / recall | 0.0% / n/a (tp 0, fn 0, fp 32) |
| schema-valid rate | 99.5% |

| Rule | n | pass@1 | pass@8 | mean distinct | ESC route |
|---|---|---|---|---|---|
| cis.iam_no_full_admin | 15 | 100.0% | 100.0% | 1.00 | no |
| cis.s3_default_encryption | 20 | 100.0% | 100.0% | 2.00 | no |
| cis.s3_public_access_block | 53 | 100.0% | 100.0% | 1.00 | no |
| cis.sg_open_ingress | 53 | 100.0% | 100.0% | 1.40 | no |
| dpdp.rule15_region | 8 | 100.0% | 100.0% | 1.00 | no |
| dpdp.rule6_account_mfa | 8 | 75.0% | 75.0% | 1.00 | no |
| dpdp.rule6_logging | 20 | 100.0% | 100.0% | 1.00 | no |
| dpdp.rule6_public_exposure | 53 | 100.0% | 100.0% | 1.17 | no |
| dpdp.rule6_sg_open_ingress | 53 | 100.0% | 100.0% | 1.00 | no |
| dpdp.rule6a | 50 | 100.0% | 100.0% | 1.20 | no |
| dpdp.rule6a_rds | 20 | 50.0% | 100.0% | 2.00 | no |
| dpdp.rule7_detection | 8 | 100.0% | 100.0% | 1.00 | no |
