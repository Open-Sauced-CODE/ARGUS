"""Phase 6 P3c tests: counterfactual fixes, oracle split, leak guard, corruptor store, accounting, diagnostics."""
from __future__ import annotations

import json
import math

import pytest

from ml.train_m2.labels import counterfactual as cf
from ml.train_m2.labels import corruptor_store as cs
from ml.train_m2.labels import harvest_checks as hc
from ml.train_m2.labels import shortcut_by_type as sb
from ml.train_m2.labels.accounting import compute_accounting, cp_upper_zero_errors, render_markdown
from ml.train_m2.labels.leakguard import (
    KeySets, LeakError, assert_training_safe, audit_label_rows, load_key_sets, raise_if_violations,
    training_rows,
)
from ml.train_m2.labels.oracle import LabelRow, _oracle_class, label_candidate

S3_ONE_FALSE = {
    "fields": {"block_public_acls": True, "block_public_policy": False, "ignore_public_acls": True,
               "resource_type": "AWSS3Bucket", "restrict_public_buckets": True},
    "finding_id": "F-0", "resource_id": "BUCKET_1", "resource_ref": "BUCKET_1", "rule_id": "cis.s3_public_access_block"}
S3_NONE_SET = {"fields": {"resource_type": "AWSS3Bucket"}, "finding_id": "F-0", "resource_id": "BUCKET_1",
               "resource_ref": "BUCKET_1", "rule_id": "cis.s3_public_access_block"}


def _ref(ops, rule="cis.s3_public_access_block"):
    return {"finding_id": "F-0", "resource_ref": "BUCKET_1", "ops": ops, "rationale_ref": rule}


def _set(attr, value):
    return {"op": "set_attr", "attr": attr, "value": value}


@pytest.fixture()
def bool_domain(monkeypatch):
    """Fresh clones have no dataset; supply the observed boolean fields the search needs."""
    obs = {f: {True, False} for f in
           ("block_public_acls", "block_public_policy", "ignore_public_acls", "restrict_public_buckets")}
    monkeypatch.setattr(cf, "_observed_field_values", lambda: obs)


class TestCounterfactualFixes:
    def test_search_depth_covers_all_rule_fields(self, bool_domain):
        o = cf.CounterfactualOracle("cis.s3_public_access_block")      # default max_edits=3
        assert o.max_edits >= 4

    def test_four_absent_flags_need_four_edits(self, bool_domain):
        ref = _ref([_set(a, True) for a in
                    ("block_public_acls", "block_public_policy", "ignore_public_acls", "restrict_public_buckets")])
        res = cf.CounterfactualOracle("cis.s3_public_access_block").classify(S3_NONE_SET, ref)
        assert res.label == "minimal_correct" and res.min_edits == 4

    def test_single_false_flag_is_one_edit(self, bool_domain):
        res = cf.CounterfactualOracle("cis.s3_public_access_block").classify(
            S3_ONE_FALSE, _ref([_set("block_public_policy", True)]))
        assert res.label == "minimal_correct" and res.min_edits == 1

    def test_partial_fix_is_not_minimal_correct_when_more_edits_needed(self, bool_domain):
        res = cf.CounterfactualOracle("cis.s3_public_access_block").classify(
            S3_NONE_SET, _ref([_set("block_public_acls", True)]))
        assert res.label != "minimal_correct"

    def test_domain_is_type_correct(self):
        lst = ["s3:ListBucket", "s3:GetObject", "*"]
        dom = cf._domain("action", lst)
        assert dom and all(isinstance(v, list) for v in dom)           # never a bool for a list field
        assert ["s3:ListBucket", "s3:GetObject"] in dom
        assert cf._domain("block_public_acls", False) == [True, False]

    def test_absent_field_uses_observed_bools(self, bool_domain):
        assert cf._domain("block_public_acls", None) == [True, False]

    def test_unknown_carries_a_reason(self, bool_domain):
        silent = {"fields": {"block_public_acls": True, "block_public_policy": True, "ignore_public_acls": True,
                             "resource_type": "AWSS3Bucket", "restrict_public_buckets": True},
                  "finding_id": "F-0", "resource_id": "BUCKET_1", "resource_ref": "BUCKET_1",
                  "rule_id": "cis.s3_public_access_block"}
        res = cf.CounterfactualOracle("cis.s3_public_access_block").classify(silent, _ref([_set("block_public_acls", True)]))
        assert res.label == "unknown" and res.reason == "already_silent"

    def test_states_counter_is_per_search(self, bool_domain):
        o = cf.CounterfactualOracle("cis.s3_public_access_block")
        o.search_minimal(dict(S3_NONE_SET["fields"]))
        first = o.last_search["visited"]
        o.search_minimal(dict(S3_NONE_SET["fields"]))
        assert o.last_search["visited"] == first


