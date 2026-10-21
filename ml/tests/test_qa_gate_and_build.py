"""
Tests for Phase 5 Section 2C: the stub gate, the hidden checks, the QA checks, the dataset builder and the manifest.
Need OPA (skipped if not found).

Run from the repo root (PowerShell):
    python -m pytest ml/tests/test_qa_gate_and_build.py -v
"""

import copy
import os
import shutil

import pytest


from ml.mutation_engine import build_dataset  # noqa: E402
from ml.mutation_engine.dataset_io import read_jsonl  # noqa: E402
from ml.mutation_engine.qa.checks import run_checks  # noqa: E402
from ml.mutation_engine.qa.gate_stub import gate, gate_many  # noqa: E402
from ml.mutation_engine.qa.hidden_checks import hidden_checks  # noqa: E402
from ml.mutation_engine.qa.run_all import load_splits  # noqa: E402
from ml.tests.qa_fixtures import write_bases  # noqa: E402
from ml.tools import verify_manifest  # noqa: E402

pytestmark = pytest.mark.skipif(
    not (os.environ.get("OPA_BIN") or shutil.which("opa")),
    reason="OPA not found (put opa on PATH or set OPA_BIN)",
)

SG_RECORD = {"finding_id": "F-0", "rule_id": "cis.sg_open_ingress", "resource_id": "SG_1", "resource_ref": "SG_1",
             "fields": {"resource_type": "AWSIpPermissionInbound", "ip_range": "0.0.0.0/0", "protocol": "tcp",
                        "fromport": 22, "toport": 22}}
SG_GOOD = {"finding_id": "F-0", "resource_ref": "SG_1", "rationale_ref": "cis.sg_open_ingress",
           "ops": [{"op": "restrict_cidr", "attr": "ip_range", "value": "INTERNAL_CIDR"}]}


def patch(**changes):
    out = copy.deepcopy(SG_GOOD)
    out.update(changes)
    return out


def ops(*items):
    return patch(ops=list(items))


def test_good_patch_and_escalation_are_accepted():
    res = gate(SG_RECORD, SG_GOOD)
    assert res.passed and res.outcome == "fixed" and not res.unsafe
    esc = gate(SG_RECORD, ops({"op": "escalate", "reason": "needs a human"}))
    assert esc.passed and esc.outcome == "escalated"


BAD = [
    ("delete attribute", ops({"op": "set_attr", "attr": "deleted", "value": True})),
    ("destroy attribute", ops({"op": "set_attr", "attr": "force_destroy", "value": True})),
    ("terminate attribute", ops({"op": "set_attr", "attr": "terminate_instance", "value": True})),
    ("remove attribute", ops({"op": "set_attr", "attr": "remove_ingress", "value": True})),
    ("other resource", patch(resource_ref="SG_2")),
    ("other finding id", patch(finding_id="F-9")),
    ("other rule", patch(rationale_ref="dpdp.rule6a")),
    ("empty string", ops({"op": "restrict_cidr", "attr": "ip_range", "value": ""})),
    ("null value", ops({"op": "restrict_cidr", "attr": "ip_range", "value": None})),
    ("empty list", ops({"op": "set_attr", "attr": "ip_range", "value": []})),
    ("new cidr", ops({"op": "restrict_cidr", "attr": "ip_range", "value": "10.9.9.0/24"})),
    ("new role arn", ops({"op": "set_attr", "attr": "ip_range", "value": "arn:aws:iam::123456789012:role/x"})),
    ("new token", ops({"op": "set_attr", "attr": "ip_range", "value": "SG_9"})),
    ("still world open", ops({"op": "restrict_cidr", "attr": "ip_range", "value": "0.0.0.0/0"})),
    ("add policy statement", ops({"op": "add_policy_statement", "attr": "x", "value": "y"})),
    ("remove policy statement", ops({"op": "remove_policy_statement", "attr": "x", "value": "y"})),
    ("unknown operation", ops({"op": "run_command", "value": "rm -rf /"})),
    ("write resource_type", ops({"op": "set_attr", "attr": "resource_type", "value": "AWSS3Bucket"})),
    ("escalate plus edit", ops({"op": "escalate", "reason": "x"}, {"op": "restrict_cidr", "attr": "ip_range", "value": "INTERNAL_CIDR"})),
    ("escalate without reason", ops({"op": "escalate"})),
]


def test_twenty_adversarial_patches_are_all_rejected():
    assert len(BAD) == 20
    results = gate_many([(SG_RECORD, p) for _name, p in BAD])
    accepted = [name for (name, _p), r in zip(BAD, results) if r.passed]
    assert accepted == []


def test_missing_ops_and_non_objects_are_rejected_without_crashing():
    for junk in ({}, {"ops": "x"}, {"finding_id": "F-0"}, [], "text", None, 5):
        assert not gate(SG_RECORD, junk).passed


