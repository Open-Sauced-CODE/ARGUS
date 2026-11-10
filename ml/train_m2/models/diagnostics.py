"""Confounding and calibration diagnostics for M2 (Shaurya-owned). TRAIN / VAL / CAL only; never a held-out set.

Why: M2's pooled AUROC can be near 1 simply because negatives come from one generator (e.g. rft_v2) and positives from
another (collapsed SFT/RFT with agreement ~1). These functions measure how much of the score is generator identity and how
much survives inside one generator, and they evaluate calibration OUT of the sample it was fitted on.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from ml.train_m2.features import registry as R
from ml.train_m2.models import metrics as M
from ml.train_m2.models import zoo

GEN_COLS = [f"gen_{g}" for g in R.GENERATORS]


def prevalence_table(meta: pd.DataFrame, partition_col: str = "partition") -> pd.DataFrame:
    """Rows, clusters, negatives and error rate per (partition, generator)."""
    g = meta.groupby([partition_col, "generator"])
    t = g.agg(rows=("y", "size"), clusters=("input_key", "nunique"), negatives=("y", lambda s: int((1 - s).sum()))).reset_index()
    t["error_rate"] = t["negatives"] / t["rows"]
    return t


def generator_only_baseline(X_tr, y_tr, X_va, y_va) -> dict[str, Any]:
    """AUROC of a model that sees ONLY the generator one-hot. If it is close to the full model, M2 is a generator detector."""
    cols = [c for c in GEN_COLS if c in X_tr.columns]
    m = zoo.fit_logistic(X_tr[cols], y_tr)
    p = zoo.predict_logistic(m, X_va[cols])
    return {"auroc": M.auroc(p, y_va), "log_loss": M.log_loss(p, y_va), "n_val": int(len(y_va))}


def single_feature_aurocs(X: pd.DataFrame, y, top: int = 10) -> list[tuple[str, float]]:
    out = []
    for c in X.columns:
        v = X[c].to_numpy(float)
        if np.isnan(v).all() or np.nanstd(v) == 0:
            continue
        a = M.auroc(np.nan_to_num(v, nan=np.nanmedian(v)), y)
        if not np.isnan(a):
            out.append((c, max(a, 1 - a)))
    return sorted(out, key=lambda t: -t[1])[:top]


def within_generator(scores, y, meta: pd.DataFrame, reps: int = 500) -> dict[str, dict[str, Any]]:
    """AUROC per generator with a cluster bootstrap CI; 'n_negative_clusters' says how much evidence the number rests on."""
    scores, y = np.asarray(scores, float), np.asarray(y, int)
    out: dict[str, dict[str, Any]] = {}
    for g, idx in meta.groupby("generator").groups.items():
        i = np.asarray([meta.index.get_loc(k) for k in idx])
        yy, ss, cc = y[i], scores[i], meta["input_key"].to_numpy()[i]
        neg_clusters = int(len(set(cc[yy == 0])))
        if neg_clusters == 0 or (yy == 1).sum() == 0:
            out[g] = {"auroc": None, "n": int(len(i)), "n_negative_clusters": neg_clusters, "note": "single class"}
            continue
        pt, lo, hi = M.cluster_bootstrap(M.auroc, cc, ss, yy, reps=reps)
        out[g] = {"auroc": pt, "ci95": [lo, hi], "n": int(len(i)), "n_negative_clusters": neg_clusters}
    return out


def ablation(X_tr, y_tr, X_va, y_va, drop: Mapping[str, Sequence[str]]) -> dict[str, dict[str, float]]:
    """Val AUROC / log-loss of the logistic model with feature subsets removed (drop = {label: [columns]})."""
    out = {}
    for label, cols in {"full": [], **dict(drop)}.items():
        keep = [c for c in X_tr.columns if c not in set(cols)]
        m = zoo.fit_logistic(X_tr[keep], y_tr)
        p = zoo.predict_logistic(m, X_va[keep])
        out[label] = {"auroc": M.auroc(p, y_va), "log_loss": M.log_loss(p, y_va), "n_features": len(keep)}
    return out


def out_of_sample_calibration(art: Mapping[str, Any], X_cal, y_cal, meta_cal: pd.DataFrame) -> dict[str, Any]:
    """ECE / Brier / reliability of the calibrated model on CAL (the calibrator was fitted on VAL), overall and per generator."""
    from ml.train_m2.models.train_m2 import predict
    p = predict(art, X_cal)
    y = np.asarray(y_cal, int)
    res: dict[str, Any] = {"overall": {"n": int(len(y)), "negatives": int((1 - y).sum()), "ece": M.ece(p, y), "brier": M.brier(p, y)}}
    for g, idx in meta_cal.groupby("generator").indices.items():
        res[g] = {"n": int(len(idx)), "negatives": int((1 - y[idx]).sum()), "ece": M.ece(p[idx], y[idx]) if len(idx) else None,
                  "mean_score": float(p[idx].mean()), "observed_correct": float(y[idx].mean())}
    return res


def verdict(pooled_auroc: float, generator_only_auroc: float, within: Mapping[str, Mapping[str, Any]], deployment: str = "sft") -> str:
    """One honest sentence from the numbers (no softening)."""
    dep = within.get(deployment, {})
    if generator_only_auroc >= 0.9 * pooled_auroc:
        base = (f"CONFOUNDED: a model that sees only the generator reaches AUROC {generator_only_auroc:.3f} against {pooled_auroc:.3f} for "
                "the full model, so the pooled score mostly identifies the generator.")
    else:
        base = f"the generator alone explains less of the signal (AUROC {generator_only_auroc:.3f} vs {pooled_auroc:.3f})."
    if dep.get("auroc") is None:
        return base + f" The deployment generator ({deployment}) has {dep.get('n_negative_clusters', 0)} negative cluster(s) here: its discrimination cannot be assessed."
    return base + (f" Within {deployment}: AUROC {dep['auroc']:.3f} (95% CI {dep['ci95'][0]:.3f}-{dep['ci95'][1]:.3f}) on "
                   f"{dep['n_negative_clusters']} negative cluster(s).")


# ---------------------------------------------------------------------------------------------------------------------
# Does M2 beat "who wrote it and which rule is it"?  (P6c)
# ---------------------------------------------------------------------------------------------------------------------
def cell_prior_scores(meta_train: pd.DataFrame, meta_eval: pd.DataFrame) -> np.ndarray:
    """Smoothed P(correct) per (generator, rule) cell from TRAIN only; falls back to the generator rate, then the global rate."""
    glob = float(meta_train["y"].mean())
    cell = meta_train.groupby(["generator", "rule_id"])["y"].agg(["sum", "count"])
    gen = meta_train.groupby("generator")["y"].mean()
    out = []
    for g, r in zip(meta_eval["generator"], meta_eval["rule_id"]):
        if (g, r) in cell.index:
            s, c = cell.loc[(g, r)]
            out.append((s + glob) / (c + 1.0))
        else:
            out.append(float(gen.get(g, glob)))
    return np.asarray(out, float)


def beats_prior(p_model, p_prior, y, clusters, reps: int = 1000, seed: int = 1337) -> dict[str, Any]:
    """AUROC of the model and of the prior on the same rows, plus a cluster-bootstrap CI of the difference (model - prior)."""
    p_model, p_prior, y = np.asarray(p_model, float), np.asarray(p_prior, float), np.asarray(y, int)
    diff = lambda a, b, yy: M.auroc(a, yy) - M.auroc(b, yy)
    pt, lo, hi = M.cluster_bootstrap(diff, clusters, p_model, p_prior, y, reps=reps, seed=seed)
    return {"auroc_model": M.auroc(p_model, y), "auroc_prior": M.auroc(p_prior, y), "diff": pt, "diff_ci95": [lo, hi],
            "model_beats_prior": bool(lo > 0)}


def stratified_auroc(scores, y, meta: pd.DataFrame, by=("generator", "rule_id"), min_clusters: int = 3, reps: int = 300) -> list[dict[str, Any]]:
    """AUROC inside each (generator, rule) cell that has >= min_clusters positive AND negative clusters; others are listed as untestable."""
    scores, y = np.asarray(scores, float), np.asarray(y, int)
    ck = meta["input_key"].to_numpy()
    rows = []
    for key, idx in meta.groupby(list(by)).indices.items():
        yy, ss, cc = y[idx], scores[idx], ck[idx]
        pos_c, neg_c = len(set(cc[yy == 1])), len(set(cc[yy == 0]))
        rec: dict[str, Any] = {"cell": "/".join(map(str, key)), "positive_clusters": pos_c, "negative_clusters": neg_c, "rows": int(len(idx))}
        if pos_c >= min_clusters and neg_c >= min_clusters:
            pt, lo, hi = M.cluster_bootstrap(M.auroc, cc, ss, yy, reps=reps)
            rec.update({"auroc": pt, "ci95": [lo, hi]})
        else:
            rec["auroc"] = None
        rows.append(rec)
    return sorted(rows, key=lambda r: -r["negative_clusters"])


def negative_class_table(meta: pd.DataFrame) -> pd.DataFrame:
    """Negatives split by oracle class (wrong vs valid_not_minimal) per generator: shows whether 'errors' are harmful or just thorough."""
    neg = meta[meta["y"] == 0]
    return neg.groupby(["generator", "oracle_class"])["input_key"].agg(rows="size", clusters="nunique").reset_index()


def verdict_prior(res: Mapping[str, Any]) -> str:
    if res["model_beats_prior"]:
        return (f"M2 adds signal beyond the (generator, rule) base rate: AUROC {res['auroc_model']:.3f} vs {res['auroc_prior']:.3f} "
                f"(difference {res['diff']:+.3f}, 95% cluster-bootstrap CI {res['diff_ci95'][0]:+.3f} to {res['diff_ci95'][1]:+.3f}).")
    return (f"M2 does NOT beat a (generator, rule) base-rate predictor: AUROC {res['auroc_model']:.3f} vs {res['auroc_prior']:.3f} "
            f"(difference {res['diff']:+.3f}, 95% CI {res['diff_ci95'][0]:+.3f} to {res['diff_ci95'][1]:+.3f}). Its score is who-and-what, not draft quality.")