class TestOracleSplitAndFields:
    H = {"full_equivalence": True, "minimal_patch": False, "decoys_untouched": True, "no_side_effects": True}

    def test_harmless_extra_is_valid_not_minimal(self):
        assert _oracle_class(True, "fixed", dict(self.H), "fix", False) == "valid_not_minimal"

    def test_side_effects_are_wrong(self):
        h = dict(self.H, no_side_effects=False)
        assert _oracle_class(True, "fixed", h, "fix", False) == "wrong"

    def test_touched_decoys_are_wrong(self):
        h = dict(self.H, decoys_untouched=False)
        assert _oracle_class(True, "fixed", h, "fix", False) == "wrong"

    def test_label_row_carries_patch_and_answer_key(self):
        rec = S3_ONE_FALSE
        ref = _ref([_set("block_public_policy", True)])
        row = label_candidate(rec, ref, reference=ref, route="fix", input_key="k1")
        assert row.patch == ref and row.answer_key
        again = LabelRow.from_dict(row.to_dict())
        assert again.patch == ref and again.answer_key == row.answer_key

    def test_content_parameter_fills_patch_when_no_object(self):
        ref = _ref([_set("block_public_policy", True)])
        row = label_candidate(S3_ONE_FALSE, None, reference=ref, route="fix", content=json.dumps(ref))
        assert row.patch == ref and row.answer_key

    def test_same_patch_same_answer_key(self):
        ref = _ref([_set("block_public_policy", True)])
        other = dict(ref, finding_id="F-9")                              # finding_id is ignored by canon
        a = label_candidate(S3_ONE_FALSE, ref, reference=ref, route="fix")
        b = label_candidate(S3_ONE_FALSE, other, reference=ref, route="fix")
        assert a.answer_key == b.answer_key


def _ks():
    return KeySets(held_out={"tierB1": {"h1", "h2"}, "gold": {"g1"}}, a_val={"v1", "v2"},
                   phase5_train={"t1", "t2", "t3", "h1", "v1"}, v2_train={"t1", "t2", "t3", "h1", "v1"})


def _row(**kw):
    base = {"input_key": "t1", "generator": "sft", "source": "scored_log", "gate_pass": True,
            "oracle_class": "minimal_correct", "outcome": "fixed", "answer_key": "a1", "patch": {}, "sample_idx": 0,
            "source_file": "f", "profile": "A"}
    base.update(kw)
    return base


class TestLeakGuard:
    def test_generator_seen_rules(self):
        ks = _ks()
        assert ks.generator_seen("sft", "t1") and not ks.generator_seen("sft", "v2")
        assert not ks.generator_seen("zeroshot", "t1")
        with pytest.raises(ValueError):
            ks.generator_seen("nope", "t1")

    def test_corruptor_eligible_excludes_heldout_and_a_val(self):
        assert _ks().corruptor_eligible() == {"t1", "t2", "t3"}

    def test_clean_rows_pass(self):
        rep = audit_label_rows([_row(), _row(input_key="v2", sample_idx=1)], _ks())
        assert rep["violations"] == {}

    def test_corruptor_rows_need_no_generator(self):
        row = _row(source="corruptor", generator=None, input_key="t1", source_input_key="t1",
                   corruption_type="C1", train_only=True, answer_key="q")
        assert audit_label_rows([row], _ks())["violations"] == {}

    def test_audit_catches_problems(self):
        ks = _ks()
        rows = [
            _row(input_key="h1", heldout_sets=[]),                                   # wrong held-out flag
            _row(input_key="t1", generator_seen=False),                              # wrong seen flag
            _row(answer_key=None, sample_idx=2),                                     # no answer key
            _row(source="corruptor", input_key="t1", source_input_key="h1", corruption_type="C1",
                 train_only=True, answer_key="x", sample_idx=3),                    # seed is held-out
            _row(source="corruptor", input_key="t2", source_input_key="t2", corruption_type="C1",
                 train_only=True, answer_key="y", sample_idx=4),
            _row(source="corruptor", input_key="t2", source_input_key="t2", corruption_type="C1",
                 train_only=True, answer_key="y", sample_idx=5),                    # duplicate corruptor row
            _row(source="corruptor", input_key="t3", source_input_key="t3", corruption_type="C2",
                 answer_key="z", sample_idx=6),                                      # not train_only
            _row(sample_idx=7), _row(sample_idx=7),                                  # duplicate natural row
        ]
        v = audit_label_rows(rows, ks)["violations"]
        for name in ("flag_heldout_sets_wrong", "flag_generator_seen_wrong", "missing_answer_key",
                     "corruptor_seed_heldout", "corruptor_seed_not_eligible", "duplicate_corruptor_row",
                     "corruptor_not_train_only", "duplicate_natural_row"):
            assert name in v, name
        with pytest.raises(LeakError):
            raise_if_violations({"violations": v})

    def test_training_rows_filter_and_assert(self):
        ks = _ks()
        good = _row(input_key="t2")
        held = _row(input_key="h1")
        bad_c = _row(source="corruptor", input_key="t1", source_input_key="v1", corruption_type="C1")
        ok_c = _row(source="corruptor", input_key="t1", source_input_key="t1", corruption_type="C1")
        kept = list(training_rows([good, held, bad_c, ok_c], ks))
        assert kept == [good, ok_c]
        assert assert_training_safe(kept, ks) == 2
        with pytest.raises(LeakError):
            assert_training_safe([held], ks)
        with pytest.raises(LeakError):
            assert_training_safe([bad_c], ks)

    def test_load_key_sets_and_strict(self, tmp_path):
        def w(rel, rows):
            p = tmp_path / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("\r\n".join(json.dumps(r) for r in rows) + "\r\n", encoding="utf-8", newline="")
        for n, k in (("tierB1", "h1"), ("tierB2", "h2"), ("tierC_verifier", "h3"), ("gold", "g1")):
            w(f"ml/mutation_engine/held_out/{n}.jsonl", [{"input_key": k}])
        w("ml/mutation_engine/dataset/val.jsonl", [{"input_key": "v1"}])
        w("ml/train_m1/data/sft_train.jsonl", [{"input_key": "t1"}, {"input_key": "t1"}])
        w("ml/train_m1/v2/data/v2_train.meta.jsonl", [{"input_key": "t1"}])
        ks = load_key_sets(tmp_path)
        assert ks.phase5_train == {"t1"} and ks.held_out_union == {"h1", "h2", "h3", "g1"} and ks.missing == []
        (tmp_path / "ml/mutation_engine/dataset/val.jsonl").unlink()
        with pytest.raises(LeakError):
            load_key_sets(tmp_path)
        assert load_key_sets(tmp_path, strict=False).missing


