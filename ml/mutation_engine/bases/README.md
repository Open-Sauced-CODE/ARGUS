# Tier A bases (Phase 5, Step 4)

Written by `python -m ml.real_data.filter_terrads` (see its docstring). Do not edit these files by hand.

| File | What it is |
|---|---|
| `bases.jsonl` | One clean base per line. A base is a resource with ZERO violations under every Rego rule, de-duplicated. |
| `manifest.csv` | One row per base: base_id, resource_type, bucket, repo, commit, license, file, tf_type, tf_name, norm_hash. |
| `counts.csv` | Number of bases per resource type and bucket (train / val / test). |
| `repo_buckets.csv` | Every selected repository, its bucket (hash of the repository name), licence, commit, and how many bases it gave. |
| `funnel.json` | Every counter of the run, the skip reasons, and the Terraform resource types seen. |

A base line looks like:

    {"base_id": "b-1a2b3c4d5e6f", "resource_type": "AWSS3Bucket",
     "attrs":  {...every field a Rego rule reads, with the Rego field names...},
     "extras": {...harmless real attributes no rule reads; decoy material for Step 6...},
     "source": {"repo_id": 123, "repo": "owner/name", "commit": "...", "license": "MIT",
                "file": "path/main.tf", "tf_type": "aws_s3_bucket", "tf_name": "data", "bucket": "train"},
     "norm_hash": "<sha256 of resource_type + attrs + extras>"}

Real bucket names, tags, descriptions and every secret-like attribute are never stored.
Buckets: hash of the repository name mod 100; 0-69 train, 70-79 val, 80-99 test. CloudGoat and TerraGoat
repositories are "reserved" for the Phase 10 testbed and never feed train or validation.
