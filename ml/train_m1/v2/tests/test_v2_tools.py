"""Tests for escalate_stats, eval_v2 and build_v2_data with stand-in gate/scorer/prompt functions (no OPA, no Ollama)."""

import json
from collections import namedtuple

import pytest

from ml.train_m1.v2 import build_v2_data as b
from ml.train_m1.v2 import escalate_stats as es
from ml.train_m1.v2 import eval_v2 as ev

Gate = namedtuple("Gate", "passed outcome unsafe")


def rec(rule, **fields):
    return {"finding_id": "F-0", "rule_id": rule, "resource_id": "R_1", "resource_ref": "R_1", "fields": fields}


def fix(attr, value, rule="r.fix"):
    return {"finding_id": "F-0", "resource_ref": "R_1", "rationale_ref": rule, "ops": [{"op": "set_attr", "attr": attr, "value": value}]}


ESC = {"finding_id": "F-0", "resource_ref": "R_1", "rationale_ref": "r.esc", "ops": [{"op": "escalate", "reason": "human"}]}


def ex(i, rule, route, record, target, h=None):
    return {"id": "ex-%06d" % i, "rule_id": rule, "input": record, "target": target, "meta": {"route": route, "full_hash": h or "h%d" % i}}


def fake_gate(cases):
    out = []
    for record, patch in cases:
        ops = patch.get("ops") or [{}]
        op = ops[0].get("op")
        if op == "escalate":
            out.append(Gate(True, "escalated", False))
        elif op == "delete":
            out.append(Gate(False, "rejected", True))
        else:
            out.append(Gate(True, "fixed", False))
    return out


def line(key, idx, content, gen="sft", prof="B"):
    return {"input_key": key, "sample_idx": idx, "content": content, "error": None}


@pytest.fixture
def world():
    r1, r2 = rec("r.fix", a=False), rec("r.esc", s=False)
    k1, k2 = b.example_input_key(r1), b.example_input_key(r2)
    train = [ex(1, "r.fix", "T0", r1, fix("a", True)), ex(2, "r.fix", "T0", r1, fix("a", True)), ex(3, "r.esc", "ESC", r2, ESC),
             ex(4, "r.fix", "T0", r1, fix("a", True)), ex(5, "r.fix", "T0", r1, fix("a", True))]
    pool = {k1: [("sft/B", i, json.dumps(fix("a", v))) for i, v in enumerate([True, 1, 2, 3, 4, 5, "x", 9])] + [("sft/B", 9, json.dumps(fix("b", 0)))] +
                [("sft/B", 10, json.dumps({"ops": [{"op": "delete"}]})), ("sft/B", 11, "not json"), ("sft/B", 12, json.dumps(ESC))],
            k2: [("sft/B", 0, json.dumps(ESC)), ("sft/B", 1, json.dumps(fix("s", True)))]}
    return train, pool, k1, k2


def test_build_caps_distinct_answers_keeps_reference_and_rejects_bad_candidates(world):
    train, pool, k1, k2 = world
    rows, stats = b.build_rows(train, pool, fake_gate, seed=1)
    for key in (k1, k2):
        answers = {b.canon_of_patch(r["patch"]) for r in rows if r["input_key"] == key}
        assert len(answers) <= 4
    ref = b.canon_of_patch(fix("a", True))
    assert any(r["input_key"] == k1 and b.canon_of_patch(r["patch"]) == ref and r["kind"] == "sft" for r in rows)
    # no delete, no invalid JSON, and no escalate answer for a FIX rule, no fix answer for an ESC rule
    for r in rows:
        ops = [o["op"] for o in r["patch"]["ops"]]
        assert "delete" not in ops
        assert (ops == ["escalate"]) == (r["route"] == "ESC")
    assert stats["pool_candidates_gate_accepted"] < stats["pool_candidates_staged"]


def test_replay_side_matches_candidate_side(world):
    train, pool, k1, k2 = world
    rows, stats = b.build_rows(train, pool, fake_gate, seed=1)
    kinds = stats["rows_by_kind"]
    assert kinds["cand"] >= 1 and kinds["sft"] >= kinds["cand"] - 1 and abs(kinds["sft"] - kinds["cand"]) <= max(1, kinds["sft"] - 2)
    assert 0.3 < stats["sft_share"] < 0.8


def test_build_is_deterministic_and_seed_changes_choices(world):
    train, pool, *_ = world
    a, _ = b.build_rows(train, pool, fake_gate, seed=1)
    c, _ = b.build_rows(train, pool, fake_gate, seed=1)
    assert json.dumps(a, sort_keys=True) == json.dumps(c, sort_keys=True)
    others = {json.dumps(b.build_rows(train, pool, fake_gate, seed=s)[0], sort_keys=True) for s in range(2, 8)}
    assert len(others | {json.dumps(a, sort_keys=True)}) > 1


