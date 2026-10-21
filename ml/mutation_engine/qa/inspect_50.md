# 50 examples for the hand inspection (Step 8)

Read each one. Ask: (1) does the fix fix what the input shows? (2) is it the smallest fix? (3) would a careful engineer agree?
Write your verdicts in qa/inspection_log.md.

## 1. ex-000488 (train) rule dpdp.rule6_sg_open_ingress
mutators: ['m_sg_world_open']  variants: ['all_traffic_v6']
INPUT : {"fields": {"fromport": 0, "ip_range": "::/0", "protocol": "-1", "resource_type": "AWSIpPermissionInbound", "toport": 0}, "finding_id": "F-1", "resource_id": "RESOURCE_1", "resource_ref": "RESOURCE_1", "rule_id": "dpdp.rule6_sg_open_ingress"}
TARGET: {"finding_id": "F-1", "ops": [{"attr": "ip_range", "op": "restrict_cidr", "value": "INTERNAL_CIDR"}], "rationale_ref": "dpdp.rule6_sg_open_ingress", "resource_ref": "RESOURCE_1"}

## 2. ex-001309 (train) rule dpdp.rule6_sg_open_ingress
mutators: ['m_sg_world_open']  variants: ['base_v6']
INPUT : {"fields": {"fromport": 0, "ip_range": "::/0", "protocol": "tcp", "resource_type": "AWSIpPermissionInbound", "toport": 65535}, "finding_id": "F-1", "resource_id": "RESOURCE_1", "resource_ref": "RESOURCE_1", "rule_id": "dpdp.rule6_sg_open_ingress"}
TARGET: {"finding_id": "F-1", "ops": [{"attr": "ip_range", "op": "restrict_cidr", "value": "INTERNAL_CIDR"}], "rationale_ref": "dpdp.rule6_sg_open_ingress", "resource_ref": "RESOURCE_1"}

## 3. ex-002059 (train) rule cis.sg_open_ingress
mutators: ['m_sg_world_open']  variants: ['mysql_v4']
INPUT : {"fields": {"fromport": 3306, "ip_range": "0.0.0.0/0", "protocol": "tcp", "resource_type": "AWSIpPermissionInbound", "toport": 3306}, "finding_id": "F-0", "resource_id": "RESOURCE_1", "resource_ref": "RESOURCE_1", "rule_id": "cis.sg_open_ingress"}
TARGET: {"finding_id": "F-0", "ops": [{"attr": "ip_range", "op": "restrict_cidr", "value": "INTERNAL_CIDR"}], "rationale_ref": "cis.sg_open_ingress", "resource_ref": "RESOURCE_1"}

## 4. ex-002097 (train) rule dpdp.rule6_sg_open_ingress
mutators: ['m_sg_world_open']  variants: ['postgres_v6']
INPUT : {"fields": {"fromport": 5432, "ip_range": "::/0", "protocol": "tcp", "resource_type": "AWSIpPermissionInbound", "toport": 5432}, "finding_id": "F-1", "resource_id": "RESOURCE_1", "resource_ref": "RESOURCE_1", "rule_id": "dpdp.rule6_sg_open_ingress"}
TARGET: {"finding_id": "F-1", "ops": [{"attr": "ip_range", "op": "restrict_cidr", "value": "INTERNAL_CIDR"}], "rationale_ref": "dpdp.rule6_sg_open_ingress", "resource_ref": "RESOURCE_1"}

## 5. ex-002651 (val) rule dpdp.rule6_public_exposure
mutators: ['m_s3_public_block_off']  variants: ['one_acls']
INPUT : {"fields": {"block_public_acls": false, "block_public_policy": true, "ignore_public_acls": true, "resource_type": "AWSS3Bucket", "restrict_public_buckets": true}, "finding_id": "F-1", "resource_id": "BUCKET_1", "resource_ref": "BUCKET_1", "rule_id": "dpdp.rule6_public_exposure"}
TARGET: {"finding_id": "F-1", "ops": [{"attr": "block_public_acls", "op": "set_attr", "value": true}], "rationale_ref": "dpdp.rule6_public_exposure", "resource_ref": "BUCKET_1"}

## 6. ex-000421 (train) rule dpdp.rule6_public_exposure
mutators: ['m_s3_public_block_off', 'm_s3_sse_off']  variants: ['one_acls', 'keep']
INPUT : {"fields": {"block_public_acls": false, "block_public_policy": true, "ignore_public_acls": true, "resource_type": "AWSS3Bucket", "restrict_public_buckets": true}, "finding_id": "F-2", "resource_id": "BUCKET_1", "resource_ref": "BUCKET_1", "rule_id": "dpdp.rule6_public_exposure"}
TARGET: {"finding_id": "F-2", "ops": [{"attr": "block_public_acls", "op": "set_attr", "value": true}], "rationale_ref": "dpdp.rule6_public_exposure", "resource_ref": "BUCKET_1"}

