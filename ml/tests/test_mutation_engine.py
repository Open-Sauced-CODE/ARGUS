"""
Tests for the Phase 5 mutation engine (Steps 5 to 7): mutators, composition, decoys, labeler, synthetic bases and
the byte-for-byte link to the Phase 4 airlock. Needs OPA (skipped if not found).

Run from the repo root (PowerShell):
    python -m pytest ml/tests/test_mutation_engine.py -v
"""

import json
import os
import random
import re
import shutil
from pathlib import Path

import pytest

pytest.importorskip("hcl2", reason="python-hcl2 is not installed (pip install -r requirements-phase5.txt)")

from ml.mutation_engine import coverage, synth_bases  # noqa: E402
from ml.mutation_engine.compose import compose, conflicts, load_violation_counts, mutator_weights  # noqa: E402
from ml.mutation_engine.decoys import decoy_extras, decoys_untouched  # noqa: E402
from ml.mutation_engine.examples import build_from_base, resource_from_plain  # noqa: E402
from ml.mutation_engine.labeler import LabelError, label, schema_errors  # noqa: E402
from ml.mutation_engine.model import MISSING, Resource, apply_patch, diff_attrs  # noqa: E402
from ml.mutation_engine.mutators import ALL_MUTATORS, BY_ID, rules_covered, variant_count  # noqa: E402
from ml.mutation_engine.project import raw_finding, throwaway_vault  # noqa: E402
from ml.real_data.rego_runner import evaluate, resource_for_rules  # noqa: E402
from ml.real_data.tf_normalise import norm_hash  # noqa: E402
from privacy.airlock.airlock import run_airlock  # noqa: E402
from privacy.airlock.projection import REPO_ROOT, load_declarations  # noqa: E402

pytestmark = pytest.mark.skipif(
    not (os.environ.get("OPA_BIN") or shutil.which("opa")),
    reason="OPA not found (put opa on PATH or set OPA_BIN)",
)


def make_base(rtype, attrs, extras=None, bucket="train"):
    h = norm_hash(rtype, attrs, extras or {})
    return {"base_id": "b-" + h[:12], "resource_type": rtype, "attrs": attrs, "extras": extras or {}, "norm_hash": h,
            "source": {"repo_id": 1, "repo": "o/r", "commit": "c", "license": "MIT", "file": "main.tf",
                       "tf_type": "x", "tf_name": "y", "bucket": bucket}}


S3_ATTRS = {"default_encryption": True, "encryption_algorithm": "AES256", "block_public_acls": True,
            "block_public_policy": True, "ignore_public_acls": True, "restrict_public_buckets": True,
            "logging_enabled": True, "has_lifecycle_expiration": True}
BASES = [
    make_base("AWSS3Bucket", dict(S3_ATTRS, personal_data=True, versioning_status="Enabled"), {"force_destroy": True}),
    make_base("AWSS3Bucket", dict(S3_ATTRS, has_lifecycle_expiration=False, encryption_algorithm="aws:kms:dsse")),
    make_base("AWSIpPermissionInbound", {"ip_range": "10.0.0.0/16", "protocol": "tcp", "fromport": 22, "toport": 22}),
    make_base("AWSIpPermissionInbound", {"ip_range": "10.1.0.0/16", "protocol": "tcp", "fromport": 443, "toport": 443}),
    make_base("AWSIpPermissionInbound", {"ip_range": "0.0.0.0/0", "protocol": "tcp", "fromport": 443, "toport": 443}),
    make_base("AWSPolicyStatement", {"effect": "Allow", "action": ["s3:GetObject", "s3:ListBucket"],
                                     "resource": ["arn:aws:s3:::acme-data", "arn:aws:s3:::acme-data/*"]}),
    make_base("AWSPolicyStatement", {"effect": "Allow", "action": ["ec2:Describe*"], "resource": ["*"]}),
    make_base("AWSRDSInstance", {"storage_encrypted": True}, {"engine": "mysql", "allocated_storage": 20}),
    synth_bases.account_fixtures(1)[0],
]


def results_for(resources):
    return evaluate([resource_for_rules(r) if hasattr(r, "attrs") else r for r in resources])


def resources(res_list):
    return [r.rule_view() for r in res_list]


def test_fixture_bases_are_clean():
    assert all(v.clean for v in evaluate([resource_for_rules(b) for b in BASES]))


def test_registry_matches_the_contracts_table_and_the_rego_rules():
    text = (REPO_ROOT / "ml" / "README_contracts.md").read_text(encoding="utf-8-sig")
    table = text.split("| Rule ID |", 1)[1].split("Totals:", 1)[0]
    assert set(re.findall(r"`(m_[a-z0-9_]+)`", table)) == {m.mutator_id for m in ALL_MUTATORS}
    assert set(rules_covered()) == set(load_declarations())
    assert len(ALL_MUTATORS) == 12 and variant_count() == 43