def _make_rows(record, reference, route, ik, seed):
    out = []
    for ct in ("C1", "C2", "C3", "C4"):
        for ak in ("a", "b"):
            out.append({"input_key": ik, "corruption_type": ct, "answer_key": f"{ct}-{ak}", "gate_pass": True,
                        "oracle_class": "wrong"})
    out.append({"input_key": ik, "corruption_type": "C1", "answer_key": "C1-a", "gate_pass": True,
                "oracle_class": "wrong"})                                              # duplicate
    return out


class TestCorruptorStore:
    def test_cap_for(self):
        assert cs.cap_for(65, 0.35) == 35 and cs.cap_for(0, 0.35) == 0
        with pytest.raises(ValueError):
            cs.cap_for(10, 1.0)

    def test_build_store_filters_dedupes_caps_and_is_deterministic(self):
        seeds = [("k2", {}, {}, "fix"), ("k1", {}, {}, "fix")]
        rows, rep = cs.build_store(seeds, _make_rows, keep_types={"C1", "C2", "C3"}, n_natural=10, frac=0.35, seed=1)
        assert rep["generated"] == 2 * 9 and rep["after_type_filter"] == 2 * 7
        assert rep["after_dedupe"] == 2 * 6 and rep["cap"] == cs.cap_for(10, 0.35)
        assert rep["kept"] == len(rows) <= rep["cap"]
        assert all(r["train_only"] and r["source"] == "corruptor" and r["source_input_key"] in ("k1", "k2") for r in rows)
        assert len({(r["source_input_key"], r["corruption_type"], r["answer_key"]) for r in rows}) == len(rows)
        rows2, _ = cs.build_store(seeds[::-1], _make_rows, keep_types={"C1", "C2", "C3"}, n_natural=10, frac=0.35, seed=1)
        assert rows == rows2                                                           # order-independent, deterministic

    def test_round_robin_across_types(self):
        rows, _ = cs.build_store([("k1", {}, {}, "fix"), ("k2", {}, {}, "fix")], _make_rows,
                                 keep_types={"C1", "C2", "C3"}, n_natural=6, frac=0.35, seed=1)
        types = {r["corruption_type"] for r in rows}
        assert len(rows) == 3 and types == {"C1", "C2", "C3"}


def _arow(generator, key, ak, cls, **kw):
    base = {"input_key": key, "generator": generator, "source": "scored_log", "gate_pass": True, "outcome": "fixed",
            "oracle_class": cls, "answer_key": ak, "patch": {}, "sample_idx": 0, "source_file": "f"}
    base.update(kw)
    return base


