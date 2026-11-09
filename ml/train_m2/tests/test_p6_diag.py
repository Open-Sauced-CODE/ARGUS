"""Diagnostics tests: a generator-confounded synthetic set must be flagged; a genuinely informative one must not."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ml.train_m2.features import registry as R
from ml.train_m2.models import diagnostics as DG


def _data(confounded: bool, n=800, seed=0):
    rng = np.random.default_rng(seed)
    X = pd.DataFrame(0.0, index=range(n), columns=R.names())
    gen = rng.choice(["sft", "rft_v2"], n, p=[0.7, 0.3])
    for g in ("sft", "rft_v2"):
        X[f"gen_{g}"] = (gen == g).astype(float)
    X["agreement_rate"] = rng.uniform(0, 1, n)
    if confounded:
        y = np.where(gen == "sft", 1, (rng.uniform(size=n) < 0.2).astype(int))
        X["agreement_rate"] = np.where(gen == "sft", 1.0, rng.uniform(0, 1, n))
    else:
        y = (rng.uniform(size=n) < 0.2 + 0.7 * X["agreement_rate"]).astype(int)
    meta = pd.DataFrame({"input_key": [f"c{i % 200}" for i in range(n)], "generator": gen, "y": y})
    return X, y, meta


def test_confounded_set_is_flagged_and_informative_set_is_not():
    for confounded, expect in ((True, True), (False, False)):
        X, y, meta = _data(confounded)
        tr, va = slice(0, 500), slice(500, 800)
        from ml.train_m2.models import zoo
        m = zoo.fit_logistic(X.iloc[tr], y[tr])
        pooled = DG.M.auroc(zoo.predict_logistic(m, X.iloc[va]), y[va])
        g = DG.generator_only_baseline(X.iloc[tr], y[tr], X.iloc[va], y[va])
        within = DG.within_generator(zoo.predict_logistic(m, X.iloc[va]), y[va], meta.iloc[va].reset_index(drop=True), reps=50)
        text = DG.verdict(pooled, g["auroc"], within, "sft")
        assert text.startswith("CONFOUNDED") == expect, (confounded, text)


def test_within_generator_single_class_is_reported_not_hidden():
    meta = pd.DataFrame({"input_key": list("abcd"), "generator": ["sft"] * 4, "y": [1, 1, 1, 1]})
    out = DG.within_generator([0.9, 0.8, 0.7, 0.6], [1, 1, 1, 1], meta, reps=10)
    assert out["sft"]["auroc"] is None and out["sft"]["n_negative_clusters"] == 0
    assert "cannot be assessed" in DG.verdict(0.99, 0.99, out, "sft")


def test_prevalence_and_ablation_and_single_feature():
    X, y, meta = _data(True)
    meta["partition"] = ["train"] * 500 + ["val"] * 300
    t = DG.prevalence_table(meta)
    assert set(t.columns) >= {"partition", "generator", "rows", "clusters", "negatives", "error_rate"}
    ab = DG.ablation(X.iloc[:500], y[:500], X.iloc[500:], y[500:], {"no_generator": DG.GEN_COLS})
    assert set(ab) == {"full", "no_generator"} and ab["full"]["n_features"] > ab["no_generator"]["n_features"]
    assert DG.single_feature_aurocs(X.iloc[:500], y[:500])[0][1] >= 0.5


def test_out_of_sample_calibration_runs():
    from ml.train_m2.models import train_m2 as T
    X, y, meta = _data(False, n=900)
    art, _ = T.fit_m2(X.iloc[:400], y[:400], X.iloc[400:650], y[400:650], meta.iloc[400:650], "sha")
    res = DG.out_of_sample_calibration(art, X.iloc[650:], y[650:], meta.iloc[650:].reset_index(drop=True))
    assert res["overall"]["n"] == 250 and "sft" in res and 0 <= res["overall"]["ece"] <= 1