## 7. ex-000915 (train) rule dpdp.rule6_public_exposure
mutators: ['m_s3_public_block_off', 'm_s3_sse_off']  variants: ['one_acls', 'keep']
INPUT : {"fields": {"block_public_acls": false, "block_public_policy": true, "ignore_public_acls": true, "resource_type": "AWSS3Bucket", "restrict_public_buckets": true}, "finding_id": "F-2", "resource_id": "BUCKET_1", "resource_ref": "BUCKET_1", "rule_id": "dpdp.rule6_public_exposure"}
TARGET: {"finding_id": "F-2", "ops": [{"attr": "block_public_acls", "op": "set_attr", "value": true}], "rationale_ref": "dpdp.rule6_public_exposure", "resource_ref": "BUCKET_1"}

## 8. ex-002462 (train) rule cis.iam_no_full_admin
mutators: ['m_iam_full_admin']  variants: ['action_only']
INPUT : {"fields": {"action": ["ssm:SendCommand", "ssm:ListCommands", "ssm:ListCommandInvocations", "ssm:DescribeInstanceInformation", "ssm:GetAutomationExecution", "ssm:DescribeAutomationExecutions", "ssm:DescribeAutomationStepExecutions", "ssm:StopAutomationExecution", "ssm:GetParameter", "ssm:GetParameters", "*"], "effect": "Allow", "resource": ["*"], "resource_type": "AWSPolicyStatement"}, "finding_id": "F-0", "resource_id": "RESOURCE_1", "resource_ref": "RESOURCE_1", "rule_id": "cis.iam_no_full_admin"}
TARGET: {"finding_id": "F-0", "ops": [{"attr": "action", "op": "set_attr", "value": ["ssm:SendCommand", "ssm:ListCommands", "ssm:ListCommandInvocations", "ssm:DescribeInstanceInformation", "ssm:GetAutomationExecution", "ssm:DescribeAutomationExecutions", "ssm:DescribeAutomationStepExecutions", "ssm:StopAutomationExecution", "ssm:GetParameter", "ssm:GetParameters"]}], "rationale_ref": "cis.iam_no_full_admin", "resource_ref": "RESOURCE_1"}

## 9. ex-002546 (val) rule dpdp.rule7_detection
mutators: ['m_account_detection_off']  variants: ['guardduty_off']
INPUT : {"fields": {"cloudtrail_enabled": true, "guardduty_enabled": false, "resource_type": "AWSAccount"}, "finding_id": "F-0", "resource_id": "RESOURCE_1", "resource_ref": "RESOURCE_1", "rule_id": "dpdp.rule7_detection"}
TARGET: {"finding_id": "F-0", "ops": [{"op": "escalate", "reason": "CloudTrail and GuardDuty would be new resources, which Patch-IR cannot create."}], "rationale_ref": "dpdp.rule7_detection", "resource_ref": "RESOURCE_1"}

## 10. ex-002280 (train) rule dpdp.rule6_sg_open_ingress
mutators: ['m_sg_world_open']  variants: ['rdp_v6']
INPUT : {"fields": {"fromport": 3389, "ip_range": "::/0", "protocol": "tcp", "resource_type": "AWSIpPermissionInbound", "toport": 3389}, "finding_id": "F-1", "resource_id": "RESOURCE_1", "resource_ref": "RESOURCE_1", "rule_id": "dpdp.rule6_sg_open_ingress"}
TARGET: {"finding_id": "F-1", "ops": [{"attr": "ip_range", "op": "restrict_cidr", "value": "INTERNAL_CIDR"}], "rationale_ref": "dpdp.rule6_sg_open_ingress", "resource_ref": "RESOURCE_1"}

## 11. ex-001723 (train) rule dpdp.rule6_sg_open_ingress
mutators: ['m_sg_world_open']  variants: ['base_v4']
INPUT : {"fields": {"fromport": 0, "ip_range": "0.0.0.0/0", "protocol": "tcp", "resource_type": "AWSIpPermissionInbound", "toport": 3000}, "finding_id": "F-1", "resource_id": "RESOURCE_1", "resource_ref": "RESOURCE_1", "rule_id": "dpdp.rule6_sg_open_ingress"}
TARGET: {"finding_id": "F-1", "ops": [{"attr": "ip_range", "op": "restrict_cidr", "value": "INTERNAL_CIDR"}], "rationale_ref": "dpdp.rule6_sg_open_ingress", "resource_ref": "RESOURCE_1"}

## 12. ex-003209 (B2) rule cis.s3_default_encryption
mutators: ['m_s3_sse_off']  variants: ['clear']
INPUT : {"fields": {"default_encryption": false, "resource_type": "AWSS3Bucket"}, "finding_id": "F-0", "resource_id": "BUCKET_1", "resource_ref": "BUCKET_1", "rule_id": "cis.s3_default_encryption"}
TARGET: {"finding_id": "F-0", "ops": [{"attr": "default_encryption", "op": "set_attr", "value": true}, {"attr": "encryption_algorithm", "op": "set_attr", "value": "aws:kms"}], "rationale_ref": "cis.s3_default_encryption", "resource_ref": "BUCKET_1"}

