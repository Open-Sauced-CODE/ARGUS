# Precision of our rules on real code (hand-labelled sample)

| rule | true violations | precision |
|---|---:|---|
| cis.iam_no_full_admin | 2/2 | 2/2 = 100.0% [34.2, 100.0] |
| cis.s3_default_encryption | 10/10 | 10/10 = 100.0% [72.2, 100.0] |
| cis.s3_public_access_block | 10/10 | 10/10 = 100.0% [72.2, 100.0] |
| cis.sg_open_ingress | 9/10 | 9/10 = 90.0% [59.6, 98.2] |
| dpdp.rule6_logging | 10/10 | 10/10 = 100.0% [72.2, 100.0] |
| dpdp.rule6_public_exposure | 10/10 | 10/10 = 100.0% [72.2, 100.0] |
| dpdp.rule6_sg_open_ingress | 9/10 | 9/10 = 90.0% [59.6, 98.2] |
| dpdp.rule6a | 9/9 | 9/9 = 100.0% [70.1, 100.0] |
| dpdp.rule6a_rds | 9/9 | 9/9 = 100.0% [70.1, 100.0] |

Overall: 78/80 = 97.5% [91.3, 99.3]
Rows still unlabelled: 0
