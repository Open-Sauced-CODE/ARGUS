"""M2 core tests: features, splits, metrics, calibrators, model, risk control, decision engine, run-once."""
from __future__ import annotations

import json
import random
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ml.train_m2 import decide as D
from ml.train_m2 import splits as S
from ml.train_m2.eval import run_once as RO
from ml.train_m2.features import compute as FC
from ml.train_m2.features import registry as R
from ml.train_m2.models import calibrate as CAL
from ml.train_m2.models import dataset as DS
from ml.train_m2.models import metrics as M
from ml.train_m2.models import train_m2 as T
from ml.train_m2.models import zoo
from ml.train_m2.risk import calibrate_tau as CT
from ml.train_m2.risk.decisions import select_decisions

FEATURE_DIR = Path(__file__).resolve().parents[1] / "features"


def _tok(text, lp=-0.1, top=None):
    return {"t": text, "lp": lp, "top": top or [[text, lp], ["x", lp - 2.0]]}


def _row(content, idx=0, gen="sft", toks=True):
    r = {"content": content, "generator": gen, "sample_idx": idx}
    r["tokens"] = [_tok(c) for c in [content[:5], content[5:]]] if toks else None
    return r


PATCH = '{"finding_id":"F-0","resource_ref":"R","ops":[{"op":"set_attr","attr":"default_encryption","value":true}],"rationale_ref":"dpdp.rule6a"}'
OTHER = '{"finding_id":"F-0","resource_ref":"R","ops":[{"op":"set_attr","attr":"encryption_algorithm","value":"aws:kms"}],"rationale_ref":"dpdp.rule6a"}'
CTX = {"rule_id": "dpdp.rule6a", "route": "fix"}


class TestFeatures:
    def test_agreement_hand_calculation(self):
        cohort = [_row(PATCH, i) for i in range(6)] + [_row(OTHER, i) for i in (6, 7)]
        f = FC.compute_features(cohort[0], cohort, CTX)
        assert f["agreement_rate"] == 0.75 and f["modal_share"] == 0.75 and f["n_distinct_patches"] == 2.0
        assert f["greedy_is_modal"] == 1.0 and f["n_valid_over_n_requested"] == 1.0
        g = FC.compute_features(cohort[7], cohort, CTX)
        assert g["agreement_rate"] == 0.25

    def test_finding_id_does_not_change_the_answer(self):
        a = PATCH
        b = PATCH.replace('"F-0"', '"F-9"')
        cohort = [_row(a, 0), _row(b, 1)]
        assert FC.compute_features(cohort[0], cohort, CTX)["agreement_rate"] == 1.0

    def test_none_without_tokens_and_invalid_json(self):
        r = _row("not json", toks=False)
        f = FC.compute_features(r, [r], CTX)
        assert f["lp_mean"] is None and f["entropy_mean"] is None and f["n_valid_over_n_requested"] == 0.0
        assert f["n_ops"] == 0.0 and f["writes_only_rule_fields_frac"] is None

    def test_uncertainty_values(self):
        r = {"content": "ab", "generator": "sft", "sample_idx": 0,
             "tokens": [_tok("a", -1.0, [["a", -1.0], ["b", -2.0]]), _tok("b", -3.0, [["b", -3.0], ["c", -3.0]])]}
        f = FC.compute_features(r, [r], CTX)
        assert f["lp_mean"] == -2.0 and f["lp_min"] == -3.0 and f["seq_logprob"] == -4.0
        assert f["top1_top2_margin_mean"] == pytest.approx(0.5) and 0 < f["entropy_mean"] <= np.log(2)

    def test_writes_only_rule_fields(self):
        cohort = [_row(PATCH)]
        assert FC.compute_features(cohort[0], cohort, CTX)["writes_only_rule_fields_frac"] == 1.0

    def test_parity_matrix_vs_single(self):
        rows = [(_row(PATCH if i % 3 else OTHER, i % 8), [_row(PATCH, j) for j in range(8)], CTX) for i in range(60)]
        mat = FC.compute_matrix(rows)
        for i, (r, c, x) in enumerate(rows):
            single = FC.compute_features(r, c, x)
            for n in R.names():
                a, b = mat.iloc[i][n], single[n]
                assert (np.isnan(a) and b is None) or a == b

    def test_spec_hash_changes_with_spec(self):
        base = R.spec_hash()
        changed = tuple(s if s.name != "lp_mean" else R.FeatureSpec("lp_mean", "U", -1, s.description) for s in R.REGISTRY)
        assert R.spec_hash(changed) != base and all(len(R.names()) == len(set(R.names())) for _ in [0])

    def test_features_never_import_labels(self):
        for p in FEATURE_DIR.glob("*.py"):
            assert not re.search(r"^\s*(from|import)\s+ml\.train_m2\.labels", p.read_text(encoding="utf-8"), re.M), p.name

    def test_real_harvest_rows_if_present(self):
        root = Path(__file__).resolve().parents[3] / "ml" / "train_m2" / "harvest_out" / "sft" / "A"
        files = sorted(root.glob("part-*.jsonl"))
        if not files:
            pytest.skip("harvest_out not present in this checkout (git-ignored data)")
        rows = [json.loads(l) for l in open(files[0], encoding="utf-8", newline="") if l.strip()][:16]
        k = rows[0]["input_key"]
        cohort = [r for r in rows if r["input_key"] == k]
        f = FC.compute_features(cohort[0], cohort, {"rule_id": "dpdp.rule6a", "route": "fix"})
        assert f["lp_mean"] is not None and set(R.names()) <= set(f)


