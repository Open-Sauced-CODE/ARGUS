# Tier C funnel

## Tier C-verifier (our rules on real repositories)
| step | count |
|---|---:|
| repos_scanned | 58 |
| files_parsed | 7050 |
| parse_errors | 40 |
| records | 2028 |
| resources_skipped_unresolved | 1278 |
| violations | 2128 |
| duplicate_in_repo | 1194 |
| over_repo_cap | 152 |
| duplicate_across_repos | 316 |
| blocked_by_airlock | 0 |
| findings_written | 466 |

Findings by rule: {'cis.iam_no_full_admin': 2, 'cis.s3_default_encryption': 51, 'cis.s3_public_access_block': 78, 'cis.sg_open_ingress': 46, 'dpdp.rule6_logging': 67, 'dpdp.rule6_public_exposure': 77, 'dpdp.rule6_sg_open_ingress': 46, 'dpdp.rule6a': 48, 'dpdp.rule6a_rds': 51}

## Tier C-mined (real fixes from git history)
| step | count |
|---|---:|
| repos_scanned | 58 |
| repos_git_error | 0 |
| commits_touching_tf | 4251 |
| commits_dropped_by_keyword_prefilter | 735 |
| ambiguous_multi_record | 0 |
| resource_pairs | 0 |
| resource_pairs_changed | 0 |
| violating_before_passing_after | 0 |
| out_of_vocabulary_attribute_removed | 0 |
| out_of_vocabulary_no_rule_field_changed | 0 |
| airlock_or_token_problem | 0 |
| not_schema_valid | 0 |
| gate_rejected_human_fix | 0 |
| duplicate | 0 |
| over_repo_cap | 0 |
| in_vocabulary_gate_passing | 0 |
| candidates written for review | 0 |
| reviewed and kept by a person | 0 |

Each drop is informative: a large out-of-vocabulary count says how often real fixes need operations Patch-IR does not have.