## 13. ex-002346 (train) rule dpdp.rule15_region
mutators: ['m_region_outside_approved']  variants: ['us_east_1']
INPUT : {"fields": {"approved_regions": ["ap-south-1", "ap-south-2"], "personal_data": true, "region": "us-east-1"}, "finding_id": "F-0", "resource_id": "RESOURCE_1", "resource_ref": "RESOURCE_1", "rule_id": "dpdp.rule15_region"}
TARGET: {"finding_id": "F-0", "ops": [{"op": "escalate", "reason": "Moving personal data to another region is a data migration, which Patch-IR cannot express."}], "rationale_ref": "dpdp.rule15_region", "resource_ref": "RESOURCE_1"}

## 14. ex-002244 (train) rule dpdp.rule8_lifecycle
mutators: ['m_s3_lifecycle_off']  variants: ['missing']
INPUT : {"fields": {"personal_data": true, "resource_type": "AWSS3Bucket"}, "finding_id": "F-0", "resource_id": "BUCKET_1", "resource_ref": "BUCKET_1", "rule_id": "dpdp.rule8_lifecycle"}
TARGET: {"finding_id": "F-0", "ops": [{"attr": "has_lifecycle_expiration", "op": "set_lifecycle_rule", "value": true}], "rationale_ref": "dpdp.rule8_lifecycle", "resource_ref": "BUCKET_1"}

## 15. ex-002993 (B1) rule dpdp.rule6_account_mfa
mutators: ['m_account_detection_off', 'm_account_mfa_off']  variants: ['both_off', 'false']
INPUT : {"fields": {"account_mfa_enabled": false, "resource_type": "AWSAccount"}, "finding_id": "F-0", "resource_id": "RESOURCE_1", "resource_ref": "RESOURCE_1", "rule_id": "dpdp.rule6_account_mfa"}
TARGET: {"finding_id": "F-0", "ops": [{"op": "escalate", "reason": "Enabling account-level MFA is a human action and cannot be expressed as a Terraform change."}], "rationale_ref": "dpdp.rule6_account_mfa", "resource_ref": "RESOURCE_1"}

## 16. ex-003181 (B2) rule dpdp.rule6a_rds
mutators: ['m_rds_unencrypted']  variants: ['missing']
INPUT : {"fields": {"resource_type": "AWSRDSInstance"}, "finding_id": "F-0", "resource_id": "DB_1", "resource_ref": "DB_1", "rule_id": "dpdp.rule6a_rds"}
TARGET: {"finding_id": "F-0", "ops": [{"op": "escalate", "reason": "An existing RDS instance cannot be encrypted in place; it needs a snapshot copy and restore, which Patch-IR cannot express."}], "rationale_ref": "dpdp.rule6a_rds", "resource_ref": "DB_1"}

## 17. ex-003147 (B2) rule dpdp.rule6a
mutators: ['m_s3_sse_algo']  variants: ['kms_legacy']
INPUT : {"fields": {"default_encryption": true, "encryption_algorithm": "aws:kms:legacy", "resource_type": "AWSS3Bucket"}, "finding_id": "F-0", "resource_id": "BUCKET_1", "resource_ref": "BUCKET_1", "rule_id": "dpdp.rule6a"}
TARGET: {"finding_id": "F-0", "ops": [{"attr": "encryption_algorithm", "op": "set_attr", "value": "aws:kms"}], "rationale_ref": "dpdp.rule6a", "resource_ref": "BUCKET_1"}

## 18. ex-002011 (train) rule cis.iam_no_full_admin
mutators: ['m_iam_full_admin']  variants: ['both']
INPUT : {"fields": {"action": ["logs:DescribeLogStreams", "*"], "effect": "Allow", "resource": ["arn:aws:logs:*:*:log-group:dms-tasks-*", "*"], "resource_type": "AWSPolicyStatement"}, "finding_id": "F-0", "resource_id": "RESOURCE_1", "resource_ref": "RESOURCE_1", "rule_id": "cis.iam_no_full_admin"}
TARGET: {"finding_id": "F-0", "ops": [{"attr": "action", "op": "set_attr", "value": ["logs:DescribeLogStreams"]}, {"attr": "resource", "op": "set_attr", "value": ["arn:aws:logs:*:*:log-group:dms-tasks-*"]}], "rationale_ref": "cis.iam_no_full_admin", "resource_ref": "RESOURCE_1"}

## 19. ex-003077 (B1) rule dpdp.rule6_account_mfa
mutators: ['m_account_mfa_off', 'm_account_detection_off']  variants: ['missing', 'cloudtrail_off']
INPUT : {"fields": {"resource_type": "AWSAccount"}, "finding_id": "F-0", "resource_id": "RESOURCE_1", "resource_ref": "RESOURCE_1", "rule_id": "dpdp.rule6_account_mfa"}
TARGET: {"finding_id": "F-0", "ops": [{"op": "escalate", "reason": "Enabling account-level MFA is a human action and cannot be expressed as a Terraform change."}], "rationale_ref": "dpdp.rule6_account_mfa", "resource_ref": "RESOURCE_1"}