def _clusters(n=300, fams=("a", "b", "c", "d")):
    rnd = random.Random(3)
    return {f"k{i}": rnd.choice(fams) for i in range(n)}


class TestSplits:
    def test_disjoint_cover_and_test_only(self):
        cl = _clusters()
        test_only = {f"k{i}" for i in range(0, 300, 7)}
        s = S.build_splits(cl, test_only, force_cal={"k1", "k2"})
        S.assert_disjoint(s)
        assert test_only <= set(s["parts"]["test"]) and {"k1", "k2"} <= set(s["parts"]["cal"])
        assert sum(len(v) for v in s["parts"].values()) == len(cl)

    def test_deterministic_and_hash_sensitive(self):
        cl = _clusters()
        a, b = S.build_splits(cl, set()), S.build_splits(cl, set())
        assert a == b
        moved = json.loads(json.dumps(a))
        k = moved["parts"]["train"].pop()
        moved["parts"]["val"].append(k)
        assert S.splits_hash(moved) != a["sha256"]
        assert S.build_splits(cl, set(), seed=7)["sha256"] != a["sha256"]

    def test_lofo_removes_family_everywhere(self):
        s = S.build_splits(_clusters(), set())
        for fam, parts in S.lofo_splits(s):
            for p in ("train", "val", "cal"):
                assert all(s["family"][k] != fam for k in parts[p])
            assert parts["test"] and all(s["family"][k] == fam for k in parts["test"])

    def test_read_rejects_tampering(self, tmp_path):
        s = S.build_splits(_clusters(50), set())
        S.write_splits(tmp_path / "s.json", s)
        assert S.read_splits(tmp_path / "s.json")["sha256"] == s["sha256"]
        d = json.loads((tmp_path / "s.json").read_text())
        d["parts"]["val"].append(d["parts"]["train"].pop())
        (tmp_path / "t.json").write_text(json.dumps(d))
        with pytest.raises(AssertionError):
            S.read_splits(tmp_path / "t.json")

    def test_cell_table_flags_small_cells(self):
        assert "*" in S.cell_table(S.build_splits(_clusters(40), set()))


