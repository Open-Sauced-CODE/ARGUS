"""Metrics with cluster-bootstrap confidence intervals (Shaurya-owned). Resampling is ALWAYS over clusters."""
from __future__ import annotations

import math
from typing import Callable, Sequence

import numpy as np
from scipy.stats import rankdata


def log_loss(p, y, eps: float = 1e-6) -> float:
    p = np.clip(np.asarray(p, float), eps, 1 - eps)
    y = np.asarray(y, float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def brier(p, y) -> float:
    return float(np.mean((np.asarray(p, float) - np.asarray(y, float)) ** 2))


def ece(p, y, bins: int = 15, equal_mass: bool = True) -> float:
    p, y = np.asarray(p, float), np.asarray(y, float)
    if len(p) == 0:
        return float("nan")
    order = np.argsort(p)
    chunks = np.array_split(order, min(bins, len(p))) if equal_mass else \
        [np.where((p >= lo) & (p < hi + (1e-12 if hi == 1 else 0)))[0] for lo, hi in zip(np.linspace(0, 1, bins + 1)[:-1], np.linspace(0, 1, bins + 1)[1:])]
    return float(sum(len(c) / len(p) * abs(p[c].mean() - y[c].mean()) for c in chunks if len(c)))


def mce(p, y, bins: int = 15) -> float:
    p, y = np.asarray(p, float), np.asarray(y, float)
    chunks = np.array_split(np.argsort(p), min(bins, len(p)))
    return float(max((abs(p[c].mean() - y[c].mean()) for c in chunks if len(c)), default=float("nan")))


def auroc(p, y) -> float:
    p, y = np.asarray(p, float), np.asarray(y, int)
    n1, n0 = int(y.sum()), int((1 - y).sum())
    if n1 == 0 or n0 == 0:
        return float("nan")
    r = rankdata(p)
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def risk_coverage_curve(p, wrong) -> tuple[np.ndarray, np.ndarray]:
    """Selective risk (error among accepted) vs coverage, accepting highest scores first."""
    order = np.argsort(-np.asarray(p, float), kind="stable")
    w = np.asarray(wrong, float)[order]
    cov = np.arange(1, len(w) + 1) / len(w)
    return cov, np.cumsum(w) / np.arange(1, len(w) + 1)


def aurc(p, wrong) -> float:
    cov, risk = risk_coverage_curve(p, wrong)
    return float(np.mean(risk)) if len(risk) else float("nan")


def cluster_bootstrap(metric: Callable[..., float], clusters: Sequence[str], *arrays, reps: int = 1000, seed: int = 1337,
                      level: float = 0.95) -> tuple[float, float, float]:
    """(point, lo, hi): resample whole clusters with replacement, keep all rows of a drawn cluster."""
    clusters = np.asarray(clusters)
    arrays = [np.asarray(a) for a in arrays]
    point = metric(*arrays)
    uniq = np.unique(clusters)
    idx_by = {c: np.where(clusters == c)[0] for c in uniq}
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(reps):
        draw = rng.choice(uniq, size=len(uniq), replace=True)
        idx = np.concatenate([idx_by[c] for c in draw])
        v = metric(*[a[idx] for a in arrays])
        if not (isinstance(v, float) and math.isnan(v)):
            vals.append(v)
    if not vals:
        return point, float("nan"), float("nan")
    a = (1 - level) / 2
    return point, float(np.quantile(vals, a)), float(np.quantile(vals, 1 - a))