## 20. ex-003167 (B2) rule dpdp.rule6a
mutators: ['m_s3_sse_algo']  variants: ['none']
INPUT : {"fields": {"default_encryption": true, "encryption_algorithm": "NONE", "resource_type": "AWSS3Bucket"}, "finding_id": "F-0", "resource_id": "BUCKET_1", "resource_ref": "BUCKET_1", "rule_id": "dpdp.rule6a"}
TARGET: {"finding_id": "F-0", "ops": [{"attr": "encryption_algorithm", "op": "set_attr", "value": "aws:kms"}], "rationale_ref": "dpdp.rule6a", "resource_ref": "BUCKET_1"}

## 21. ex-002403 (train) rule cis.sg_open_ingress
mutators: ['m_sg_world_open']  variants: ['all_traffic_v4']
INPUT : {"fields": {"fromport": 0, "ip_range": "0.0.0.0/0", "protocol": "-1", "resource_type": "AWSIpPermissionInbound", "toport": 0}, "finding_id": "F-0", "resource_id": "RESOURCE_1", "resource_ref": "RESOURCE_1", "rule_id": "cis.sg_open_ingress"}
TARGET: {"finding_id": "F-0", "ops": [{"attr": "ip_range", "op": "restrict_cidr", "value": "INTERNAL_CIDR"}], "rationale_ref": "cis.sg_open_ingress", "resource_ref": "RESOURCE_1"}

## 22. ex-001807 (train) rule cis.sg_open_ingress
mutators: ['m_sg_world_open']  variants: ['all_traffic_v4']
INPUT : {"fields": {"fromport": 0, "ip_range": "0.0.0.0/0", "protocol": "-1", "resource_type": "AWSIpPermissionInbound", "toport": 0}, "finding_id": "F-0", "resource_id": "RESOURCE_1", "resource_ref": "RESOURCE_1", "rule_id": "cis.sg_open_ingress"}
TARGET: {"finding_id": "F-0", "ops": [{"attr": "ip_range", "op": "restrict_cidr", "value": "INTERNAL_CIDR"}], "rationale_ref": "cis.sg_open_ingress", "resource_ref": "RESOURCE_1"}

## 23. ex-000983 (train) rule dpdp.rule6_public_exposure
mutators: ['m_s3_public_block_off']  variants: ['one_restrict']
INPUT : {"fields": {"block_public_acls": true, "block_public_policy": true, "ignore_public_acls": true, "resource_type": "AWSS3Bucket", "restrict_public_buckets": false}, "finding_id": "F-1", "resource_id": "BUCKET_1", "resource_ref": "BUCKET_1", "rule_id": "dpdp.rule6_public_exposure"}
TARGET: {"finding_id": "F-1", "ops": [{"attr": "restrict_public_buckets", "op": "set_attr", "value": true}], "rationale_ref": "dpdp.rule6_public_exposure", "resource_ref": "BUCKET_1"}

## 24. ex-000011 (train) rule cis.s3_public_access_block
mutators: ['m_s3_public_block_off']  variants: ['missing']
INPUT : {"fields": {"resource_type": "AWSS3Bucket"}, "finding_id": "F-0", "resource_id": "BUCKET_1", "resource_ref": "BUCKET_1", "rule_id": "cis.s3_public_access_block"}
TARGET: {"finding_id": "F-0", "ops": [{"attr": "block_public_acls", "op": "set_attr", "value": true}, {"attr": "block_public_policy", "op": "set_attr", "value": true}, {"attr": "ignore_public_acls", "op": "set_attr", "value": true}, {"attr": "restrict_public_buckets", "op": "set_attr", "value": true}], "rationale_ref": "cis.s3_public_access_block", "resource_ref": "BUCKET_1"}

## 25. ex-002516 (val) rule dpdp.rule6a
mutators: ['m_s3_sse_algo']  variants: ['aes128']
INPUT : {"fields": {"default_encryption": true, "encryption_algorithm": "AES128", "resource_type": "AWSS3Bucket"}, "finding_id": "F-0", "resource_id": "BUCKET_1", "resource_ref": "BUCKET_1", "rule_id": "dpdp.rule6a"}
TARGET: {"finding_id": "F-0", "ops": [{"attr": "encryption_algorithm", "op": "set_attr", "value": "aws:kms"}], "rationale_ref": "dpdp.rule6a", "resource_ref": "BUCKET_1"}

## 26. ex-000331 (train) rule dpdp.rule6_public_exposure
mutators: ['m_s3_logging_off', 'm_s3_public_block_off']  variants: ['missing', 'missing']
INPUT : {"fields": {"resource_type": "AWSS3Bucket"}, "finding_id": "F-2", "resource_id": "BUCKET_1", "resource_ref": "BUCKET_1", "rule_id": "dpdp.rule6_public_exposure"}
TARGET: {"finding_id": "F-2", "ops": [{"attr": "block_public_acls", "op": "set_attr", "value": true}, {"attr": "block_public_policy", "op": "set_attr", "value": true}, {"attr": "ignore_public_acls", "op": "set_attr", "value": true}, {"attr": "restrict_public_buckets", "op": "set_attr", "value": true}], "rationale_ref": "dpdp.rule6_public_exposure", "resource_ref": "BUCKET_1"}