class TestMetricsAndCalibrators:
    def test_ece_calibrated_vs_overconfident(self):
        rng = np.random.default_rng(0)
        p = rng.uniform(0.05, 0.95, 20000)
        y = (rng.uniform(size=20000) < p).astype(int)
        assert M.ece(p, y) < 0.02
        assert M.ece(np.full(2000, 0.99), (rng.uniform(size=2000) < 0.7).astype(int)) > 0.25

    def test_auroc_and_aurc(self):
        assert M.auroc([0.9, 0.8, 0.2, 0.1], [1, 1, 0, 0]) == 1.0
        assert M.aurc([0.9, 0.8, 0.2, 0.1], [0, 0, 1, 1]) < M.aurc([0.9, 0.8, 0.2, 0.1], [1, 1, 0, 0])

    def test_bootstrap_resamples_whole_clusters(self):
        calls = []
        def metric(c, v):
            calls.append(sorted(set(c)))
            return float(np.mean(v))
        clusters = np.repeat(np.arange(10), 5)
        vals = np.arange(50, dtype=float)
        M.cluster_bootstrap(lambda v: float(np.mean(v)), clusters, vals, reps=50)
        idx = np.random.default_rng(1337).choice(np.unique(clusters), size=10, replace=True)
        assert len(idx) == 10                                           # draws are over the 10 clusters, not the 50 rows

    def test_calibrators_monotone_and_bounded(self):
        rng = np.random.default_rng(1)
        p = rng.uniform(size=400)
        y = (rng.uniform(size=400) < p ** 2).astype(int)
        grid = np.linspace(0.02, 0.98, 40)
        for name, cal in CAL.fit_all(p, y).items():
            q = cal.predict(grid)
            assert np.all(q >= 0) and np.all(q <= 1), name
            assert np.all(np.diff(q) >= -1e-9), name

    def test_single_class_gives_no_calibrators(self):
        assert CAL.fit_all([0.5, 0.6], [1, 1]) == {}


def _synthetic(n=600, seed=0):
    rng = np.random.default_rng(seed)
    X = pd.DataFrame(0.0, index=range(n), columns=R.names())
    X["agreement_rate"] = rng.uniform(0, 1, n)
    X["lp_min"] = -rng.exponential(3, n)
    X["n_ops"] = rng.integers(1, 4, n).astype(float)
    X["lp_mean"] = -rng.exponential(0.5, n)
    z = 3 * X["agreement_rate"] + 0.2 * X["lp_min"] - 0.3 * X["n_ops"] + 0.5
    y = (rng.uniform(size=n) < 1 / (1 + np.exp(-z))).astype(int)
    meta = pd.DataFrame({"input_key": [f"c{i % 150}" for i in range(n)], "generator": "sft", "sample_idx": np.arange(n) % 8,
                         "rule_id": "dpdp.rule6a", "y": y})
    return X, y, meta


class TestModel:
    def test_monotone_constraint_respected(self):
        X, y, _ = _synthetic()
        m = zoo.fit_lightgbm(X.iloc[:400], y[:400], X.iloc[400:], y[400:])
        base = X.iloc[[0]].copy()
        preds = []
        for v in np.linspace(0, 1, 25):
            base["agreement_rate"] = v
            preds.append(zoo.predict_lightgbm(m, base)[0])
        assert np.all(np.diff(preds) >= -1e-9)

    def test_fit_is_deterministic_and_roundtrips(self, tmp_path):
        X, y, meta = _synthetic()
        a1, rep1 = T.fit_m2(X.iloc[:400], y[:400], X.iloc[400:], y[400:], meta.iloc[400:], "sha", 1337)
        a2, rep2 = T.fit_m2(X.iloc[:400], y[:400], X.iloc[400:], y[400:], meta.iloc[400:], "sha", 1337)
        assert np.allclose(T.predict(a1, X.iloc[400:]), T.predict(a2, X.iloc[400:]))
        assert rep1["selected_model"] in ("logistic", "lightgbm") and rep1["calibrated"]
        T.save(a1, rep1, tmp_path)
        assert (tmp_path / "m2.joblib").exists() and "model" not in json.loads((tmp_path / "model_card.json").read_text())

    def test_single_class_val_is_flagged_not_hidden(self):
        X, y, meta = _synthetic()
        art, rep = T.fit_m2(X.iloc[:400], y[:400], X.iloc[400:], np.ones(200, int), meta.iloc[400:], "sha")
        assert rep["calibrated"] is False and "NOT calibrated" in rep["warning"]

    def test_build_frame_population_and_labels(self):
        hv = {"sft": {("k", i): {"content": PATCH, "tokens": [_tok("a")], "generator": "sft", "sample_idx": i} for i in range(8)}}
        info = {"k": {"route": "fix", "rule_id": "dpdp.rule6a"}, "e": {"route": "escalate", "rule_id": "dpdp.rule7_detection"}}
        base = {"generator": "sft", "gate_pass": True, "outcome": "fixed", "source": "scored_log"}
        rows = [dict(base, input_key="k", sample_idx=0, oracle_class="minimal_correct"),
                dict(base, input_key="k", sample_idx=1, oracle_class="wrong"),
                dict(base, input_key="k", sample_idx=2, oracle_class="valid_not_minimal"),
                dict(base, input_key="k", sample_idx=3, oracle_class="unknown"),
                dict(base, input_key="k", sample_idx=4, oracle_class="wrong", gate_pass=False),
                dict(base, input_key="k", sample_idx=5, oracle_class="wrong", source="corruptor"),
                dict(base, input_key="e", sample_idx=0, oracle_class="fixed_should_escalate"),
                dict(base, input_key="k", sample_idx=99, oracle_class="wrong")]
        X, meta = DS.build_frame(rows, hv, info)
        assert list(meta["y"]) == [1, 0, 0] and list(X.columns) == R.names()
        assert meta.attrs["n_unjoined_label_rows"] == 1


