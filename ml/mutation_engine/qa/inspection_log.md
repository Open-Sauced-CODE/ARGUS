# Hand inspection log

Date: 2026-10-21
Reviewer: Prabhav Tiwari (Role C)

| # | example id | verdict (ok / wrong / unclear) | note |
|---|---|---|---|
| 1 | ex-000488 | ok | Restrict open ::/0 ingress to INTERNAL_CIDR |
| 2 | ex-001309 | ok | Restrict open TCP range ::/0 to INTERNAL_CIDR |
| 3 | ex-002059 | ok | Restrict open MySQL port 3306 to INTERNAL_CIDR |
| 4 | ex-002097 | ok | Restrict open PostgreSQL port 5432 to INTERNAL_CIDR |
| 5 | ex-002651 | ok | Minimal fix: set block_public_acls to true |
| 6 | ex-000421 | ok | Minimal fix: set block_public_acls to true |
| 7 | ex-000915 | ok | Minimal fix: set block_public_acls to true |
| 8 | ex-002462 | ok | Minimal fix: remove wildcard from SSM action list |
| 9 | ex-002546 | ok | Escalate: GuardDuty/CloudTrail are new resources |
| 10 | ex-002280 | ok | Restrict open RDP port 3389 to INTERNAL_CIDR |
| 11 | ex-001723 | ok | Restrict open port range to INTERNAL_CIDR |
| 12 | ex-003209 | ok | Enable default encryption with aws:kms |
| 13 | ex-002346 | ok | Escalate: cross-region data migration required |
| 14 | ex-002244 | ok | Add lifecycle expiration rule for personal data |
| 15 | ex-002993 | ok | Escalate: account-level MFA requires human action |
| 16 | ex-003181 | ok | Escalate: existing RDS encryption requires snapshot/restore |
| 17 | ex-003147 | ok | Update legacy KMS algorithm to aws:kms |
| 18 | ex-002011 | ok | Narrow wildcard action and resource to original scope |
| 19 | ex-003077 | ok | Escalate: account-level MFA requires human action |
| 20 | ex-003167 | ok | Set encryption algorithm from NONE to aws:kms |
| 21 | ex-002403 | ok | Restrict open all-traffic ingress to INTERNAL_CIDR |
| 22 | ex-001807 | ok | Restrict open all-traffic ingress to INTERNAL_CIDR |
| 23 | ex-000983 | ok | Minimal fix: set restrict_public_buckets to true |
| 24 | ex-000011 | ok | Set all 4 S3 public access block flags to true |
| 25 | ex-002516 | ok | Upgrade AES128 encryption algorithm to aws:kms |
| 26 | ex-000331 | ok | Set all 4 S3 public access block flags to true |
| 27 | ex-000454 | ok | Minimal fix: set restrict_public_buckets to true |
| 28 | ex-001177 | ok | Narrow wildcard action and resource to original ELB scope |
| 29 | ex-000402 | ok | Restrict open SSH port 22 to INTERNAL_CIDR |
| 30 | ex-001842 | ok | Set all 4 S3 public access block flags to true |
| 31 | ex-000048 | ok | Minimal fix: set ignore_public_acls to true |
| 32 | ex-002807 | ok | Upgrade AES128 encryption algorithm to aws:kms |
| 33 | ex-002009 | ok | Set all 4 S3 public access block flags to true |
| 34 | ex-002783 | ok | Restrict full port range ingress to INTERNAL_CIDR |
| 35 | ex-001288 | ok | Escalate: CloudTrail/GuardDuty are new resources |
| 36 | ex-000862 | ok | Minimal fix: set restrict_public_buckets to true |
| 37 | ex-001628 | ok | Restrict full port range ::/0 to INTERNAL_CIDR |
| 38 | ex-001031 | ok | Restrict open PostgreSQL port 5432 to INTERNAL_CIDR |
| 39 | ex-001425 | ok | Restrict full port range ingress to INTERNAL_CIDR |
| 40 | ex-001461 | ok | Minimal fix: remove wildcard from autoscaling/EC2 actions |
| 41 | ex-003298 | ok | Enable default encryption with aws:kms |
| 42 | ex-001542 | ok | Restrict open PostgreSQL port 5432 to INTERNAL_CIDR |
| 43 | ex-003056 | ok | Enable S3 bucket server access logging |
| 44 | ex-002104 | ok | Minimal fix: enable default encryption (algorithm already set) |
| 45 | ex-002613 | ok | Restrict full port range ingress to INTERNAL_CIDR |
| 46 | ex-000313 | ok | Escalate: account-level MFA requires human action |
| 47 | ex-002962 | ok | Set all 4 S3 public access block flags to true |
| 48 | ex-001395 | ok | Minimal fix: set ignore_public_acls to true |
| 49 | ex-000368 | ok | Restrict open all-traffic ingress to INTERNAL_CIDR |
| 50 | ex-002284 | ok | Restrict open MySQL port 3306 to INTERNAL_CIDR |
