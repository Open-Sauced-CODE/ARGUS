"""
Tests for Phase 5 Sections 2C-3 tools: T0 templates, prompt format, SFT preparation, scoring, statistics, Modelfile writer.
Need OPA (skipped if not found).

    python -m pytest ml/tests/test_phase5_train_tools.py -v
"""

import json
import os
import shutil

import pytest

from ml.mutation_engine import build_dataset
from ml.mutation_engine.dataset_io import read_jsonl
from ml.mutation_engine.qa.gate_stub import gate_many
from ml.tests.qa_fixtures import write_bases
from ml.train_m1 import prepare_sft
from ml.train_m1.eval.score import score_inputs
from ml.train_m1.prompt import patch_json
from ml.train_m1.serve.make_modelfile import build_modelfile
from ml.train_m1.stats import cohen_kappa, mcnemar_exact, wilson
from remediate.templates import T0_RULES, match

pytestmark = pytest.mark.skipif(not (os.environ.get("OPA_BIN") or shutil.which("opa")), reason="OPA not found")

ARGS = ["--seed", "3", "--train", "150", "--val", "30", "--b1", "30", "--b2", "20", "--min-per-mutator", "4",
        "--min-per-mutator-val", "1", "--min-per-mutator-b2", "4"]


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("ds")
    bases = write_bases(tmp / "bases")
    assert build_dataset.main(ARGS + ["--bases-dir", str(bases), "--out", str(tmp / "out")]) == 0
    return tmp / "out"


def test_templates_pass_the_gate_on_every_t0_example(built):
    rows = [e for e in read_jsonl(built / "dataset" / "train.jsonl") if e["rule_id"] in T0_RULES]
    assert rows
    cases = []
    for ex in rows:
        patch = match(ex["input"])
        assert patch is not None, ex["id"]
        cases.append((ex["input"], patch))
    assert all(r.passed and r.outcome == "fixed" for r in gate_many(cases))


def test_templates_return_none_for_other_rules_and_clean_findings():
    assert match({"finding_id": "F", "rule_id": "cis.iam_no_full_admin", "resource_ref": "RESOURCE_1", "fields": {}}) is None
    clean = {"finding_id": "F", "rule_id": "dpdp.rule6_logging", "resource_ref": "BUCKET_1", "fields": {"logging_enabled": True}}
    assert match(clean) is None


def test_reference_answers_score_as_correct(built):
    rows = read_jsonl(built / "dataset" / "val.jsonl")[:25]
    items = [{"record": e["input"], "route": e["meta"]["route"], "reference": e["target"], "contents": [json.dumps(e["target"])]} for e in rows]
    results = score_inputs(items)
    assert all(r["pass_at"][1] for r in results)
    assert all(r["candidates"][0]["hidden_ok"] for r in results)
    bad = [{"record": rows[0]["input"], "route": rows[0]["meta"]["route"], "reference": rows[0]["target"], "contents": ["not json", "{}"]}]
    assert score_inputs(bad)[0]["pass_at"] == {1: False, 2: False}


def test_patch_json_follows_schema_order_and_prepare_sft_guard(built, tmp_path):
    text = patch_json({"rationale_ref": "r", "ops": [{"value": 1, "attr": "a", "op": "set_attr"}], "resource_ref": "B_1", "finding_id": "F"})
    assert text.index("finding_id") < text.index("resource_ref") < text.index("ops") < text.index("rationale_ref")
    assert text.index('"op"') < text.index('"attr"') < text.index('"value"')
    out = tmp_path / "data"
    code = prepare_sft.main(["--dataset-dir", str(built / "dataset"), "--held-out", str(built / "held_out"), "--out", str(out)])
    assert code == 0 and (out / "sft_train.jsonl").exists() and (out / "val_distinct.jsonl").exists()
    leaky = tmp_path / "held"
    leaky.mkdir()
    first = read_jsonl(built / "dataset" / "train.jsonl")[0]["meta"]["full_hash"]
    (leaky / "held_out_hashes.txt").write_text(first + "\n")
    assert prepare_sft.main(["--dataset-dir", str(built / "dataset"), "--held-out", str(leaky), "--out", str(tmp_path / "x")]) == 1


def test_statistics_and_modelfile():
    lo, hi = wilson(41, 60)
    assert 0.55 < lo < 0.68 < hi < 0.80
    assert mcnemar_exact(0, 0) == 1.0 and mcnemar_exact(10, 0) < 0.01 and abs(mcnemar_exact(5, 5) - 1.0) < 1e-9
    k, agree = cohen_kappa(list("yyny"), list("yyny"))
    assert k == 1.0 and agree == 1.0
    text = build_modelfile("# c\nFROM /a/blob\nFROM /b/mmproj\nTEMPLATE \"\"\"x\"\"\"\nPARAMETER stop <|im_end|>", "C:/m/x.gguf")
    assert text.count("FROM ") == 1 and "FROM C:/m/x.gguf" in text and "PARAMETER stop" in text
