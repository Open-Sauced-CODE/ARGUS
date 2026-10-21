"""Helpers shared by the Phase 5 QA / training tests (not a test file itself)."""

import json
from pathlib import Path



S3 = {"default_encryption": True, "encryption_algorithm": "AES256", "block_public_acls": True,
      "block_public_policy": True, "ignore_public_acls": True, "restrict_public_buckets": True,
      "logging_enabled": True}


def make_base(rtype, attrs, extras=None, bucket="train", tag=""):
    from ml.mutation_engine.dataset_io import sha256_text, canon
    h = sha256_text(canon([rtype, attrs, extras or {}, tag]))
    return {"base_id": "b-" + h[:12], "resource_type": rtype, "attrs": attrs, "extras": extras or {}, "norm_hash": h,
            "source": {"repo_id": 1, "repo": "o/r", "commit": "c", "license": "MIT", "file": "main.tf",
                       "tf_type": "x", "tf_name": "y", "bucket": bucket}}


def tiny_bases():
    """A small clean base set with every resource type in every bucket (train, val, test)."""
    bases = []
    for bucket in ("train", "val", "test"):
        n = 6 if bucket == "train" else 3
        for i in range(n):
            algo = ("AES256", "aws:kms", "aws:kms:dsse")[i % 3]
            bases.append(make_base("AWSS3Bucket", dict(S3, encryption_algorithm=algo, personal_data=True,
                                                       versioning_status="Enabled", has_lifecycle_expiration=True),
                                   {"force_destroy": bool(i % 2)}, bucket, "p%d" % i))
            bases.append(make_base("AWSS3Bucket", dict(S3, encryption_algorithm=algo, has_lifecycle_expiration=False),
                                   {"force_destroy": bool(i % 2)}, bucket, "n%d" % i))
            port = (22, 443, 3306)[i % 3]
            bases.append(make_base("AWSIpPermissionInbound", {"ip_range": "10.%d.0.0/16" % i, "protocol": "tcp",
                                                              "fromport": port, "toport": port}, {}, bucket, "s%d" % i))
            bases.append(make_base("AWSPolicyStatement", {"effect": "Allow", "action": ["s3:GetObject", "s3:ListBucket"],
                                                          "resource": ["arn:aws:s3:::acme-data%d" % i, "arn:aws:s3:::acme-data%d/*" % i]},
                                   {}, bucket, "i%d" % i))
            bases.append(make_base("AWSPolicyStatement", {"effect": "Allow", "action": ["ec2:Describe*", "logs:PutLogEvents"][: 1 + i % 2],
                                                          "resource": ["*"]}, {}, bucket, "j%d" % i))
            bases.append(make_base("AWSRDSInstance", {"storage_encrypted": True},
                                   {"engine": "mysql", "allocated_storage": 20 + i}, bucket, "r%d" % i))
            bases.append(make_base("AWSAccount", {"account_mfa_enabled": True, "cloudtrail_enabled": True,
                                                  "guardduty_enabled": True}, {"alias_index": i}, bucket, "a%d" % i))
    return bases


def write_bases(folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / "bases.jsonl", "w", encoding="utf-8", newline="\n") as handle:
        for b in tiny_bases():
            handle.write(json.dumps(b, sort_keys=True) + "\n")
    return folder