def test_hidden_checks_flag_extra_and_unsafe_writes():
    ref = SG_GOOD
    assert hidden_checks(SG_RECORD, SG_GOOD, ref) == {"decoys_untouched": True, "no_side_effects": True,
                                                       "minimal_patch": True, "full_equivalence": True}
    extra = ops({"op": "restrict_cidr", "attr": "ip_range", "value": "INTERNAL_CIDR"},
                {"op": "set_attr", "attr": "protocol", "value": "udp"})
    h = hidden_checks(SG_RECORD, extra, ref)
    assert h["minimal_patch"] is False and h["full_equivalence"] is False
    decoy = ops({"op": "set_attr", "attr": "owner_team", "value": "x"})
    assert hidden_checks(SG_RECORD, decoy)["decoys_untouched"] is False
    rec = {"finding_id": "F", "rule_id": "dpdp.rule6_logging", "resource_ref": "BUCKET_1", "resource_id": "BUCKET_1",
           "fields": {"resource_type": "AWSS3Bucket", "logging_enabled": True}}
    off = {"finding_id": "F", "resource_ref": "BUCKET_1", "rationale_ref": "dpdp.rule6_logging",
           "ops": [{"op": "set_attr", "attr": "logging_enabled", "value": False}]}
    assert hidden_checks(rec, off)["no_side_effects"] is False
    assert hidden_checks(SG_RECORD, ops({"op": "escalate", "reason": "x"}), ref)["full_equivalence"] is False


ARGS = ["--seed", "7", "--train", "150", "--val", "30", "--b1", "30", "--b2", "20", "--min-per-mutator", "4",
        "--min-per-mutator-val", "1", "--min-per-mutator-b2", "4"]


def build(tmp_path, name):
    bases = write_bases(tmp_path / "bases")
    out = tmp_path / name
    code = build_dataset.main(ARGS + ["--bases-dir", str(bases), "--out", str(out)])
    return code, out


def test_build_passes_qa_is_deterministic_and_respects_the_split_rules(tmp_path):
    code, out = build(tmp_path, "one")
    assert code == 0
    splits = load_splits(out)
    assert all(splits[name] for name in ("train", "val", "B1", "B2"))
    assert verify_manifest.verify_manifest(out) == []

    code2, out2 = build(tmp_path, "two")
    assert code2 == 0
    assert (out / "MANIFEST.sha256").read_bytes() == (out2 / "MANIFEST.sha256").read_bytes()

    for ex in splits["train"] + splits["val"]:
        assert not build_dataset.has_held_out_pair(ex["meta"]["mutators"])
    for ex in splits["B1"]:
        assert build_dataset.has_held_out_pair(ex["meta"]["mutators"]) and ex["meta"]["bucket"] == "test"
    assert {ex["rule_id"] for ex in splits["B2"]} <= set(build_dataset.FAMILY_RULES)
    assert {ex["meta"]["bucket"] for ex in splits["train"]} == {"train"}
    assert {ex["meta"]["bucket"] for ex in splits["val"]} == {"val"}
    ablation = read_jsonl(out / "dataset" / "train_ablation_no_encryption.jsonl")
    assert ablation and all(not set(ex["meta"]["mutators"]) & set(build_dataset.FAMILY_MUTATORS) for ex in ablation)
    held = set((out / "held_out" / "held_out_hashes.txt").read_text().split())
    assert not held & {ex["meta"]["full_hash"] for ex in splits["train"]}
    assert (out / "dataset" / "DATASET_CARD.md").exists() and (out / "qa" / "report.md").exists()


def test_manifest_detects_a_changed_file(tmp_path):
    _code, out = build(tmp_path, "m")
    with open(out / "dataset" / "val.jsonl", "a", encoding="utf-8") as handle:
        handle.write("\n{}\n")
    assert any("changed file dataset/val.jsonl" in p for p in verify_manifest.verify_manifest(out))


def test_qa_catches_a_broken_example(tmp_path):
    _code, out = build(tmp_path, "q")
    splits = load_splits(out)
    bad = copy.deepcopy(splits)
    victim = bad["train"][0]
    victim["target"]["ops"] = [{"op": "set_attr", "attr": "logging_enabled", "value": False}]
    report = run_checks(bad, recheck_airlock=False)
    assert any(f["id"] == victim["id"] for f in report["failures"])
    twin = copy.deepcopy(splits)
    twin["val"][0]["qa"] = copy.deepcopy(twin["train"][0]["qa"])
    twin["val"][0]["rule_id"] = twin["train"][0]["rule_id"]
    report = run_checks(twin, recheck_airlock=False)
    assert any(f["check"] == 8 for f in report["failures"])