ALL_VARIANTS = [(m.mutator_id, v) for m in ALL_MUTATORS for v in m.variants]


@pytest.mark.parametrize("mutator_id,variant", ALL_VARIANTS, ids=["{}:{}".format(*p) for p in ALL_VARIANTS])
def test_each_variant_fires_exactly_its_declared_rules_and_its_patch_undoes_it(mutator_id, variant):
    mutator = BY_ID[mutator_id]
    pairs = []
    for base in BASES:
        res = Resource.from_base(base)
        clean = mutator.prepare(res, variant) if res.resource_type in mutator.resource_types else None
        if clean is not None:
            pairs.append((clean, mutator.mutate(clean, variant)))
    assert pairs, "no fixture base exercises {}:{}".format(mutator_id, variant)
    verdicts = results_for([c.rule_view() for c, _ in pairs] + [b.rule_view() for _, (b, _m) in pairs])
    n = len(pairs)
    for i, (clean, (broken, mutation)) in enumerate(pairs):
        assert verdicts[i].clean, "canonical original is not clean"
        fired = verdicts[n + i].deny | verdicts[n + i].warn
        assert fired == set(mutation.rules_fired) == set(mutator.rules_for(variant))
        assert set(diff_attrs(clean, broken)) == set(mutation.paths)
        rule = mutation.rules_fired[0]
        patch = label(clean, broken, [mutation], rule, "F-1", "BUCKET_1")
        assert schema_errors(patch) == []
        fixed = apply_patch(broken, patch)
        if mutation.route == "fix":
            assert fixed.attrs == clean.attrs
            assert results_for([fixed.rule_view()])[0].clean
        else:
            assert [op["op"] for op in patch["ops"]] == ["escalate"] and patch["ops"][0]["reason"]
            assert fixed.attrs == broken.attrs


def test_random_composition_fires_exactly_the_declared_violations_and_decoys_change_nothing():
    rng = random.Random(7)
    cleans, brokens, declared, multi = [], [], [], 0
    for _ in range(200):
        base = rng.choice(BASES)
        out = compose(Resource.from_base(base), rng, rng.randint(1, 4))
        if out is None:
            continue
        clean, broken, mutations = out
        extras, _names = decoy_extras(clean.extras, rng)
        clean.extras, broken.extras = dict(extras), dict(extras)
        assert decoys_untouched(Resource(clean.resource_type, clean.attrs), Resource(clean.resource_type, dict(clean.attrs), extras))
        cleans.append(clean)
        brokens.append(broken)
        declared.append({r for m in mutations for r in m.rules_fired})
        multi += len(mutations) > 1
    assert len(cleans) > 150 and multi > 20
    verdicts = results_for(resources(cleans) + resources(brokens))
    n = len(cleans)
    for i in range(n):
        assert verdicts[i].clean
        assert (verdicts[n + i].deny | verdicts[n + i].warn) == declared[i]


def test_composed_mutators_never_share_an_attribute_or_a_rule():
    rng = random.Random(3)
    for base in BASES:
        out = compose(Resource.from_base(base), rng, 4)
        if out is None:
            continue
        _clean, _broken, mutations = out
        paths = [p for m in mutations for p in m.paths]
        rules = [r for m in mutations for r in m.rules_fired]
        assert len(paths) == len(set(paths)) and len(rules) == len(set(rules))
    assert conflicts((BY_ID["m_s3_sse_off"], "clear"), (BY_ID["m_s3_sse_algo"], "none"))
    assert not conflicts((BY_ID["m_s3_versioning_off"], "suspended"), (BY_ID["m_s3_lifecycle_off"], "false"))


def test_labeler_rejects_an_undeclared_change_or_an_unknown_rule():
    res = Resource.from_base(BASES[0])
    clean = BY_ID["m_s3_logging_off"].prepare(res, "false")
    broken, mutation = BY_ID["m_s3_logging_off"].mutate(clean, "false")
    broken.attrs["default_encryption"] = False  # a change no mutator declared
    with pytest.raises(LabelError):
        label(clean, broken, [mutation], "dpdp.rule6_logging", "F-1", "BUCKET_1")
    broken2, mutation2 = BY_ID["m_s3_logging_off"].mutate(clean, "false")
    with pytest.raises(LabelError):
        label(clean, broken2, [mutation2], "dpdp.rule6a", "F-1", "BUCKET_1")


def test_examples_are_deterministic_and_seeds_differ():
    def run(seed):
        out = []
        with throwaway_vault() as vault:
            for base in BASES:
                out.extend(build_from_base(base, random.Random(seed), 2, vault, "F"))
        return json.dumps(out, sort_keys=True)

    assert run(5) == run(5)
    assert len({run(s) for s in range(6)}) > 1