class TestAccounting:
    def test_pools_distinct_and_generated_rows_never_counted(self):
        ks = _ks()
        rows = [
            _arow("sft", "t1", "a", "minimal_correct"),
            _arow("sft", "t1", "a", "minimal_correct", sample_idx=1),                    # same candidate again
            _arow("sft", "v2", "b", "wrong"),                                              # unseen, A_val-only: calibration
            _arow("sft", "v2", "c", "valid_not_minimal"),
            _arow("sft", "h1", "d", "wrong"),                                              # held-out
            _arow("zeroshot", "t2", "e", "fixed_should_escalate"),
            _arow("sft", "t3", "f", "unknown"),                                            # excluded
            _arow("sft", "t3", "g", "wrong", gate_pass=False),                             # excluded (gate-fail)
        ]
        for i in range(50):                                                                # generated rows must not count
            rows.append({"input_key": "t1", "generator": "sft", "source": "corruptor", "source_input_key": "t1",
                         "corruption_type": "C1", "answer_key": f"c{i}", "gate_pass": True, "oracle_class": "wrong",
                         "train_only": True, "patch": {}})
        rep = compute_accounting(rows, ks)
        sft_all = rep["natural"]["all"]["sft"]
        assert sft_all["candidates"] == 4 and sft_all["strict_negatives"] == 3 and sft_all["harmful_negatives"] == 2
        sft_cal = rep["natural"]["calibration"]["sft"]
        assert sft_cal["candidates"] == 2 and sft_cal["clusters"] == 1 and sft_cal["strict_negatives"] == 2
        assert rep["natural"]["usable"]["union"]["strict_negatives"] == 3          # v2:b, v2:c, t2:e
        assert rep["corruptor"]["hard_negatives"] == 50
        assert rep["bar"]["total_negatives"] == 3 + 50 and rep["bar"]["natural_cluster_verdict"].startswith("FAIL")
        assert "never summed" in render_markdown(rep)

    def test_zero_error_alpha(self):
        assert cp_upper_zero_errors(15) == pytest.approx(1 - 0.05 ** (1 / 15))
        assert 0.18 < cp_upper_zero_errors(15) < 0.19 and cp_upper_zero_errors(59) < 0.05
        assert math.isnan(cp_upper_zero_errors(0))


class TestShortcutDiagnostics:
    def test_auc_values(self):
        assert sb.auc([2, 3], [0, 1]) == 1.0 and sb.auc([0, 1], [2, 3]) == 0.0 and sb.auc([1, 1], [1, 1]) == 0.5

    def test_separability_per_type(self):
        nat = [{"patch": {"ops": [{}]}} for _ in range(5)]
        cor = [{"corruption_type": "C1", "patch": {"ops": [{}, {}]}}] * 3 + \
              [{"corruption_type": "C2", "patch": {"ops": [{}]}}] * 3
        out = sb.separability(cor, nat)
        assert out["C1"]["n_ops"] == 1.0 and out["C1"]["trivially_separable"]
        assert out["C2"]["n_ops"] == 0.5


class TestHarvestChecks:
    def test_length_stats_accepts_iterators(self):
        rows = iter([{"sample_idx": 0, "eval_count": 500, "done_reason": "length"},
                     {"sample_idx": 0, "eval_count": 100, "done_reason": "stop"},
                     {"sample_idx": 1, "eval_count": 900, "done_reason": "length"}])
        s = hc.length_stats(rows, 400)
        assert s["greedy_rows"] == 2 and s["greedy_over_limit"] == 1 and s["greedy_done_length"] == 1

    def test_compare_common_uses_only_shared_keys(self):
        r = hc.compare_common({"a": True, "b": False, "c": True}, {"b": True, "c": True, "d": True})
        assert r["n_common"] == 2 and r["a_pass"] == 1 and r["b_pass"] == 2 and r["b_only_pass"] == 1

    def test_per_key_vs_per_example(self):
        mk = lambda fid, extra=0: {"rule_id": "r", "input": {"finding_id": fid, "x": extra}, "target": {"t": extra},
                                   "meta": {"route": "FIX"}}
        exs = [mk("F-0"), mk("F-1"), mk("F-1", 7)]
        gate = lambda ex, p: ((ex["input"]["x"] == 0) and p["finding_id"] == ex["input"]["finding_id"], [])
        res = hc.per_key_vs_per_example(exs, {"k": {"finding_id": "F-0"}}, lambda e: "k", gate)
        assert res["n_examples"] == 3 and res["per_key_weighted_pass"] == 3 and res["per_example_aligned_pass"] == 2
        d = res["differing_examples"]
        assert len(d) == 1 and d[0]["record_fields_differ"] == ["x"] and d[0]["reference_differs"] is True