def test_held_out_hashes_never_reach_the_output_and_a_leak_is_fatal(world):
    train, pool, *_ = world
    rows, stats = b.build_rows(train, pool, fake_gate, seed=1, held={"h3", "h1"})
    assert not {"h3", "h1"} & {r["full_hash"] for r in rows}
    assert stats["train_examples_dropped_as_held_out"] == 2
    with pytest.raises(b.BuildError):
        b.check_no_leak(rows, {rows[0]["full_hash"]})


def test_only_train_inputs_are_used_and_extra_esc_needs_a_new_input(world):
    train, pool, k1, k2 = world
    pool["unrelated-key"] = [("sft/B", 0, json.dumps(fix("z", 1)))]
    r3 = rec("r.esc", s=True)
    extra = [ex(90, "r.esc", "ESC", r3, ESC, "x1"), ex(91, "r.esc", "ESC", rec("r.esc", s=False), ESC, "x2"),
             ex(92, "r.fix", "T0", rec("r.fix", a=True), fix("a", True), "x3"), ex(93, "r.esc", "ESC", rec("r.esc", s="held"), ESC, "heldhash")]
    rows, stats = b.build_rows(train, pool, fake_gate, seed=1, held={"heldhash"}, extra=extra)
    assert all(r["input_key"] != "unrelated-key" for r in rows)
    extras = [r for r in rows if r["kind"] == "esc_extra"]
    assert [r["example_id"] for r in extras] == ["ex-000090"] and stats["esc_distinct_inputs_added"] == 1


def test_gate_accepts_requires_matching_outcome():
    assert b.gate_accepts(Gate(True, "fixed", False), "T0") and not b.gate_accepts(Gate(True, "escalated", False), "M1")
    assert b.gate_accepts(Gate(True, "escalated", False), "ESC") and not b.gate_accepts(Gate(True, "fixed", False), "ESC")
    assert not b.gate_accepts(Gate(True, "fixed", True), "T0") and not b.gate_accepts(Gate(False, "fixed", False), "T0")


def test_write_outputs_is_byte_identical_and_uses_messages_format(world, tmp_path):
    train, pool, *_ = world
    rows, stats = b.build_rows(train, pool, fake_gate, seed=1)
    msgs = lambda r: [{"role": "system", "content": "s"}, {"role": "user", "content": json.dumps(r, sort_keys=True)}]  # noqa: E731
    pj = lambda p: json.dumps(p, sort_keys=True)  # noqa: E731
    p1 = b.write_outputs(rows, stats, tmp_path / "a", msgs, pj, 1, {})
    p2 = b.write_outputs(rows, stats, tmp_path / "b", msgs, pj, 1, {})
    assert p1["train"].read_bytes() == p2["train"].read_bytes() and b"\r" not in p1["train"].read_bytes()
    first = json.loads(p1["train"].read_text().splitlines()[0])
    assert set(first) == {"messages"} and [m["role"] for m in first["messages"]] == ["system", "user", "assistant"]
    assert len(p1["meta"].read_text().splitlines()) == len(rows)


def test_load_held_hashes_requires_the_files(tmp_path):
    f = tmp_path / "h.txt"
    f.write_text("a\nb c\n")
    assert b.load_held_hashes([f]) == {"a", "b", "c"}
    with pytest.raises(b.BuildError):
        b.load_held_hashes([tmp_path / "missing.txt"])


# ---- escalate_stats -------------------------------------------------------------------------------------

CONTRACT = """# x

| Rule ID | Library | Family | Resource type | Route | Mutator ID(s) | Notes |
|---|---|---|---|---|---|---|
| `r.fix` | CIS | f | T | T0 | `m_a` | n |
| `r.esc` | DPDP | f | T | ESC | `m_b` | n |

Totals: x
"""


def test_route_table_and_is_escalate(tmp_path):
    path = tmp_path / "c.md"
    path.write_text(CONTRACT)
    assert es.route_table(path) == {"r.fix": "T0", "r.esc": "ESC"}
    assert es.is_escalate(json.dumps(ESC)) and not es.is_escalate(json.dumps(fix("a", 1)))
    assert not es.is_escalate("junk") and not es.is_escalate(None) and not es.is_escalate('{"ops": []}')
    assert not es.is_escalate(json.dumps({"ops": [{"op": "escalate"}, {"op": "set_attr"}]}))


