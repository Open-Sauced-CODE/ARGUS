"""Selective-risk control: Learn-then-Test (fixed sequence) with a binomial test, one decision per cluster.

Guarantee (decisions are exchangeable clusters; the grid is fixed in advance; labels are the strict oracle):
with probability >= 1 - delta over the calibration draw, the returned threshold satisfies
    P(wrong | score >= tau) <= alpha        (selective risk, the quantity a customer cares about).
If nothing can be certified, tau is None and autonomy stays OFF.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.stats import beta, binom

# Pre-specified grid, independent of the data (descending = most conservative first).
GRID: tuple = tuple(sorted({round(float(x), 6) for x in np.concatenate(
    [np.linspace(0.50, 0.99, 99), 1.0 - np.logspace(-2, -5, 25)])}, reverse=True))


def rule_of_n(alpha: float, delta: float) -> int:
    """Smallest number of accepted clusters that can certify risk <= alpha with ZERO errors."""
    if not (0 < alpha < 1 and 0 < delta < 1):
        raise ValueError("alpha and delta must be in (0, 1)")
    return math.ceil(math.log(delta) / math.log(1.0 - alpha))


def cp_upper(k: int, n: int, delta: float) -> float:
    """One-sided Clopper-Pearson upper (1 - delta) confidence bound for a binomial proportion."""
    if n <= 0 or k >= n:
        return 1.0
    return float(beta.ppf(1.0 - delta, k + 1, n - k))


@dataclass(frozen=True)
class LTTResult:
    tau: float | None
    alpha: float
    delta: float
    n_total: int
    n_accepted: int
    n_errors: int
    ucb: float | None
    coverage: float
    certified: bool
    n_min: int
    path: tuple = field(default_factory=tuple)  # (tau, n_accepted, n_errors, p_value) per tested threshold


def ltt_threshold(scores, wrong, alpha: float = 0.05, delta: float = 0.05, grid: tuple = GRID) -> LTTResult:
    s = np.asarray(scores, dtype=float)
    w = np.asarray(wrong, dtype=bool)
    if s.ndim != 1 or s.shape != w.shape:
        raise ValueError("scores and wrong must be 1-D arrays of equal length")
    if np.isnan(s).any():
        raise ValueError("NaN score")
    n_min = rule_of_n(alpha, delta)
    path, best, started = [], None, False
    for tau in grid:  # descending
        acc = s >= tau
        n = int(acc.sum())
        if not started:
            if n < n_min:  # cannot be rejected yet; skipping depends on scores only, never on labels
                continue
            started = True
        k = int(w[acc].sum())
        p = float(binom.cdf(k, n, alpha))  # H0: selective risk > alpha
        path.append((tau, n, k, p))
        if p <= delta:
            best = (tau, n, k)
        else:
            break  # fixed-sequence testing: stop at the first failure
    if best is None:
        return LTTResult(None, alpha, delta, len(s), 0, 0, None, 0.0, False, n_min, tuple(path))
    tau, n, k = best
    return LTTResult(tau, alpha, delta, len(s), n, k, cp_upper(k, n, delta), n / len(s), True, n_min, tuple(path))


def crc_joint_threshold(scores, wrong, alpha: float = 0.05):
    """BASELINE ONLY (v3 section 7.6). Controls E[1(accepted and wrong)] <= alpha over ALL patches,
    NOT P(wrong | accepted), and only in expectation (no 1 - delta statement)."""
    s = np.asarray(scores, dtype=float)
    w = np.asarray(wrong, dtype=bool)
    n = len(s)
    for tau in np.unique(s):  # ascending: most accepting first
        if (np.sum((s >= tau) & w) + 1.0) / (n + 1.0) <= alpha:
            return float(tau)
    return None
