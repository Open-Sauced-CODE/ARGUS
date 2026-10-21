# ARGUS Phase 5 - dataset card

Built by `python -m ml.mutation_engine.build_dataset --seed 1337` at commit `b803463`. Do not edit by hand.

## What it is
Synthetic (broken resource, reference Patch-IR fix) pairs made by the mutation engine from clean base resources taken from real
public Terraform (TerraDS) plus documented synthetic bases. The model input is exactly what the Phase 4 airlock returns for one
(resource, rule) pair; the target is the Patch-IR fix. No paid API was used anywhere.

## Splits
| split | examples | distinct inputs | ambiguous inputs | source bucket |
|---|---:|---:|---:|---|
| train | 2507 | 230 | 1 | train |
| val | 361 | 70 | 1 | val |
| B1 | 261 | 36 | 1 | test |
| B2 | 180 | 10 | 1 | test |

Distinct inputs are far fewer than examples (decision D10): the airlock shows the model only the fields of one rule, so many
examples are identical to the model. Report both numbers in the paper. An ambiguous input is one input with more than one
reference patch (for example the CIS encryption rule cannot show whether the algorithm was cleared).

## Examples per mutator
| mutator | train | val | B1 | B2 |
|---|---:|---:|---:|---:|
| m_s3_sse_off | 160 | 40 | 40 | 80 |
| m_s3_sse_algo | 120 | 30 | 27 | 60 |
| m_rds_unencrypted | 80 | 20 | 20 | 40 |
| m_s3_versioning_off | 80 | 0 | 20 | 0 |
| m_s3_lifecycle_off | 80 | 0 | 20 | 0 |
| m_s3_public_block_off | 480 | 106 | 54 | 0 |
| m_sg_world_open | 996 | 106 | 0 | 0 |
| m_iam_full_admin | 151 | 15 | 0 | 0 |
| m_account_mfa_off | 80 | 8 | 20 | 0 |
| m_s3_logging_off | 80 | 20 | 20 | 0 |
| m_account_detection_off | 100 | 8 | 20 | 0 |
| m_region_outside_approved | 100 | 8 | 20 | 0 |

## Routes (fix versus escalate)
- train: {'fix': 2147, 'escalate': 360}
- val: {'fix': 317, 'escalate': 44}
- B1: {'fix': 181, 'escalate': 80}
- B2: {'fix': 140, 'escalate': 40}

## Overlap of inputs with train (not a leak by the full-hash rule, see D10)
- val: 346 of 361 examples have an input that also appears in train
- B1: 261 of 261 examples have an input that also appears in train
- B2: 180 of 180 examples have an input that also appears in train

## Shortfalls against the quota (not errors; the data ran out)
- train / m_account_mfa_off: got 80 of 100 examples
- train / m_rds_unencrypted: got 80 of 368 examples
- train / m_s3_lifecycle_off: got 80 of 100 examples
- train / m_s3_logging_off: got 80 of 774 examples
- train / m_s3_public_block_off: got 480 of 978 examples
- train / m_s3_sse_algo: got 120 of 682 examples
- train / m_s3_sse_off: got 160 of 964 examples
- train / m_s3_versioning_off: got 80 of 100 examples
- train / m_sg_world_open: got 996 of 1051 examples
- val / m_rds_unencrypted: got 20 of 37 examples
- val / m_s3_lifecycle_off: no applicable base in the val bucket
- val / m_s3_logging_off: got 20 of 78 examples
- val / m_s3_sse_algo: got 30 of 68 examples
- val / m_s3_sse_off: got 40 of 97 examples
- val / m_s3_versioning_off: no applicable base in the val bucket
- B1 / m_account_detection_off+m_account_mfa_off: got 40 of 80 examples
- B1 / m_rds_unencrypted+m_region_outside_approved: got 40 of 80 examples
- B1 / m_s3_lifecycle_off+m_s3_logging_off: got 40 of 80 examples
- B1 / m_s3_sse_off+m_s3_versioning_off: got 60 of 80 examples
- B2 / m_rds_unencrypted: got 40 of 46 examples
- B2 / m_s3_sse_algo: got 60 of 85 examples
- B2 / m_s3_sse_off: got 80 of 120 examples

## Held-out design
- Held-out mutator pairs (never in train or validation): m_s3_sse_off+m_s3_versioning_off; m_s3_sse_algo+m_s3_public_block_off; m_s3_lifecycle_off+m_s3_logging_off; m_account_detection_off+m_account_mfa_off; m_rds_unencrypted+m_region_outside_approved
- B2 family: encryption-at-rest (rules cis.s3_default_encryption, dpdp.rule6a, dpdp.rule6a_rds). `train_ablation_no_encryption.jsonl` has no resource that used a family mutator.
- Honest note on B1 (decision D17): the airlock shows only one rule's fields, so a combination of mutators is invisible to the
  model. B1 therefore measures generalisation to unseen repositories and decoys, plus resource-level success (all findings of
  one resource fixed), not 'unseen combinations' in the model's own view.
- Validation has no bases for the personal-data S3 rules (versioning, lifecycle) because no validation-bucket repository gave a
  clean personal-data bucket; those rules are T0-covered and are checked by the T0 tests instead.

## Known limitations
- Synthetic completed S3 bases are only as diverse as the real extras they inherit (decision D9).
- Operations add_policy_statement, remove_policy_statement and enable_feature are unused (decision D13).
- Security-group fixes use the placeholder INTERNAL_CIDR, resolved by the Phase 7 compiler (decision D12).
- Escalate share is about 14.4% of train because every mutator gets a minimum number of examples.

## Source repositories by licence (Tier A bases, from bases/manifest.csv)
- MIT: 7084 bases
- Apache-2.0: 3524 bases
- GPL-3.0: 1164 bases
- MPL-2.0: 451 bases
- MIT-0: 305 bases
- BSD-3-Clause: 173 bases
- Unlicense: 95 bases
- GPL-2.0: 76 bases
- AGPL-3.0: 75 bases
- CC0-1.0: 73 bases
- BSD-2-Clause: 42 bases
- CC-BY-SA-4.0: 28 bases
- ISC: 27 bases
- CC-BY-4.0: 17 bases
- LGPL-3.0: 6 bases
- WTFPL: 5 bases
- EPL-2.0: 3 bases
- EUPL-1.2: 3 bases
- 0BSD: 1 bases
- BSD-4-Clause: 1 bases
- EPL-1.0: 1 bases
- LGPL-2.1: 1 bases

## Intended use
Training and evaluating the M1 remediation model of ARGUS. Not for any other purpose.
