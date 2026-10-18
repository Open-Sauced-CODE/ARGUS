# ARGUS Phase 5 - Contracts (frozen)

Phase 4 commit: `6d01d0d`
Frozen on: 2026-10-07
Owner: Role C (ML track)

Everything in sections 1 to 5 is frozen. To change any of it: message the whole team first, then add a row
to the change log in section 7. `python -m pytest ml/tests/test_contracts_doc.py` fails if this file drifts
away from the real Rego rules, the Patch-IR schema or the Phase 4 function signatures.

## 1. Interfaces Phase 5 builds on (owned by Phase 4, do not change)

| Name | Exact signature | File |
|---|---|---|
| project | `project(raw_finding, rule_id, policy_dir=None)` | `privacy/airlock/projection.py` |
| run_airlock | `run_airlock(raw_finding, rule_id, *, vault=None, policy_dir=None)` | `privacy/airlock/airlock.py` |
| leak_check | `leak_check(payload, vault_values=())` | `privacy/airlock/leakcheck.py` |
| scrub | `scrub(record, engine='auto')` | `privacy/scrubbers/scrubbers.py` |
| tokenize | `tokenize(record, vault=None)` | `privacy/vault/tokenizer.py` |
| rehydrate | `rehydrate(obj, vault_refs, vault=None)` | `privacy/vault/tokenizer.py` |

Patch-IR schema file: `remediate/patch_ir/schema.json`
Patch-IR schema fingerprint (canonical SHA-256): `4550b8f68640019523e232a9e38cb4f1c13d6205a75c62d00ad60a0521b8761a`
Patch-IR operations (closed vocabulary, 7): set_attr, add_policy_statement, remove_policy_statement, restrict_cidr, enable_feature, set_lifecycle_rule, escalate.
Patch-IR resource_ref pattern: `^[A-Z_]+_[0-9]+$` (airlock tokens such as BUCKET_1, SG_1, RESOURCE_1).

Rule source of truth: the `.rego` files under `policy/` (14 rules; run `python -m ml.tools.list_rules` to print them).

There is NO verification-gate code in the repository yet (the full gate is built in Phase 7). Phase 5 therefore
builds a stub gate for its own QA and reward-hacking audit (see decision D3).

## 2. Interfaces Phase 5 creates

| Name | Status | Where / when |
|---|---|---|
| gate stub: `gate(mutated, patch_ir)` returning passed plus per-check results (a) to (d) | planned | `ml/mutation_engine/qa/gate_stub.py`, Section 2 (Steps 5-8) |
| T0 `match(finding)` returns Patch-IR or None | planned, signature frozen at Step 22 | `remediate/templates/` |
| M1 `generate(tokenized_finding)` returns a list of Patch-IR candidates | planned, signature frozen at Step 22 | `remediate/local_model/` |
| `generate_with_stats(...)` returns candidates plus log-probability statistics and agreement rate | planned, for Phase 6 | `remediate/local_model/` |

## 3. Shapes

What the model sees is exactly what `run_airlock` returns for ONE (resource, rule) pair. Shape only; the exact bytes come from the airlock:

    {"finding_id": "F-0001", "rule_id": "dpdp.rule6_versioning", "resource_id": "BUCKET_1",
     "fields": {"resource_type": "AWSS3Bucket", "personal_data": true, "versioning_status": "Suspended"},
     "resource_ref": "BUCKET_1"}

What the model must answer (reference Patch-IR for that finding):

    {"finding_id": "F-0001", "resource_ref": "BUCKET_1",
     "ops": [{"op": "set_attr", "attr": "versioning_status", "value": "Enabled"}],
     "rationale_ref": "dpdp.rule6_versioning"}

Naming rules:

- Patch-IR `attr` is always a finding field name, i.e. a name the Rego rules read (`versioning_status`, `default_encryption`, `logging_enabled` ...). It is never a Terraform attribute name.
- Mutator ID format: `m_<what>_<violation>` (lowercase, digits, underscores). Variants of one mutator are written `<mutator_id>__<variant>`.
- Example ID format: `ex-000123`. Tiers: A (train, validation), B1, B2, C-verifier, C-mined, gold.

## 4. Rules, families, routing and mutators

Route meaning: **T0** = a deterministic template fixes it (single-attribute change); the example is still used to train M1. **M1** = no template, the model has to draft the patch. **ESC** = the correct answer is the `escalate` operation (the fix is outside the vocabulary); no template, M1 must learn to escalate.

