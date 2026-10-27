"""Tests for the pilot helpers (constructed examples) and a full pilot run against the fake server."""

import json

import pytest

from ml.train_m2.harvest import pilot
from ml.train_m2.harvest.paths import PATCH_IR_SCHEMA, SCHEMA_PATH
from ml.train_m2.harvest.tests.fake_ollama import FakeOllama, canned_content
from ml.train_m2.harvest.tests.test_run import SCHEMA, make_inputs, messages_fn


def answer(attr, finding="F-0"):
    return json.dumps({"finding_id": finding, "resource_ref": "R_1", "ops": [{"op": "set_attr", "attr": attr, "value": 1}], "rationale_ref": "r"})


def test_canonical_ignores_finding_id_and_key_order():
    a = answer("x", "F-0")
    b = json.dumps({"rationale_ref": "r", "ops": [{"value": 1, "attr": "x", "op": "set_attr"}], "resource_ref": "R_1", "finding_id": "F-9"})
    assert pilot.canonical_answer(a) == pilot.canonical_answer(b)
    assert pilot.canonical_answer(a) != pilot.canonical_answer(answer("y"))
    assert pilot.canonical_answer("not json").startswith("INVALID:")
    assert pilot.canonical_answer("[1]").startswith("INVALID:")


def test_distinct_and_mean_distinct():
    assert pilot.distinct_count([answer("x"), answer("x", "F-1"), answer("y")]) == 2
    by_input = {"k1": {0: answer("x"), 1: answer("x")}, "k2": {0: answer("x"), 1: answer("y"), 2: "bad"}}
    assert pilot.mean_distinct(by_input) == pytest.approx((1 + 3) / 2)
    assert pilot.mean_distinct({}) == 0.0


def test_match_rates_on_constructed_examples():
    old = {"k1": [answer("x")] * 3, "k2": [answer("x"), answer("y"), answer("z")]}
    new = {"k1": {0: answer("x"), 1: answer("x", "F-7"), 2: answer("q")},   # exact, canonical-only, mismatch
           "k2": {0: answer("x"), 1: answer("y")}, "k3": {0: answer("x")}}  # k3 has no Phase 5 log
    r = pilot.match_rates(new, old)
    assert r["n_compared"] == 5 and r["inputs_without_phase5_log"] == 1
    assert r["exact_by_idx"] == {"0": 1.0, "1": 0.5, "2": 0.0}
    assert r["canonical_by_idx"] == {"0": 1.0, "1": 1.0, "2": 0.0}
    assert r["exact_overall"] == pytest.approx(0.6) and r["canonical_overall"] == pytest.approx(0.8)
    assert pilot.match_rates({}, old)["exact_overall"] is None


def test_schema_valid_share():
    schema = {"type": "object", "required": ["a"]}
    assert pilot.schema_valid_share(['{"a":1}', '{"b":1}', "nope", '{"a":2}'], schema) == 0.5
    assert pilot.schema_valid_share([], schema) == 0.0


def test_load_phase5_contents_reads_every_candidates_file(tmp_path):
    folder = tmp_path / "sft"
    folder.mkdir()
    (folder / "A_val.candidates.jsonl").write_text(json.dumps({"input_key": "k1", "contents": ["a"] * 8}) + "\n" + json.dumps({"input_key": "k2", "contents": ["b"] * 8}) + "\n")
    (folder / "B1.candidates.jsonl").write_text(json.dumps({"input_key": "k1", "contents": ["DIFFERENT"] * 8}) + "\n" + "\n")
    (folder / "ignored.txt").write_text("x")
    mapping, conflicts = pilot.load_phase5_contents("sft", tmp_path)
    assert set(mapping) == {"k1", "k2"} and mapping["k1"] == ["a"] * 8 and conflicts == 1
    assert pilot.load_phase5_contents("rft", tmp_path) == ({}, 0)


