"""Grouped CV and gate-only certification tests (synthetic)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ml.train_m2.features import registry as R
from ml.train_m2.models import diagnostics as DG


def _data(n_clusters=120, per=4, seed=0, informative=True):
    rng = np.random.default_rng(seed)
    rows = []
    for c in range(n_clusters):
        gen = "rft_v2" if c % 2 else "sft"
        rule = "r1" if c % 3 else "r2"
        q = rng.uniform()
        for s in range(per):
            ok = int(rng.uniform() < (0.97 if gen == "sft" else 0.2 + 0.7 * q))
            rows.append({"input_key": f"c{c}", "generator": gen, "rule_id": rule, "sample_idx": s, "y": ok,
                         "oracle_class": "minimal_correct" if ok else ("wrong" if rng.uniform() < .8 else "valid_not_minimal"), "q": q})
    meta = pd.DataFrame(rows)
    X = pd.DataFrame(0.0, index=range(len(meta)), columns=R.names())
    X["agreement_rate"] = meta["q"].to_numpy() if informative else rng.uniform(size=len(meta))
    for g in ("sft", "rft_v2"):
        X[f"gen_{g}"] = (meta["generator"] == g).astype(float)
    return X, meta.drop(columns="q")


def test_folds_are_by_cluster_and_deterministic():
    X, meta = _data()
    a, b = DG.grouped_cv(X, meta, 5, 1337), DG.grouped_cv(X, meta, 5, 1337)
    assert a["fold"].equals(b["fold"])
    assert (a.groupby("input_key")["fold"].nunique() == 1).all()           # a cluster never straddles folds
    assert a["score_m2"].notna().all() and a["score_prior"].notna().all()


def test_each_fold_model_is_fitted_without_its_own_fold(monkeypatch):
    X, meta = _data()
    sizes = []
    orig = DG.zoo.fit_logistic
    monkeypatch.setattr(DG.zoo, "fit_logistic", lambda Xtr, ytr, seed=1337: (sizes.append(len(Xtr)), orig(Xtr, ytr, seed))[1])
    DG.grouped_cv(X, meta, 5, 1337)
    assert len(sizes) == 5 and all(n < len(X) for n in sizes)


def test_informative_feature_beats_prior_inside_generator_and_noise_does_not():
    for informative in (True, False):
        X, meta = _data(informative=informative, n_clusters=200)
        rep = DG.cv_report(DG.grouped_cv(X, meta, 5, 1337), reps=200)
        assert rep["by_generator"]["rft_v2"]["model_beats_prior"] == informative, (informative, rep["by_generator"]["rft_v2"])


def test_single_class_is_skipped_not_crashed():
    X, meta = _data(n_clusters=10)
    meta["y"] = 1
    out = DG.grouped_cv(X, meta, 5, 1337)
    assert out["score_m2"].isna().all() and DG.cv_report(out)["rows"] == 0


def test_clopper_pearson_and_gate_only_table():
    assert DG.cp_upper(0, 15) == pytest.approx(1 - 0.05 ** (1 / 15))
    assert DG.cp_upper(0, 59) < 0.0501 and DG.cp_upper(3, 3) == 1.0 and DG.cp_upper(0, 0) == 1.0
    X, meta = _data()
    tab = DG.gate_only_table(meta, lambda g, k: int(k[1:]) % 4 == 0)
    get = lambda scope: next(r for r in tab if r["generator"] == "sft" and r["scope"] == scope)
    assert get("seen")["clusters"] + get("unseen")["clusters"] == get("all")["clusters"]
    assert get("unseen")["clean_clusters_still_needed_for_alpha"] in (None, max(0, 59 - get("unseen")["clusters"]))
    assert get("all")["harmful_errors"] <= get("all")["strict_errors"]


def test_below_chance_prior_cannot_be_beaten_by_a_chance_model():
    rng = np.random.default_rng(0)
    n = 400
    keys = np.array([f"c{i // 2}" for i in range(n)])
    y = (rng.uniform(size=n) < 0.5).astype(int)
    prior = np.where(y == 1, 0.4, 0.6) + rng.normal(0, 0.01, n)             # anti-informative prior (AUROC well below 0.5)
    model = rng.uniform(size=n)                                             # chance
    res = DG.beats_prior(model, prior, y, keys, reps=200)
    assert res["auroc_prior"] < 0.2 and res["diff_ci95"][0] > 0 and res["model_beats_prior"] is False


def test_too_few_negative_clusters_is_insufficient_evidence_not_a_win():
    y = np.array([1] * 40 + [0] * 3)
    s = np.array([0.9] * 40 + [0.1] * 3)
    res = DG.beats_prior(s, np.full(43, 0.5), y, np.array([f"c{i}" for i in range(43)]), reps=100)
    assert res["evidence_ok"] is False and res["model_beats_prior"] is False
    assert DG.verdict_prior(res).startswith("INSUFFICIENT EVIDENCE")
