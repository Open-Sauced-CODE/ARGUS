"""
Tests for ml/real_data/rego_runner.py and ml/real_data/buckets.py (Phase 5, Step 4).
The Rego tests need the OPA program (the same one you used for `opa test policy/`); they are skipped if it is not found.

Run from the repo root (PowerShell):
    python -m pytest ml/tests/test_rego_runner_and_buckets.py -v
"""

import os
import shutil
from collections import Counter

import pytest

from ml.real_data.buckets import bucket_number, bucket_of
from ml.real_data.rego_runner import discover_rules, evaluate, resource_for_rules
from privacy.airlock.projection import load_declarations

needs_opa = pytest.mark.skipif(
    not (os.environ.get("OPA_BIN") or shutil.which("opa")),
    reason="OPA not found (put opa on PATH or set OPA_BIN)",
)

CLEAN_BUCKET = {
    "resource_type": "AWSS3Bucket", "default_encryption": True, "encryption_algorithm": "aws:kms",
    "block_public_acls": True, "block_public_policy": True, "ignore_public_acls": True,
    "restrict_public_buckets": True, "logging_enabled": True, "has_lifecycle_expiration": False,
}


def test_every_rego_rule_file_is_discovered():
    discovered = {rule_id for rule_id, _pkg, _kinds in discover_rules()}
    assert discovered == set(load_declarations())


@needs_opa
def test_results_match_the_rego_rules_and_stay_aligned_with_the_input():
    resources = [
        dict(CLEAN_BUCKET, default_encryption=False),
        CLEAN_BUCKET,
        {"resource_type": "AWSIpPermissionInbound", "ip_range": "0.0.0.0/0", "protocol": "tcp", "fromport": 22, "toport": 22},
        {"resource_type": "AWSIpPermissionInbound", "ip_range": "0.0.0.0/0", "protocol": "tcp", "fromport": 443, "toport": 443},
        {"resource_type": "AWSPolicyStatement", "effect": "Allow", "action": ["*"], "resource": ["*"]},
        {"resource_type": "AWSRDSInstance", "storage_encrypted": False},
        {"personal_data": True, "region": "us-east-1", "approved_regions": ["ap-south-1"]},
    ]
    r = evaluate(resources)
    assert r[0].deny == {"dpdp.rule6a", "cis.s3_default_encryption"}
    assert r[1].clean
    assert r[2].deny == {"dpdp.rule6_sg_open_ingress", "cis.sg_open_ingress"}
    assert r[3].clean
    assert r[4].deny == {"cis.iam_no_full_admin"}
    assert r[5].deny == {"dpdp.rule6a_rds"}
    assert r[6].warn == {"dpdp.rule15_region"} and not r[6].deny


@needs_opa
def test_chunking_gives_the_same_answer_and_empty_input_is_fine():
    resources = [dict(CLEAN_BUCKET, logging_enabled=bool(i % 2)) for i in range(7)]
    assert evaluate(resources, chunk=3) == evaluate(resources, chunk=100)
    assert [x.deny for x in evaluate(resources)] == [frozenset() if i % 2 else frozenset({"dpdp.rule6_logging"}) for i in range(7)]
    assert evaluate([]) == []


def test_resource_for_rules_adds_the_resource_type():
    rec = {"resource_type": "AWSRDSInstance", "attrs": {"storage_encrypted": True}}
    assert resource_for_rules(rec) == {"storage_encrypted": True, "resource_type": "AWSRDSInstance"}


def test_bucket_boundaries_and_distribution():
    counts = Counter(bucket_of("owner/repo{}".format(i)) for i in range(20000))
    assert 0.66 < counts["train"] / 20000 < 0.74
    assert 0.08 < counts["val"] / 20000 < 0.12
    assert 0.17 < counts["test"] / 20000 < 0.23
    for i in range(300):
        n = bucket_number("x/y{}".format(i))
        expected = "train" if n <= 69 else "val" if n <= 79 else "test"
        assert bucket_of("x/y{}".format(i)) == expected


def test_bucket_is_stable_case_insensitive_and_reserved_repos_are_never_train():
    assert bucket_of("Owner/Repo") == bucket_of("owner/repo") == bucket_of("  owner/repo ")
    assert bucket_of("RhinoSecurityLabs/cloudgoat") == "reserved"
    assert bucket_of("bridgecrewio/TerraGoat") == "reserved"
    assert bucket_of("some/fork-of-terragoat-demo") == "reserved"