## 27. ex-000454 (train) rule dpdp.rule6_public_exposure
mutators: ['m_s3_public_block_off']  variants: ['one_restrict']
INPUT : {"fields": {"block_public_acls": true, "block_public_policy": true, "ignore_public_acls": true, "resource_type": "AWSS3Bucket", "restrict_public_buckets": false}, "finding_id": "F-1", "resource_id": "BUCKET_1", "resource_ref": "BUCKET_1", "rule_id": "dpdp.rule6_public_exposure"}
TARGET: {"finding_id": "F-1", "ops": [{"attr": "restrict_public_buckets", "op": "set_attr", "value": true}], "rationale_ref": "dpdp.rule6_public_exposure", "resource_ref": "BUCKET_1"}

## 28. ex-001177 (train) rule cis.iam_no_full_admin
mutators: ['m_iam_full_admin']  variants: ['both']
INPUT : {"fields": {"action": ["elasticloadbalancing:ModifyTargetGroup", "elasticloadbalancing:ModifyTargetGroupAttributes", "elasticloadbalancing:AddTags", "elasticloadbalancing:RemoveTags", "*"], "effect": "Allow", "resource": ["arn:aws:elasticloadbalancing:*:*:targetgroup/*/*", "*"], "resource_type": "AWSPolicyStatement"}, "finding_id": "F-0", "resource_id": "RESOURCE_1", "resource_ref": "RESOURCE_1", "rule_id": "cis.iam_no_full_admin"}
TARGET: {"finding_id": "F-0", "ops": [{"attr": "action", "op": "set_attr", "value": ["elasticloadbalancing:ModifyTargetGroup", "elasticloadbalancing:ModifyTargetGroupAttributes", "elasticloadbalancing:AddTags", "elasticloadbalancing:RemoveTags"]}, {"attr": "resource", "op": "set_attr", "value": ["arn:aws:elasticloadbalancing:*:*:targetgroup/*/*"]}], "rationale_ref": "cis.iam_no_full_admin", "resource_ref": "RESOURCE_1"}

## 29. ex-000402 (train) rule dpdp.rule6_sg_open_ingress
mutators: ['m_sg_world_open']  variants: ['ssh_v4']
INPUT : {"fields": {"fromport": 22, "ip_range": "0.0.0.0/0", "protocol": "tcp", "resource_type": "AWSIpPermissionInbound", "toport": 22}, "finding_id": "F-1", "resource_id": "RESOURCE_1", "resource_ref": "RESOURCE_1", "rule_id": "dpdp.rule6_sg_open_ingress"}
TARGET: {"finding_id": "F-1", "ops": [{"attr": "ip_range", "op": "restrict_cidr", "value": "INTERNAL_CIDR"}], "rationale_ref": "dpdp.rule6_sg_open_ingress", "resource_ref": "RESOURCE_1"}

## 30. ex-001842 (train) rule cis.s3_public_access_block
mutators: ['m_s3_public_block_off']  variants: ['all_off']
INPUT : {"fields": {"block_public_acls": false, "block_public_policy": false, "ignore_public_acls": false, "resource_type": "AWSS3Bucket", "restrict_public_buckets": false}, "finding_id": "F-0", "resource_id": "BUCKET_1", "resource_ref": "BUCKET_1", "rule_id": "cis.s3_public_access_block"}
TARGET: {"finding_id": "F-0", "ops": [{"attr": "block_public_acls", "op": "set_attr", "value": true}, {"attr": "block_public_policy", "op": "set_attr", "value": true}, {"attr": "ignore_public_acls", "op": "set_attr", "value": true}, {"attr": "restrict_public_buckets", "op": "set_attr", "value": true}], "rationale_ref": "cis.s3_public_access_block", "resource_ref": "BUCKET_1"}

## 31. ex-000048 (train) rule dpdp.rule6_public_exposure
mutators: ['m_s3_public_block_off']  variants: ['one_ignore']
INPUT : {"fields": {"block_public_acls": true, "block_public_policy": true, "ignore_public_acls": false, "resource_type": "AWSS3Bucket", "restrict_public_buckets": true}, "finding_id": "F-1", "resource_id": "BUCKET_1", "resource_ref": "BUCKET_1", "rule_id": "dpdp.rule6_public_exposure"}
TARGET: {"finding_id": "F-1", "ops": [{"attr": "ignore_public_acls", "op": "set_attr", "value": true}], "rationale_ref": "dpdp.rule6_public_exposure", "resource_ref": "BUCKET_1"}