| Rule ID | Library | Family | Resource type | Route | Mutator ID(s) | Notes |
|---|---|---|---|---|---|---|
| `dpdp.rule6a` | DPDP | encryption-at-rest | AWSS3Bucket | T0 | `m_s3_sse_off`, `m_s3_sse_algo` | set default_encryption true and encryption_algorithm aws:kms; only the algorithm if encryption is already on |
| `cis.s3_default_encryption` | CIS | encryption-at-rest | AWSS3Bucket | T0 | `m_s3_sse_off` | same mutation as dpdp.rule6a: both rules fire together |
| `dpdp.rule6a_rds` | DPDP | encryption-at-rest | AWSRDSInstance | ESC | `m_rds_unencrypted` | an existing RDS instance cannot be encrypted in place (snapshot copy and restore) |
| `dpdp.rule6_versioning` | DPDP | versioning-and-retention | AWSS3Bucket | T0 | `m_s3_versioning_off` | set versioning_status Enabled; only fires when personal_data is true |
| `dpdp.rule8_lifecycle` | DPDP | versioning-and-retention | AWSS3Bucket | T0 | `m_s3_lifecycle_off` | set_lifecycle_rule with the deployer's retention number; only fires when personal_data is true |
| `dpdp.rule6_public_exposure` | DPDP | public-exposure | AWSS3Bucket | T0 | `m_s3_public_block_off` | set only the flags that are false |
| `cis.s3_public_access_block` | CIS | public-exposure | AWSS3Bucket | T0 | `m_s3_public_block_off` | same mutation as dpdp.rule6_public_exposure: both rules fire together |
| `dpdp.rule6_sg_open_ingress` | DPDP | network-exposure | AWSIpPermissionInbound | M1 | `m_sg_world_open` | restrict_cidr; the replacement-value convention is settled at Step 5 (decision D5) |
| `cis.sg_open_ingress` | CIS | network-exposure | AWSIpPermissionInbound | M1 | `m_sg_world_open` | same mutation as dpdp.rule6_sg_open_ingress: both rules fire together |
| `cis.iam_no_full_admin` | CIS | iam-and-access | AWSPolicyStatement | M1 | `m_iam_full_admin` | convention for the replacement scope is settled at Step 5 (decision D5) |
| `dpdp.rule6_account_mfa` | DPDP | iam-and-access | AWSAccount | ESC | `m_account_mfa_off` | enabling account MFA is a human action; no Terraform base exists, so bases are synthetic (D4) |
| `dpdp.rule6_logging` | DPDP | logging-and-detection | AWSS3Bucket | T0 | `m_s3_logging_off` | set_attr logging_enabled true; the log-target bucket comes from deployer configuration |
| `dpdp.rule7_detection` | DPDP | logging-and-detection | AWSAccount | ESC | `m_account_detection_off` | CloudTrail or GuardDuty would be new resources; no Terraform base, so bases are synthetic (D4) |
| `dpdp.rule15_region` | DPDP | data-residency | any resource with a region | ESC | `m_region_outside_approved` | warn-only visibility rule; moving data to another region is a migration |

Totals: 14 rules, 7 families, 12 mutators. T0 covers 7 rules, M1 drafts 3, 4 are escalate cases.

Phase 1 skeleton mutators keep working until Step 5 replaces them. Mapping of their old IDs: `s3_disable_encryption` becomes `m_s3_sse_off`, `s3_disable_versioning` becomes `m_s3_versioning_off`, `s3_disable_public_access_block` becomes `m_s3_public_block_off`, `sg_open_ingress` becomes `m_sg_world_open`.

Held-out family (Tier B2): **encryption-at-rest**

Why: it has the most rules (3) and 3 distinct mutators, and S3 and RDS bases are the most plentiful in public Terraform, so 200 or more examples are realistic. The ablation model trained for Tier B2 never sees any example of this family; the main model does. B2 results are reported for the whole family (not only the T0-uncovered part) because B2 tests generalisation, not routing.

## 5. Decisions made (Appendix C of the Phase 5 plan)

