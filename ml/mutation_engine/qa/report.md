# QA report (Phase 5, Step 8)

Examples checked: 3309

| check | what | failures |
|---|---|---:|
| 1 | target rule fires on the mutated resource | 0 |
| 2 | original resource is clean under all rules | 0 |
| 3 | reference fix restores exactly what was broken | 0 |
| 4 | reference patch clears the stub gate | 0 |
| 5 | reference patch is schema-valid | 0 |
| 6 | decoys untouched, diff equals declared paths | 0 |
| 7 | input identical to a fresh airlock run | 0 |
| 8 | no full-resource hash shared inside or between splits | 0 |

RESULT: ALL CHECKS PASSED

## Split train
- examples: 2507, distinct inputs: 230, ambiguous inputs: 1
- routes: {'fix': 2147, 'escalate': 360}
- ops per patch: {1: 2213, 2: 134, 4: 160}
- violations per resource: {1: 780, 2: 1500, 3: 138, 4: 64, 5: 25}
- approx tokens (chars/3) p50 / p99 / max: [132, 264, 518]

| rule | examples | distinct inputs |
|---|---:|---:|
| cis.iam_no_full_admin | 151 | 142 |
| cis.s3_default_encryption | 80 | 1 |
| cis.s3_public_access_block | 240 | 6 |
| cis.sg_open_ingress | 498 | 26 |
| dpdp.rule15_region | 100 | 3 |
| dpdp.rule6_account_mfa | 80 | 2 |
| dpdp.rule6_logging | 80 | 2 |
| dpdp.rule6_public_exposure | 240 | 6 |
| dpdp.rule6_sg_open_ingress | 498 | 26 |
| dpdp.rule6_versioning | 80 | 2 |
| dpdp.rule6a | 200 | 7 |
| dpdp.rule6a_rds | 80 | 2 |
| dpdp.rule7_detection | 100 | 3 |
| dpdp.rule8_lifecycle | 80 | 2 |

## Split val
- examples: 361, distinct inputs: 70, ambiguous inputs: 1
- routes: {'fix': 317, 'escalate': 44}
- ops per patch: {1: 305, 2: 22, 4: 34}
- violations per resource: {1: 96, 2: 194, 3: 15, 4: 56}
- approx tokens (chars/3) p50 / p99 / max: [132, 275, 408]

| rule | examples | distinct inputs |
|---|---:|---:|
| cis.iam_no_full_admin | 15 | 15 |
| cis.s3_default_encryption | 20 | 1 |
| cis.s3_public_access_block | 53 | 6 |
| cis.sg_open_ingress | 53 | 12 |
| dpdp.rule15_region | 8 | 3 |
| dpdp.rule6_account_mfa | 8 | 2 |
| dpdp.rule6_logging | 20 | 2 |
| dpdp.rule6_public_exposure | 53 | 6 |
| dpdp.rule6_sg_open_ingress | 53 | 12 |
| dpdp.rule6a | 50 | 6 |
| dpdp.rule6a_rds | 20 | 2 |
| dpdp.rule7_detection | 8 | 3 |

## Split B1
- examples: 261, distinct inputs: 36, ambiguous inputs: 1
- routes: {'fix': 181, 'escalate': 80}
- ops per patch: {1: 219, 2: 20, 4: 22}
- violations per resource: {2: 120, 3: 141}
- approx tokens (chars/3) p50 / p99 / max: [124, 201, 201]

| rule | examples | distinct inputs |
|---|---:|---:|
| cis.s3_default_encryption | 20 | 1 |
| cis.s3_public_access_block | 27 | 6 |
| dpdp.rule15_region | 20 | 3 |
| dpdp.rule6_account_mfa | 20 | 2 |
| dpdp.rule6_logging | 20 | 2 |
| dpdp.rule6_public_exposure | 27 | 6 |
| dpdp.rule6_versioning | 20 | 2 |
| dpdp.rule6a | 47 | 7 |
| dpdp.rule6a_rds | 20 | 2 |
| dpdp.rule7_detection | 20 | 3 |
| dpdp.rule8_lifecycle | 20 | 2 |

## Split B2
- examples: 180, distinct inputs: 10, ambiguous inputs: 1
- routes: {'fix': 140, 'escalate': 40}
- ops per patch: {1: 140, 2: 40}
- violations per resource: {1: 84, 2: 89, 3: 5, 4: 2}
- approx tokens (chars/3) p50 / p99 / max: [117, 133, 133]

| rule | examples | distinct inputs |
|---|---:|---:|
| cis.s3_default_encryption | 40 | 1 |
| dpdp.rule6a | 100 | 7 |
| dpdp.rule6a_rds | 40 | 2 |