## 32. ex-002807 (val) rule dpdp.rule6a
mutators: ['m_s3_sse_algo']  variants: ['aes128']
INPUT : {"fields": {"default_encryption": true, "encryption_algorithm": "AES128", "resource_type": "AWSS3Bucket"}, "finding_id": "F-0", "resource_id": "BUCKET_1", "resource_ref": "BUCKET_1", "rule_id": "dpdp.rule6a"}
TARGET: {"finding_id": "F-0", "ops": [{"attr": "encryption_algorithm", "op": "set_attr", "value": "aws:kms"}], "rationale_ref": "dpdp.rule6a", "resource_ref": "BUCKET_1"}

## 33. ex-002009 (train) rule dpdp.rule6_public_exposure
mutators: ['m_s3_public_block_off']  variants: ['all_off']
INPUT : {"fields": {"block_public_acls": false, "block_public_policy": false, "ignore_public_acls": false, "resource_type": "AWSS3Bucket", "restrict_public_buckets": false}, "finding_id": "F-1", "resource_id": "BUCKET_1", "resource_ref": "BUCKET_1", "rule_id": "dpdp.rule6_public_exposure"}
TARGET: {"finding_id": "F-1", "ops": [{"attr": "block_public_acls", "op": "set_attr", "value": true}, {"attr": "block_public_policy", "op": "set_attr", "value": true}, {"attr": "ignore_public_acls", "op": "set_attr", "value": true}, {"attr": "restrict_public_buckets", "op": "set_attr", "value": true}], "rationale_ref": "dpdp.rule6_public_exposure", "resource_ref": "BUCKET_1"}

## 34. ex-002783 (val) rule cis.sg_open_ingress
mutators: ['m_sg_world_open']  variants: ['wide_v4']
INPUT : {"fields": {"fromport": 0, "ip_range": "0.0.0.0/0", "protocol": "tcp", "resource_type": "AWSIpPermissionInbound", "toport": 65535}, "finding_id": "F-0", "resource_id": "RESOURCE_1", "resource_ref": "RESOURCE_1", "rule_id": "cis.sg_open_ingress"}
TARGET: {"finding_id": "F-0", "ops": [{"attr": "ip_range", "op": "restrict_cidr", "value": "INTERNAL_CIDR"}], "rationale_ref": "cis.sg_open_ingress", "resource_ref": "RESOURCE_1"}

## 35. ex-001288 (train) rule dpdp.rule7_detection
mutators: ['m_account_detection_off']  variants: ['cloudtrail_off']
INPUT : {"fields": {"cloudtrail_enabled": false, "guardduty_enabled": true, "resource_type": "AWSAccount"}, "finding_id": "F-0", "resource_id": "RESOURCE_1", "resource_ref": "RESOURCE_1", "rule_id": "dpdp.rule7_detection"}
TARGET: {"finding_id": "F-0", "ops": [{"op": "escalate", "reason": "CloudTrail and GuardDuty would be new resources, which Patch-IR cannot create."}], "rationale_ref": "dpdp.rule7_detection", "resource_ref": "RESOURCE_1"}

## 36. ex-000862 (train) rule cis.s3_public_access_block
mutators: ['m_s3_public_block_off']  variants: ['one_restrict']
INPUT : {"fields": {"block_public_acls": true, "block_public_policy": true, "ignore_public_acls": true, "resource_type": "AWSS3Bucket", "restrict_public_buckets": false}, "finding_id": "F-0", "resource_id": "BUCKET_1", "resource_ref": "BUCKET_1", "rule_id": "cis.s3_public_access_block"}
TARGET: {"finding_id": "F-0", "ops": [{"attr": "restrict_public_buckets", "op": "set_attr", "value": true}], "rationale_ref": "cis.s3_public_access_block", "resource_ref": "BUCKET_1"}

## 37. ex-001628 (train) rule dpdp.rule6_sg_open_ingress
mutators: ['m_sg_world_open']  variants: ['base_v6']
INPUT : {"fields": {"fromport": 0, "ip_range": "::/0", "protocol": "-1", "resource_type": "AWSIpPermissionInbound", "toport": 65535}, "finding_id": "F-1", "resource_id": "RESOURCE_1", "resource_ref": "RESOURCE_1", "rule_id": "dpdp.rule6_sg_open_ingress"}
TARGET: {"finding_id": "F-1", "ops": [{"attr": "ip_range", "op": "restrict_cidr", "value": "INTERNAL_CIDR"}], "rationale_ref": "dpdp.rule6_sg_open_ingress", "resource_ref": "RESOURCE_1"}

## 38. ex-001031 (train) rule dpdp.rule6_sg_open_ingress
mutators: ['m_sg_world_open']  variants: ['postgres_v4']
INPUT : {"fields": {"fromport": 5432, "ip_range": "0.0.0.0/0", "protocol": "tcp", "resource_type": "AWSIpPermissionInbound", "toport": 5432}, "finding_id": "F-1", "resource_id": "RESOURCE_1", "resource_ref": "RESOURCE_1", "rule_id": "dpdp.rule6_sg_open_ingress"}
TARGET: {"finding_id": "F-1", "ops": [{"attr": "ip_range", "op": "restrict_cidr", "value": "INTERNAL_CIDR"}], "rationale_ref": "dpdp.rule6_sg_open_ingress", "resource_ref": "RESOURCE_1"}