def test_inputs_are_byte_identical_to_the_deployed_airlock_and_targets_use_the_same_tokens():
    rng = random.Random(11)
    token_re = re.compile(r"\b[A-Z]+(?:_[A-Z]+)*_\d+\b")
    checked = 0
    with throwaway_vault() as vault:
        for _ in range(60):
            base = rng.choice(BASES)
            for ex in build_from_base(base, rng, rng.randint(1, 3), vault, "F"):
                plain = ex["qa"]["mutated"]
                with throwaway_vault() as fresh:
                    raw = raw_finding(resource_from_plain(plain), ex["input"]["finding_id"], "tf-" + base["base_id"])
                    again, _receipt = run_airlock(raw, ex["rule_id"], vault=fresh)
                assert json.dumps(again, sort_keys=True) == json.dumps(ex["input"], sort_keys=True)
                text = json.dumps(ex["input"])
                assert "tf-b-" not in text and "acme-data" not in text
                target_tokens = set(token_re.findall(json.dumps(ex["target"]["ops"])))
                assert target_tokens <= set(token_re.findall(text))
                assert ex["target"]["resource_ref"] == ex["input"]["resource_ref"]
                assert schema_errors(ex["target"]) == []
                assert set(ex["input"]["fields"]) <= load_declarations()[ex["rule_id"]]
                checked += 1
    assert checked > 60


def test_iam_example_keeps_legitimate_entries_visible_and_the_fix_restores_them():
    base = BASES[5]
    rng = random.Random(1)
    with throwaway_vault() as vault:
        examples = build_from_base(base, rng, 1, vault, "F", mutators=[BY_ID["m_iam_full_admin"]])
    (ex,) = examples
    assert "*" in ex["input"]["fields"]["action"] and "arn:aws:s3:::BUCKET_1" in ex["input"]["fields"]["resource"]
    ops = {op["attr"]: op["value"] for op in ex["target"]["ops"]}
    assert ops["action"] == ["s3:GetObject", "s3:ListBucket"]
    assert ops["resource"] == ["arn:aws:s3:::BUCKET_1", "arn:aws:s3:::BUCKET_1/*"]


def test_violation_counts_weight_the_mutators(tmp_path):
    path = tmp_path / "violation_counts_train.csv"
    path.write_text("rule_id,violating_records_in_train_repos\ncis.iam_no_full_admin,900\ndpdp.rule6_logging,100\n", encoding="utf-8")
    weights = mutator_weights(load_violation_counts(path))
    assert weights["m_iam_full_admin"] > weights["m_s3_logging_off"] > weights["m_account_mfa_off"] > 0
    assert load_violation_counts(tmp_path / "missing.csv") == {}


def test_synthetic_bases_are_clean_inherit_buckets_and_never_repeat_a_shape(tmp_path):
    real = [b for b in BASES if b["resource_type"] == "AWSS3Bucket"][1:2]
    real[0]["source"]["bucket"] = "test"
    (tmp_path / "bases.jsonl").write_text("".join(json.dumps(b) + "\n" for b in real), encoding="utf-8")
    synthetic = synth_bases.build(tmp_path)
    s3 = [b for b in synthetic if b["resource_type"] == "AWSS3Bucket"]
    accounts = [b for b in synthetic if b["resource_type"] == "AWSAccount"]
    assert len(s3) in (8, 9) and len(accounts) == 40
    assert all(b["source"]["bucket"] == "test" and b["source"]["derived_from"] == real[0]["base_id"] for b in s3)
    assert all(b["source"]["synthetic"] in ("completed_s3", "account") for b in synthetic)
    hashes = [b["norm_hash"] for b in real + synthetic]
    assert len(hashes) == len(set(hashes))
    assert all(v.clean for v in evaluate([resource_for_rules(b) for b in synthetic]))
    assert {b["attrs"].get("personal_data") for b in s3} == {True, None}
    assert len(synth_bases.load_all_bases(tmp_path)) == len(real) + len(synthetic)
    assert (tmp_path / "manifest_synthetic.csv").exists()


def test_synthetic_s3_fallback_when_no_real_bucket_exists(tmp_path):
    (tmp_path / "bases.jsonl").write_text("", encoding="utf-8")
    synthetic = synth_bases.build(tmp_path)
    # 5 distinct extras shapes x 9 compliant combinations; identical shapes are never repeated
    assert len([b for b in synthetic if b["resource_type"] == "AWSS3Bucket"]) == 45


def test_coverage_report_passes(capsys):
    assert coverage.main(["--bases-dir", str(Path("does-not-exist"))]) == 0
    assert "every rule has at least one mutator" in capsys.readouterr().out


def test_demo_prints_examples(tmp_path, capsys):
    from ml.mutation_engine import demo

    (tmp_path / "bases.jsonl").write_text("".join(json.dumps(b) + "\n" for b in BASES), encoding="utf-8")
    assert demo.main(["--bases-dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "MODEL INPUT" in out and "REFERENCE FIX" in out and "AWSS3Bucket" in out
    assert demo.main(["--bases-dir", str(tmp_path / "empty")]) == 2