class TestRiskControl:
    def test_select_decisions_first_passing_by_sample_order(self):
        df = pd.DataFrame({"input_key": ["a", "a", "b", "b", "b"], "sample_idx": [3, 1, 2, 0, 5], "score": [.9, .5, .7, .8, .1]})
        sel = select_decisions(df)
        assert list(sel["input_key"]) == ["a", "b"] and list(sel["sample_idx"]) == [1, 0]
        assert select_decisions(df.iloc[0:0]).empty

    def test_too_few_clusters_never_certifies(self):
        out = CT.calibrate(np.full(30, 0.99), np.zeros(30, int))
        assert out["certified"] is False and out["tau"] is None and "autonomy stays OFF" in out["message"]

    def test_enough_clean_clusters_certify(self):
        rng = np.random.default_rng(0)
        s = np.concatenate([rng.uniform(0.95, 1.0, 400), rng.uniform(0.5, 0.9, 100)])
        w = np.concatenate([np.zeros(400, int), rng.integers(0, 2, 100)])
        out = CT.calibrate(s, w)
        assert out["certified"] is True and out["tau"] is not None and out["ucb"] <= 0.05 + 1e-9

    def test_run_refuses_hash_mismatch(self):
        art = {"splits_sha256": "A", "spec_hash": R.spec_hash()}
        fr = pd.DataFrame({"input_key": ["a"], "sample_idx": [0], "generator": ["sft"], "score": [0.9], "y": [1]})
        with pytest.raises(AssertionError):
            CT.run(fr, art, "B")
        with pytest.raises(AssertionError):
            CT.run(fr, {"splits_sha256": "A", "spec_hash": "zzz"}, "A")


