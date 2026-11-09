"""Decision engine for M2 (Shaurya-owned): the frozen interface confidence(features) -> p_hat and tau_star.

Order of rules in decide(): gate failed -> reject; escalate-only -> human_review (M2 not consulted); no certified tau ->
human_review; drift breaker not CLOSED -> human_review; out-of-distribution -> human_review; else
threshold_used = max(tau, bayes_cutoff) and p_hat >= threshold_used -> auto_apply (the stricter threshold wins).
tau changes ONLY through risk.calibrate_tau; set_cost_ratio never touches it. Explanations never contain identifiers.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping

import joblib
import numpy as np
import pandas as pd

from ml.train_m2.features import registry as R

_CACHE: dict[str, dict[str, Any]] = {}
_EXPL_PATH = Path(__file__).parent / "configs" / "explanations.json"


class FeatureSpecMismatch(Exception):
    """The feature vector was built with a different feature spec than the model was trained on."""


@dataclass(frozen=True)
class Contribution:
    feature: str
    value: float | None
    contribution: float
    text: str


@dataclass(frozen=True)
class Decision:
    action: str
    p_hat: float | None
    tau: float | None
    bayes_cutoff: float
    threshold_used: float | None
    reasons: tuple[str, ...]
    top_contributors: tuple[Contribution, ...]
    breaker_state: str
    model_version: str
    feature_spec_hash: str
    alpha: float
    delta: float
    cost_ratio: float


def load_model(path: str | Path) -> dict[str, Any]:
    key = str(path)
    if key not in _CACHE:
        _CACHE[key] = joblib.load(path)
    return _CACHE[key]


def bayes_cutoff(c_fa: float, c_esc: float) -> float:
    if not (c_fa > c_esc > 0):
        raise ValueError("require c_FA > c_esc > 0")
    return 1.0 - c_esc / c_fa


def set_cost_ratio(config: Mapping[str, Any], c_fa: float, c_esc: float) -> dict[str, Any]:
    """New config with a recomputed Bayes cutoff; tau is not part of the config and is never touched."""
    bayes_cutoff(c_fa, c_esc)
    new = dict(config)
    new["c_FA"], new["c_esc"] = float(c_fa), float(c_esc)
    return new


def _row(features: Mapping[str, Any], art: Mapping[str, Any]) -> pd.DataFrame:
    return pd.DataFrame([{n: (np.nan if features.get(n) is None else float(features[n])) for n in art["feature_names"]}],
                        columns=art["feature_names"])


def confidence(features: Mapping[str, Any], art: dict[str, Any] | None = None, model_path: str | Path | None = None) -> float:
    art = art or load_model(model_path)
    if features.get("spec_hash") != art["spec_hash"]:
        raise FeatureSpecMismatch(f"feature spec {str(features.get('spec_hash'))[:12]} != model spec {art['spec_hash'][:12]}")
    from ml.train_m2.models.train_m2 import predict
    return float(predict(art, _row(features, art))[0])


def is_ood(features: Mapping[str, Any], art: Mapping[str, Any], cfg: Mapping[str, Any]) -> bool:
    names = art["feature_names"]
    miss = sum(1 for n in names if features.get(n) is None) / len(names)
    if miss > cfg.get("ood_missing_frac", 0.30):
        return True
    m = cfg.get("ood_range_margin", 0.25)
    for n in names:
        v = features.get(n)
        lo, hi = art["train_min"].get(n), art["train_max"].get(n)
        if v is None or lo is None or hi is None or (isinstance(lo, float) and math.isnan(lo)):
            continue
        span = hi - lo
        if v < lo - m * span or v > hi + m * span:
            return True
    return False


def _text(name: str, value: float | None, up: bool, table: Mapping[str, Any]) -> str:
    ent = table.get(name) or table["_default"]
    return ent["up" if up else "down"].format(v=value if value is not None else float("nan"), name=name.replace("_", " "))


def explain(features: Mapping[str, Any], art: dict[str, Any], k: int = 5) -> list[Contribution]:
    X = _row(features, art)
    names = art["feature_names"]
    if art["kind"] == "lightgbm":
        contrib = art["model"].booster_.predict(X, pred_contrib=True)[0][:-1]
    else:
        pipe = art["model"]
        z = pipe.named_steps["sc"].transform(pipe.named_steps["imp"].transform(X))[0]
        contrib = pipe.named_steps["lr"].coef_[0] * z
    table = json.loads(_EXPL_PATH.read_text(encoding="utf-8"))
    order = np.argsort(-np.abs(contrib))[:k]
    return [Contribution(names[i], None if features.get(names[i]) is None else float(features[names[i]]), float(contrib[i]),
                         _text(names[i], features.get(names[i]), contrib[i] > 0, table)) for i in order]


def decide(features: Mapping[str, Any], *, gate_passed: bool, escalated_only: bool, breaker: str, config: Mapping[str, Any],
           tau_info: Mapping[str, Any], art: dict[str, Any] | None = None) -> Decision:
    art = art or load_model(config["model_path"])
    cutoff = bayes_cutoff(config["c_FA"], config["c_esc"])
    base = dict(bayes_cutoff=cutoff, breaker_state=breaker, model_version=config.get("model_version", "m2"),
                feature_spec_hash=art["spec_hash"], alpha=config["alpha"], delta=config["delta"],
                cost_ratio=config["c_FA"] / config["c_esc"], tau=tau_info.get("tau"))
    if not gate_passed:
        return Decision("reject", None, threshold_used=None, reasons=("gate failed",), top_contributors=(), **base)
    if escalated_only:
        return Decision("human_review", None, threshold_used=None, reasons=("escalate-only patch: M2 is not consulted",),
                        top_contributors=(), **base)
    p = confidence(features, art)
    contrib = tuple(explain(features, art))
    reasons: list[str] = []
    if not tau_info.get("certified"):
        reasons.append("no certified threshold: autonomy off")
    if breaker != "CLOSED":
        reasons.append("drift breaker is not closed")
    if is_ood(features, art, config):
        reasons.append("ood: input outside the training distribution")
    thr = None
    if tau_info.get("certified"):
        thr = max(float(tau_info["tau"]), cutoff)
    if not reasons and thr is not None and p >= thr:
        return Decision("auto_apply", p, threshold_used=thr, reasons=("confidence at or above both thresholds",),
                        top_contributors=contrib, **base)
    if not reasons:
        reasons.append(f"confidence {p:.3f} below the stricter threshold {thr:.3f}")
    return Decision("human_review", p, threshold_used=thr, reasons=tuple(reasons), top_contributors=contrib, **base)