def test_verdict_and_report_run_on_a_tiny_fixture():
    rep = {"n_compared": 8, "exact_overall": 1.0, "canonical_overall": 1.0, "exact_by_idx": {str(i): 1.0 for i in range(8)},
           "canonical_by_idx": {str(i): 1.0 for i in range(8)}, "inputs_without_phase5_log": 0}
    entry = {"model": "m", "model_digest": "sha256:abcdef", "inputs": 1, "lines": 8, "errors": 0, "error_rate": 0.0,
             "text_token_mismatches": 0, "mean_seconds_per_generation": 1.5, "mean_eval_count": 40.0,
             "mean_distinct_of_8": 1.2, "replication": rep}
    results = {"environment": {"version": "9.9"}, "profile_a": {g: dict(entry) for g in ("zeroshot", "sft", "rft")},
               "throughput": [{"label": "parallel4", "model": "m", "threads": 4, "generations": 60, "errors": 0, "wall_seconds": 30.0, "generations_per_hour": 7200}],
               "profile_b": {"sft": {"1.0": {"mean_distinct_of_8": 1.3, "schema_valid_share": 1.0, "error_rate": 0.0}}}}
    ready, reasons = pilot.verdict(results)
    assert ready and any("1.5" in r for r in reasons)  # ready, but profile B flagged
    text = pilot.build_report(results)
    assert "READY for the full harvest" in text and "7200" in text and "parallel4" in text and "Ollama version: 9.9" in text
    results["profile_a"]["sft"]["errors"], results["profile_a"]["sft"]["error_rate"] = 3, 0.1
    results["profile_a"]["rft"]["replication"]["canonical_by_idx"]["0"] = 0.5
    ready, reasons = pilot.verdict(results)
    assert not ready and any("above 2%" in r for r in reasons) and any("below 95%" in r for r in reasons)
    assert not pilot.verdict({"profile_a": {}, "throughput": []})[0]


@pytest.mark.skipif(not PATCH_IR_SCHEMA.exists(), reason="Patch-IR schema not present")
def test_all_pilot_steps_run_against_a_fake_server(tmp_path):
    inputs = tmp_path / "inputs.jsonl"
    rows = make_inputs(inputs)
    gens = {"zeroshot": "qwen3.5:4b", "sft": "argus-m1-sft", "rft": "argus-m1-rft"}
    phase5 = tmp_path / "p5"
    for g in gens:  # a Phase 5 log made from exactly what the fake server answers: replication must be 100%
        (phase5 / g).mkdir(parents=True)
        with open(phase5 / g / "x.candidates.jsonl", "w") as h:
            for r in rows:
                contents = [canned_content({"options": {"seed": s}}) for s in range(8)]
                h.write(json.dumps({"input_key": r["input_key"], "contents": contents}) + "\n")
    with FakeOllama() as fake:
        c = pilot.Common(host=fake.host, pilot_dir=tmp_path / "pilot", phase5_dir=phase5, inputs_path=inputs,
                         schema_path=SCHEMA_PATH, messages_fn=messages_fn, schema=SCHEMA, num_predict=64, timeout=5.0,
                         threads=2, generators=gens)
        assert pilot.main(["a"], common=c) == 0
        assert pilot.main(["throughput", "--label", "parallel4"], common=c) == 0
        assert pilot.main(["b"], common=c) == 0
        assert pilot.main(["report"], common=c) == 0
    results = pilot.load_results(tmp_path / "pilot")
    for g in gens:
        e = results["profile_a"][g]
        assert e["lines"] == 48 and e["errors"] == 0 and e["replication"]["exact_overall"] == 1.0
    assert sorted(r["threads"] for r in results["throughput"]) == [1, 2, 4]
    assert all(r["generations"] == 18 for r in results["throughput"])
    assert set(results["profile_b"]["sft"]) == {"1.0", "1.2", "1.4"}
    assert results["profile_b"]["sft"]["1.2"]["schema_valid_share"] == 1.0
    report = (tmp_path / "pilot" / "docs" / "pilot_report.md").read_text()
    assert "## Verdict" in report and "parallel4" in report
    # nothing was written into the contract folders
    assert not (tmp_path / "pilot" / "harvest_out" / "sft" / "B").exists()