## 39. ex-001425 (train) rule cis.sg_open_ingress
mutators: ['m_sg_world_open']  variants: ['wide_v4']
INPUT : {"fields": {"fromport": 0, "ip_range": "0.0.0.0/0", "protocol": "tcp", "resource_type": "AWSIpPermissionInbound", "toport": 65535}, "finding_id": "F-0", "resource_id": "RESOURCE_1", "resource_ref": "RESOURCE_1", "rule_id": "cis.sg_open_ingress"}
TARGET: {"finding_id": "F-0", "ops": [{"attr": "ip_range", "op": "restrict_cidr", "value": "INTERNAL_CIDR"}], "rationale_ref": "cis.sg_open_ingress", "resource_ref": "RESOURCE_1"}

## 40. ex-001461 (train) rule cis.iam_no_full_admin
mutators: ['m_iam_full_admin']  variants: ['action_only']
INPUT : {"fields": {"action": ["autoscaling:DescribeAutoScalingGroups", "autoscaling:DescribeAutoScalingInstances", "autoscaling:DescribeLaunchConfigurations", "autoscaling:DescribeScalingActivities", "autoscaling:DescribeTags", "ec2:DescribeImages", "ec2:DescribeInstanceTypes", "ec2:DescribeLaunchTemplateVersions", "ec2:GetInstanceTypesFromInstanceRequirements", "eks:DescribeNodegroup", "*"], "effect": "Allow", "resource": ["*"], "resource_type": "AWSPolicyStatement"}, "finding_id": "F-0", "resource_id": "RESOURCE_1", "resource_ref": "RESOURCE_1", "rule_id": "cis.iam_no_full_admin"}
TARGET: {"finding_id": "F-0", "ops": [{"attr": "action", "op": "set_attr", "value": ["autoscaling:DescribeAutoScalingGroups", "autoscaling:DescribeAutoScalingInstances", "autoscaling:DescribeLaunchConfigurations", "autoscaling:DescribeScalingActivities", "autoscaling:DescribeTags", "ec2:DescribeImages", "ec2:DescribeInstanceTypes", "ec2:DescribeLaunchTemplateVersions", "ec2:GetInstanceTypesFromInstanceRequirements", "eks:DescribeNodegroup"]}], "rationale_ref": "cis.iam_no_full_admin", "resource_ref": "RESOURCE_1"}

## 41. ex-003298 (B2) rule cis.s3_default_encryption
mutators: ['m_s3_sse_off']  variants: ['clear']
INPUT : {"fields": {"default_encryption": false, "resource_type": "AWSS3Bucket"}, "finding_id": "F-0", "resource_id": "BUCKET_1", "resource_ref": "BUCKET_1", "rule_id": "cis.s3_default_encryption"}
TARGET: {"finding_id": "F-0", "ops": [{"attr": "default_encryption", "op": "set_attr", "value": true}, {"attr": "encryption_algorithm", "op": "set_attr", "value": "aws:kms"}], "rationale_ref": "cis.s3_default_encryption", "resource_ref": "BUCKET_1"}

## 42. ex-001542 (train) rule cis.sg_open_ingress
mutators: ['m_sg_world_open']  variants: ['postgres_v6']
INPUT : {"fields": {"fromport": 5432, "ip_range": "::/0", "protocol": "tcp", "resource_type": "AWSIpPermissionInbound", "toport": 5432}, "finding_id": "F-0", "resource_id": "RESOURCE_1", "resource_ref": "RESOURCE_1", "rule_id": "cis.sg_open_ingress"}
TARGET: {"finding_id": "F-0", "ops": [{"attr": "ip_range", "op": "restrict_cidr", "value": "INTERNAL_CIDR"}], "rationale_ref": "cis.sg_open_ingress", "resource_ref": "RESOURCE_1"}

## 43. ex-003056 (B1) rule dpdp.rule6_logging
mutators: ['m_s3_lifecycle_off', 'm_s3_logging_off']  variants: ['missing', 'missing']
INPUT : {"fields": {"resource_type": "AWSS3Bucket"}, "finding_id": "F-0", "resource_id": "BUCKET_1", "resource_ref": "BUCKET_1", "rule_id": "dpdp.rule6_logging"}
TARGET: {"finding_id": "F-0", "ops": [{"attr": "logging_enabled", "op": "set_attr", "value": true}], "rationale_ref": "dpdp.rule6_logging", "resource_ref": "BUCKET_1"}