| Decision | Choice | Owner | Date |
|---|---|---|---|
| Held-out family for Tier B2 | encryption-at-rest (see section 4) | Role C | 2026-10-07 |
| Base model and size | start with Qwen3.5-4B; confirmed or changed at Step 15 using validation numbers only | Role C | 2026-10-07 |
| Can the finding record carry unresolved references | No for v1: a resource whose rule-read attribute is unresolved is skipped and counted; stated as a limitation (confirm with the Phase 4 owner) | Role C | 2026-10-07 |
| Second reviewer for the gold sample | Role D (owns the DPDP mapping, did not write the mutators) | Team | 2026-10-07 |
| GRPO attempt | decided at the end of Week 11, only if Step 17 is finished | Role C | to decide |
| Ask Reyes et al. and the TerraFormer authors for data or weights | emails sent in Week 8 | Role C | to do |

## 6. Interpretation decisions (where the plan documents needed a ruling)

- **D1. Patch-IR attr names.** `attr` uses finding field names, as in `privacy/tests/test_vault.py` (`versioning_status`), not Terraform attribute names.
- **D2. What reaches the model.** The model input is the airlock output for one (resource, rule) pair, so only the fields that the triggering rule reads reach it. Decoy attributes (tags, unrelated numbers, extra attributes) are by definition fields no rule reads, so they never reach the model. Their job in Phase 5 is to stress patch application and the hidden check "decoys untouched". A mutated resource with several violations produces one example per violated rule, each showing only that rule's fields.
- **D3. Gate in Phase 5 is a stub.** (a) Rego rules re-run on the patched resource through OPA; (b) instead of re-scoring an attack graph, check that no rule that was silent before now fires and the target rule is silent; (c) intent preservation: the patch deletes or replaces nothing; (d) no new principal: every ARN, role or CIDR token in the patch must already appear in the finding. The full gate, with graph re-scoring, arrives in Phase 7.
- **D4. Account-level rules have no Terraform base.** `account_mfa_enabled`, `cloudtrail_enabled` and `guardduty_enabled` are account facts, so their Tier A bases are synthetic fixtures written by us and documented as such in the dataset card.
- **D5. Values the model cannot see.** For security-group narrowing and for IAM full-admin statements, the projected record does not contain the original, safe value (the original CIDR or the original scope). The reference-patch convention for these is decided at Step 5 with the team; until then both routes stay "M1".
- **D6. One-time scoring rule.** The unit is the pair (model, held-out set): each pair is scored once. Baseline models are frozen at Step 15, so their held-out rows may be produced then. Every decision (model size, checkpoint, sampling settings) uses validation numbers only.
- **D7. Phase 1 skeleton and Python packages.** `ml/mutation_engine/mutators.py` and `ml/mutation_engine/test_mutators.py` stay as they are until Step 5. Do not add an `__init__.py` to `ml/mutation_engine/`: the Phase 1 test imports `mutators` as a top-level module and would stop working.
- **D8. Bases are attribute dictionaries, not Terraform text.** A base keeps `attrs` (every field a rule reads, Rego names) and `extras` (harmless real attributes no rule reads). Step 5 mutators edit `attrs`; the Phase 1 text-replacing mutators are superseded.
- **D9. Real compliant S3 buckets are rare.** If Step 4 yields too few clean S3 bases, Step 5 adds documented "completed" bases (a real bucket's extras plus synthetic compliance fields).
- **D10. The model input has few distinct values.** The airlock projects only the rule's fields, so identical inputs across splits are unavoidable. The Step 9 leakage check hashes the full mutated resource (attrs plus extras), not the projected input.
- **D11. The Phase 1 skeleton moved to ml/mutation_engine/phase1_skeleton/.** The Step 5 package ml/mutation_engine/mutators/ replaces it; this supersedes D7.
- **D12. Reference fixes for values the model cannot see.** Security groups: restrict_cidr to the placeholder INTERNAL_CIDR (resolved by the Phase 7 compiler). Encryption: aws:kms. IAM: wildcard appended, fix restores the original lists. The example original is the base with these values canonical.
- **D13. Ops used in Phase 5 data:** set_attr, restrict_cidr, set_lifecycle_rule, escalate. add_policy_statement, remove_policy_statement and enable_feature are unused (limitation).
- **D14. Synthetic bases:** completed S3 buckets and 40 account fixtures, in bases_synthetic.jsonl, each marked in source.synthetic.

## 7. Change log

| Date | Change | Reason | Approved by |
|---|---|---|---|
| 2026-10-07 | First version | Phase 5 Step 1 | |
| 2026-10-07 | Added D8, D9, D10 | Phase 5 Step 4 findings | |
| 2026-10-18 | Added D11 to D14 | Phase 5 Steps 5-7 | |