def test_compute_counts_tp_fn_fp_weighted_by_set_counts():
    inputs = [{"input_key": "k1", "record": {"rule_id": "r.esc"}, "sets": {"C_verifier": 51, "gold": 9}},
              {"input_key": "k2", "record": {"rule_id": "r.fix"}, "sets": {"A_val": 10, "C_verifier": 5}},
              {"input_key": "k3", "record": {"rule_id": "r.fix"}, "sets": {"A_val": 2}}]
    routes = {"r.esc": "ESC", "r.fix": "T0"}
    answers = {"sft": {"k1": json.dumps(fix("a", 1)), "k2": json.dumps(fix("a", 1)), "k3": json.dumps(ESC)},
               "rft": {"k1": json.dumps(ESC), "k2": None, "k3": json.dumps(fix("a", 1))}}
    r = es.compute(inputs, routes, answers)
    sft, rft = r["per_set"]["sft"], r["per_set"]["rft"]
    assert sft["C_verifier"]["fn"] == 51 and sft["C_verifier"].get("tp", 0) == 0 and sft["gold"]["fn"] == 9
    assert sft["A_val"]["fp"] == 2 and sft["A_val"]["fix_cases"] == 12
    assert rft["C_verifier"]["tp"] == 51 and rft["C_verifier"]["no_answer"] == 5 and rft["gold"]["tp"] == 9
    text = es.to_markdown(r)
    assert "| C_verifier | 51 | 51 | 0 | 1.000 |" in text and "| C_verifier | 51 | 0 | 51 | 0.000 |" in text
    with pytest.raises(ValueError):
        es.compute([{"input_key": "k", "record": {"rule_id": "unknown"}, "sets": {}}], routes, {"sft": {}})


# ---- eval_v2 --------------------------------------------------------------------------------------------

def fake_score(items):
    out = []
    for it in items:
        good = [c == json.dumps(it["reference"]) for c in it["contents"]]
        out.append({"pass_at": {1: good[0], 2: any(good[:2]), 8: any(good)}, "candidates": []})
    return out


def test_evaluate_computes_every_metric():
    r_fix, r_esc = rec("r.fix", a=False), rec("r.esc", s=False)
    ref_fix, ref_esc = fix("a", True), ESC
    examples = [ex(1, "r.fix", "T0", r_fix, ref_fix), ex(2, "r.fix", "T0", r_fix, ref_fix), ex(3, "r.esc", "ESC", r_esc, ref_esc), ex(4, "r.fix", "T0", rec("r.fix", a="other"), ref_fix)]
    good, bad = json.dumps(ref_fix), json.dumps(fix("a", False))
    cands = {b.example_input_key(r_fix): [good, bad, bad, bad, bad, bad, bad, json.dumps({"ops": [{"op": "delete"}]})],
             b.example_input_key(r_esc): [json.dumps(ref_fix)] + [good] * 7}
    res = ev.evaluate(examples, cands, fake_score, fake_gate)
    assert res["n_examples"] == 3 and res["examples_without_candidates"] == 1
    assert res["pass_at_1_count"] == 2 and res["pass_at_8"] == pytest.approx(2 / 3)
    assert res["unsafe_candidates"] == 2  # the delete candidate counted once per example sharing that input
    assert res["escalate"] == {"tp": 0, "fn": 1, "fp": 0, "tn": 2, "precision": None, "recall": 0.0}
    assert res["per_rule"]["r.fix"]["n"] == 2 and res["per_rule"]["r.esc"]["route_is_esc"] is True
    assert res["mean_distinct"] > 1 and "r.fix" in ev.to_markdown("t", res)


def test_harvest_loader_orders_samples_and_blanks_failures(tmp_path):
    from ml.train_m2.harvest.store import PartWriter
    w = PartWriter(tmp_path / "x" / "A")
    for idx, content, err in ((1, "b", None), (0, "a", None), (2, "", "timeout")):
        w.write({"input_key": "k", "sample_idx": idx, "content": content, "error": err})
    w.close()
    assert ev.candidates_from_harvest(tmp_path / "x" / "A") == {"k": ["a", "b", ""]}


# ---- guards that run on the REAL build output (skipped until you have built it) ---------------------------

def test_real_build_contains_no_held_out_hash():
    meta = b.V2_DIR / "data" / "v2_train.meta.jsonl"
    if not meta.exists():
        pytest.skip("v2 data has not been built yet (python -m ml.train_m1.v2.build_v2_data)")
    held = b.load_held_hashes(b.DEFAULT_HELD)
    rows = [json.loads(x) for x in meta.read_text().splitlines() if x.strip()]
    assert rows and not [r for r in rows if r["full_hash"] in held]
    assert {r["kind"] for r in rows} <= {"sft", "cand", "esc_extra"}
