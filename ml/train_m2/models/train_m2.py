"""Fit M2 (Shaurya-owned). Reads TRAIN and VAL only; never test or cal. Selection by VAL log-loss (then ECE).

Artifact (joblib): model, kind, calibrator (or None), calibrator_name, feature_names, spec_hash, splits_sha256,
train_min/train_max (OOD guard), label_definition, seed. Degenerate cases are flagged, never hidden:
`calibrated=False` if VAL has a single class.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from ml.train_m2.features import registry as R
from ml.train_m2.models import calibrate as C
from ml.train_m2.models import metrics as M
from ml.train_m2.models import zoo

LABEL_DEFINITION = "strict_minimal_correct_v1"


def raw_predict(art: dict[str, Any], X: pd.DataFrame) -> np.ndarray:
    X = X[art["feature_names"]]
    return zoo.predict_lightgbm(art["model"], X) if art["kind"] == "lightgbm" else zoo.predict_logistic(art["model"], X)


def predict(art: dict[str, Any], X: pd.DataFrame) -> np.ndarray:
    p = raw_predict(art, X)
    return art["calibrator"].predict(p) if art.get("calibrator") is not None else p


def fit_m2(X_tr, y_tr, X_va, y_va, meta_va, splits_sha: str, seed: int = 1337) -> tuple[dict[str, Any], dict[str, Any]]:
    names = list(X_tr.columns)
    models = {"logistic": zoo.fit_logistic(X_tr, y_tr, seed), "lightgbm": zoo.fit_lightgbm(X_tr, y_tr, X_va, y_va, seed)}
    preds = {"logistic": zoo.predict_logistic(models["logistic"], X_va), "lightgbm": zoo.predict_lightgbm(models["lightgbm"], X_va)}
    report: dict[str, Any] = {"val_n": int(len(y_va)), "val_clusters": int(meta_va["input_key"].nunique()),
                              "val_pos": int(np.sum(y_va)), "val_neg": int(len(y_va) - np.sum(y_va)), "models": {}}
    for k, p in preds.items():
        report["models"][k] = {"log_loss": M.log_loss(p, y_va), "ece": M.ece(p, y_va), "brier": M.brier(p, y_va),
                               "auroc": M.auroc(p, y_va)}
    kind = min(report["models"], key=lambda k: (report["models"][k]["log_loss"], report["models"][k]["ece"]))
    p_val = preds[kind]
    cals = C.fit_all(p_val, y_va)
    calibrated = bool(cals)
    cal_report = {}
    for n, c in cals.items():
        q = c.predict(p_val)
        cal_report[n] = {"log_loss": M.log_loss(q, y_va), "ece": M.ece(q, y_va), "brier": M.brier(q, y_va)}
    best = min(cal_report, key=lambda n: (cal_report[n]["log_loss"], cal_report[n]["ece"])) if cal_report else None
    art = {"model": models[kind], "kind": kind, "calibrator": cals.get(best) if best else None, "calibrator_name": best,
           "calibrated": calibrated, "feature_names": names, "spec_hash": R.spec_hash(), "splits_sha256": splits_sha,
           "train_min": X_tr.min().to_dict(), "train_max": X_tr.max().to_dict(), "label_definition": LABEL_DEFINITION,
           "seed": seed}
    report.update({"selected_model": kind, "calibrators": cal_report, "selected_calibrator": best, "calibrated": calibrated,
                   "warning": None if calibrated else "VAL has a single class: probabilities are NOT calibrated"})
    return art, report


def save(art: dict[str, Any], report: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(art, out_dir / "m2.joblib")
    card = {k: v for k, v in art.items() if k not in ("model", "calibrator", "train_min", "train_max")}
    (out_dir / "model_card.json").write_text(json.dumps(card, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8", newline="\n")
    (out_dir / "val_metrics.json").write_text(json.dumps(report, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8", newline="\n")