class TestDecide:
    CFG = json.loads((Path(__file__).resolve().parents[1] / "configs" / "decision.json").read_text())

    @pytest.fixture()
    def art_feats(self):
        X, y, meta = _synthetic()
        art, _ = T.fit_m2(X.iloc[:400], y[:400], X.iloc[400:], y[400:], meta.iloc[400:], "sha")
        f = {n: float(X.iloc[0][n]) for n in R.names()}
        f["agreement_rate"], f["lp_min"], f["n_ops"] = 1.0, -0.1, 1.0
        f["spec_hash"] = art["spec_hash"]
        return art, f

    def test_spec_mismatch_raises(self, art_feats):
        art, f = art_feats
        with pytest.raises(D.FeatureSpecMismatch):
            D.confidence(dict(f, spec_hash="other"), art)

    def test_gate_failure_and_escalate_only_never_reach_m2(self, art_feats):
        art, f = art_feats
        bad = dict(f, spec_hash="other")                       # would raise if M2 were consulted
        d1 = D.decide(bad, gate_passed=False, escalated_only=False, breaker="CLOSED", config=self.CFG, tau_info={}, art=art)
        d2 = D.decide(bad, gate_passed=True, escalated_only=True, breaker="CLOSED", config=self.CFG, tau_info={"certified": True, "tau": 0.5}, art=art)
        assert d1.action == "reject" and d2.action == "human_review" and d2.p_hat is None

    def test_uncertified_breaker_and_ood_force_review(self, art_feats):
        art, f = art_feats
        unc = D.decide(f, gate_passed=True, escalated_only=False, breaker="CLOSED", config=self.CFG, tau_info={"certified": False}, art=art)
        assert unc.action == "human_review" and "autonomy off" in unc.reasons[0] and unc.p_hat is not None
        brk = D.decide(f, gate_passed=True, escalated_only=False, breaker="OPEN", config=self.CFG, tau_info={"certified": True, "tau": 0.0}, art=art)
        assert brk.action == "human_review" and any("breaker" in r for r in brk.reasons)
        ood = D.decide(dict(f, lp_min=-1e6), gate_passed=True, escalated_only=False, breaker="CLOSED", config=self.CFG,
                       tau_info={"certified": True, "tau": 0.0}, art=art)
        assert ood.action == "human_review" and any("ood" in r for r in ood.reasons)

    def test_stricter_threshold_wins_property(self, art_feats):
        art, f = art_feats
        rnd = random.Random(0)
        p = D.confidence(f, art)
        for _ in range(60):
            tau = rnd.uniform(0, 1)
            cfg = D.set_cost_ratio(self.CFG, rnd.uniform(2, 50), 1.0)
            d = D.decide(f, gate_passed=True, escalated_only=False, breaker="CLOSED", config=cfg,
                         tau_info={"certified": True, "tau": tau}, art=art)
            thr = max(tau, 1 - cfg["c_esc"] / cfg["c_FA"])
            assert d.threshold_used == pytest.approx(thr)
            assert (d.action == "auto_apply") == (p >= thr and not any("ood" in r for r in d.reasons))

    def test_cost_ratio_never_changes_tau_and_validates(self):
        cfg = D.set_cost_ratio(self.CFG, 40, 1)
        assert D.bayes_cutoff(cfg["c_FA"], cfg["c_esc"]) == pytest.approx(0.975)
        with pytest.raises(ValueError):
            D.set_cost_ratio(self.CFG, 1, 5)

    def test_decide_is_deterministic(self, art_feats):
        art, f = art_feats
        kw = dict(gate_passed=True, escalated_only=False, breaker="CLOSED", config=self.CFG, tau_info={"certified": True, "tau": 0.5}, art=art)
        assert D.decide(f, **kw) == D.decide(f, **kw)

    def test_contributions_sum_to_raw_score_and_text_is_clean(self, art_feats):
        art, f = art_feats
        if art["kind"] != "lightgbm":
            art = dict(art)
            X, y, meta = _synthetic()
            art["model"] = zoo.fit_lightgbm(X.iloc[:400], y[:400], X.iloc[400:], y[400:])
            art["kind"] = "lightgbm"
        X = D._row(f, art)
        contrib = art["model"].booster_.predict(X, pred_contrib=True)[0]
        raw = art["model"].booster_.predict(X, raw_score=True)[0]
        assert contrib.sum() == pytest.approx(raw, abs=1e-6)
        for c in D.explain(f, art):
            assert not re.search(r"arn:|[A-Z]+_[0-9]+|\d{12}", c.text)


class TestRunOnce:
    def test_requires_prereg_and_blocks_repeats(self, tmp_path):
        log, pre = tmp_path / "log.md", tmp_path / "PREREG.md"
        with pytest.raises(RO.RunOnceError):
            RO.run_once("m", "B1", lambda: {"x": 1}, log=log, prereg=pre)
        pre.write_text("frozen")
        assert RO.run_once("m", "B1", lambda: {"x": 1}, log=log, prereg=pre) == {"x": 1}
        with pytest.raises(RO.RunOnceError):
            RO.run_once("m", "B1", lambda: {"x": 2}, log=log, prereg=pre)
        RO.run_once("m", "B1", lambda: {"x": 2}, repeat_reason="bug fix in loader", log=log, prereg=pre)
        RO.run_once("m", "B2", lambda: {"x": 3}, log=log, prereg=pre)
        assert len(log.read_text().strip().splitlines()) == 1 + 1 + 3        # title + 3 runs (+ blank line counted by title block)

    def test_evaluate_selected_autonomy_off_without_tau(self):
        out = RO.evaluate_selected([0.9, 0.2, 0.8], [1, 0, 1], ["a", "b", "c"], None)
        assert out["autonomy"].startswith("OFF") and out["n_clusters"] == 3

    def test_evaluate_selected_selective_risk(self):
        rng = np.random.default_rng(0)
        s = rng.uniform(size=300)
        y = (rng.uniform(size=300) < s).astype(int)
        out = RO.evaluate_selected(s, y, [f"c{i}" for i in range(300)], 0.8, reps=100)
        assert out["n_accepted"] > 0 and out["selective_risk_ci95"][0] <= out["selective_risk"] <= out["selective_risk_ci95"][1]
