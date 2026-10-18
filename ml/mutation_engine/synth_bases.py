"""
ARGUS Phase 5, Step 5 (contracts D4 and D9) - documented synthetic bases.

Two kinds, both clearly marked in `source.synthetic` and written to their OWN files (the real corpus from Step 4 is
never modified):

  completed_s3  Real clean S3 buckets are rare in public Terraform. Each real clean bucket is "completed": its real
                harmless extras are kept, and the compliance fields are set to every compliant combination
                (3 encryption algorithms x personal-data / not x versioning). The new base inherits the bucket of
                its parent repository, so a shape from a train repository can never appear in test.
  account       Account-level facts (MFA, CloudTrail, GuardDuty) have no Terraform resource, so their bases are
                fixtures written here. Their bucket comes from the hash of their synthetic name.

Run from the repo root (PowerShell):
    python -m ml.mutation_engine.synth_bases
"""

import argparse
import copy
import csv
import json
import sys
from collections import Counter
from pathlib import Path

from ml.real_data.buckets import bucket_of
from ml.real_data.rego_runner import evaluate, resource_for_rules
from ml.real_data.tf_normalise import norm_hash

BASES_DIR = Path(__file__).resolve().parent / "bases"
ALGORITHMS = ("AES256", "aws:kms", "aws:kms:dsse")
ACCOUNT_COUNT = 40
FALLBACK_S3_PARENTS = 40
_FALLBACK_EXTRAS = [{}, {"force_destroy": True}, {"force_destroy": False}, {"acl": "private"}, {"object_lock_enabled": False}]


def _finish(rtype, attrs, extras, source):
    h = norm_hash(rtype, attrs, extras)
    return {"base_id": "b-" + h[:12], "resource_type": rtype, "attrs": attrs, "extras": extras, "source": source, "norm_hash": h}


def completed_s3(real_bases):
    parents = [b for b in real_bases if b["resource_type"] == "AWSS3Bucket"]
    if not parents:  # no real bucket at all: fall back to labelled fixture parents
        parents = []
        for i in range(FALLBACK_S3_PARENTS):
            name = "synthetic/s3-fixture-{}".format(i)
            parents.append({"base_id": "fixture-{}".format(i), "extras": copy.deepcopy(_FALLBACK_EXTRAS[i % len(_FALLBACK_EXTRAS)]),
                            "source": {"repo_id": 0, "repo": name, "commit": "synthetic", "license": "synthetic",
                                       "file": "-", "tf_type": "aws_s3_bucket", "tf_name": "fixture", "bucket": bucket_of(name)}})
    out = []
    for parent in sorted(parents, key=lambda b: b["base_id"]):
        for algorithm in ALGORITHMS:
            for personal, versioning in ((True, "Enabled"), (False, None), (False, "Enabled")):
                attrs = {"default_encryption": True, "encryption_algorithm": algorithm,
                         "block_public_acls": True, "block_public_policy": True, "ignore_public_acls": True,
                         "restrict_public_buckets": True, "logging_enabled": True,
                         "has_lifecycle_expiration": bool(personal)}
                if versioning:
                    attrs["versioning_status"] = versioning
                if personal:
                    attrs["personal_data"] = True
                source = dict(parent["source"], synthetic="completed_s3", derived_from=parent["base_id"])
                out.append(_finish("AWSS3Bucket", attrs, copy.deepcopy(parent.get("extras", {})), source))
    return out


def account_fixtures(count=ACCOUNT_COUNT):
    out = []
    for i in range(count):
        name = "synthetic/account-{}".format(i)
        attrs = {"account_mfa_enabled": True, "cloudtrail_enabled": True, "guardduty_enabled": True}
        source = {"repo_id": 0, "repo": name, "commit": "synthetic", "license": "synthetic", "file": "-",
                  "tf_type": "account", "tf_name": "account-{}".format(i), "bucket": bucket_of(name), "synthetic": "account"}
        out.append(_finish("AWSAccount", attrs, {"alias_index": i}, source))
    return out


def load_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_all_bases(bases_dir=BASES_DIR):
    """Real bases (Step 4) plus synthetic bases, in a fixed order."""
    bases_dir = Path(bases_dir)
    return load_jsonl(bases_dir / "bases.jsonl") + load_jsonl(bases_dir / "bases_synthetic.jsonl")


def build(bases_dir=BASES_DIR, policy_dir=None, opa=None):
    bases_dir = Path(bases_dir)
    real = load_jsonl(bases_dir / "bases.jsonl")
    seen = {b["norm_hash"]: b["source"]["bucket"] for b in real}
    synthetic = []
    for base in completed_s3(real) + account_fixtures():
        if base["norm_hash"] in seen:
            continue  # same shape already exists: never put one shape in two buckets
        seen[base["norm_hash"]] = base["source"]["bucket"]
        synthetic.append(base)
    verdicts = evaluate([resource_for_rules(b) for b in synthetic], policy_dir=policy_dir, opa=opa)
    dirty = [b["base_id"] for b, v in zip(synthetic, verdicts) if not v.clean]
    if dirty:
        raise SystemExit("INTERNAL ERROR: synthetic bases that violate a rule: {}".format(dirty[:5]))
    with open(bases_dir / "bases_synthetic.jsonl", "w", encoding="utf-8", newline="\n") as handle:
        for b in synthetic:
            handle.write(json.dumps(b, sort_keys=True, ensure_ascii=True) + "\n")
    with open(bases_dir / "manifest_synthetic.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["base_id", "resource_type", "bucket", "synthetic", "derived_from", "repo", "norm_hash"])
        for b in synthetic:
            writer.writerow([b["base_id"], b["resource_type"], b["source"]["bucket"], b["source"]["synthetic"],
                             b["source"].get("derived_from", ""), b["source"]["repo"], b["norm_hash"]])
    return synthetic


def main(argv=None):
    p = argparse.ArgumentParser(description="Write the documented synthetic bases (completed S3 buckets, account fixtures)")
    p.add_argument("--bases-dir", default=str(BASES_DIR))
    p.add_argument("--policy-dir", default=None)
    p.add_argument("--opa", default=None)
    o = p.parse_args(argv)
    synthetic = build(o.bases_dir, o.policy_dir, o.opa)
    counts = Counter((b["resource_type"], b["source"]["bucket"]) for b in synthetic)
    print("Synthetic bases written: {}".format(len(synthetic)))
    print("| resource type | train | val | test |")
    print("|---|---:|---:|---:|")
    for t in sorted({t for t, _ in counts}):
        print("| {} | {} | {} | {} |".format(t, *[counts[(t, k)] for k in ("train", "val", "test")]))
    print("Self-check passed: every synthetic base is clean under all rules; no shape sits in two buckets.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