## 44. ex-002104 (train) rule dpdp.rule6a
mutators: ['m_s3_lifecycle_off', 'm_s3_sse_off']  variants: ['missing', 'keep']
INPUT : {"fields": {"default_encryption": false, "encryption_algorithm": "AES256", "resource_type": "AWSS3Bucket"}, "finding_id": "F-1", "resource_id": "BUCKET_1", "resource_ref": "BUCKET_1", "rule_id": "dpdp.rule6a"}
TARGET: {"finding_id": "F-1", "ops": [{"attr": "default_encryption", "op": "set_attr", "value": true}], "rationale_ref": "dpdp.rule6a", "resource_ref": "BUCKET_1"}

## 45. ex-002613 (val) rule cis.sg_open_ingress
mutators: ['m_sg_world_open']  variants: ['wide_v4']
INPUT : {"fields": {"fromport": 0, "ip_range": "0.0.0.0/0", "protocol": "tcp", "resource_type": "AWSIpPermissionInbound", "toport": 65535}, "finding_id": "F-0", "resource_id": "RESOURCE_1", "resource_ref": "RESOURCE_1", "rule_id": "cis.sg_open_ingress"}
TARGET: {"finding_id": "F-0", "ops": [{"attr": "ip_range", "op": "restrict_cidr", "value": "INTERNAL_CIDR"}], "rationale_ref": "cis.sg_open_ingress", "resource_ref": "RESOURCE_1"}

## 46. ex-000313 (train) rule dpdp.rule6_account_mfa
mutators: ['m_account_mfa_off']  variants: ['false']
INPUT : {"fields": {"account_mfa_enabled": false, "resource_type": "AWSAccount"}, "finding_id": "F-0", "resource_id": "RESOURCE_1", "resource_ref": "RESOURCE_1", "rule_id": "dpdp.rule6_account_mfa"}
TARGET: {"finding_id": "F-0", "ops": [{"op": "escalate", "reason": "Enabling account-level MFA is a human action and cannot be expressed as a Terraform change."}], "rationale_ref": "dpdp.rule6_account_mfa", "resource_ref": "RESOURCE_1"}

## 47. ex-002962 (B1) rule cis.s3_public_access_block
mutators: ['m_s3_public_block_off', 'm_s3_sse_algo']  variants: ['missing', 'kms_legacy']
INPUT : {"fields": {"resource_type": "AWSS3Bucket"}, "finding_id": "F-0", "resource_id": "BUCKET_1", "resource_ref": "BUCKET_1", "rule_id": "cis.s3_public_access_block"}
TARGET: {"finding_id": "F-0", "ops": [{"attr": "block_public_acls", "op": "set_attr", "value": true}, {"attr": "block_public_policy", "op": "set_attr", "value": true}, {"attr": "ignore_public_acls", "op": "set_attr", "value": true}, {"attr": "restrict_public_buckets", "op": "set_attr", "value": true}], "rationale_ref": "cis.s3_public_access_block", "resource_ref": "BUCKET_1"}

## 48. ex-001395 (train) rule dpdp.rule6_public_exposure
mutators: ['m_s3_public_block_off']  variants: ['one_ignore']
INPUT : {"fields": {"block_public_acls": true, "block_public_policy": true, "ignore_public_acls": false, "resource_type": "AWSS3Bucket", "restrict_public_buckets": true}, "finding_id": "F-1", "resource_id": "BUCKET_1", "resource_ref": "BUCKET_1", "rule_id": "dpdp.rule6_public_exposure"}
TARGET: {"finding_id": "F-1", "ops": [{"attr": "ignore_public_acls", "op": "set_attr", "value": true}], "rationale_ref": "dpdp.rule6_public_exposure", "resource_ref": "BUCKET_1"}

## 49. ex-000368 (train) rule dpdp.rule6_sg_open_ingress
mutators: ['m_sg_world_open']  variants: ['all_traffic_v4']
INPUT : {"fields": {"fromport": 0, "ip_range": "0.0.0.0/0", "protocol": "-1", "resource_type": "AWSIpPermissionInbound", "toport": 0}, "finding_id": "F-1", "resource_id": "RESOURCE_1", "resource_ref": "RESOURCE_1", "rule_id": "dpdp.rule6_sg_open_ingress"}
TARGET: {"finding_id": "F-1", "ops": [{"attr": "ip_range", "op": "restrict_cidr", "value": "INTERNAL_CIDR"}], "rationale_ref": "dpdp.rule6_sg_open_ingress", "resource_ref": "RESOURCE_1"}

## 50. ex-002284 (train) rule cis.sg_open_ingress
mutators: ['m_sg_world_open']  variants: ['mysql_v6']
INPUT : {"fields": {"fromport": 3306, "ip_range": "::/0", "protocol": "tcp", "resource_type": "AWSIpPermissionInbound", "toport": 3306}, "finding_id": "F-0", "resource_id": "RESOURCE_1", "resource_ref": "RESOURCE_1", "rule_id": "cis.sg_open_ingress"}
TARGET: {"finding_id": "F-0", "ops": [{"attr": "ip_range", "op": "restrict_cidr", "value": "INTERNAL_CIDR"}], "rationale_ref": "cis.sg_open_ingress", "resource_ref": "RESOURCE_1"}

