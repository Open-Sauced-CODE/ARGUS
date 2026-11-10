"""M2 must be compared with a (generator, rule) base-rate predictor; these tests pin the behaviour on synthetic data."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ml.train_m2.models import diagnostics as DG


def _meta(n=900, seed=0, informative=False):
    rng = np.random.default_rng(seed)
    gen = rng.choice(["sft", "rft_v2"], n)
    rule = rng.choice(["r1", "r2"], n)
    base = np.where(gen == "sft", 0.97, np.where(rule == "r1", 0.3, 0.8))
    hidden = rng.uniform(size=n)                                           # draft quality, visible to the model only if informative
    y = (hidden < base).astype(int)
    meta = pd.DataFrame({"input_key": [f"c{i % 300}" for i in range(n)], "generator": gen, "rule_id": rule, "y": y,
                         "oracle_class": np.where(y == 1, "minimal_correct", "wrong")})
    score = (base - hidden if informative else rng.uniform(size=n))      # base - hidden separates y exactly (cell rate AND draft quality)
    return meta, score


def test_cell_prior_uses_train_only_and_falls_back():
    tr = pd.DataFrame({"generator": ["a", "a", "b"], "rule_id": ["r", "r", "r"], "y": [1, 0, 1], "input_key": list("xyz")})
    ev = pd.DataFrame({"generator": ["a", "b", "c"], "rule_id": ["r", "q", "r"]})
    p = DG.cell_prior_scores(tr, ev)
    assert 0 < p[0] < 1 and p[1] == 1.0 and p[2] == tr["y"].mean()


def test_model_that_only_knows_the_cell_does_not_beat_prior():
    meta, _ = _meta()
    tr, ev = meta.iloc[:500], meta.iloc[500:].reset_index(drop=True)
    prior = DG.cell_prior_scores(tr, ev)
    res = DG.beats_prior(prior + np.random.default_rng(1).normal(0, 1e-3, len(prior)), prior, ev["y"], ev["input_key"], reps=200)
    assert not res["model_beats_prior"] and "does NOT beat" in DG.verdict_prior(res)


def test_model_with_real_draft_signal_beats_prior():
    meta, score = _meta(informative=True)
    tr, ev = meta.iloc[:500], meta.iloc[500:].reset_index(drop=True)
    res = DG.beats_prior(score[500:], DG.cell_prior_scores(tr, ev), ev["y"], ev["input_key"], reps=200)
    assert res["model_beats_prior"] and "adds signal" in DG.verdict_prior(res)


def test_stratified_auroc_marks_untestable_cells_and_negative_class_table():
    meta, score = _meta(informative=True)
    st = DG.stratified_auroc(score, meta["y"], meta, min_clusters=3, reps=50)
    assert any(r["auroc"] is not None for r in st)
    tiny = meta.iloc[:6].copy()
    assert all(r["auroc"] is None for r in DG.stratified_auroc(score[:6], tiny["y"], tiny, min_clusters=3))
    t = DG.negative_class_table(meta)
    assert set(t.columns) == {"generator", "oracle_class", "rows", "clusters"}
