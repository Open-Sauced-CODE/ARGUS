"""Calibrators fit on VAL only (Shaurya-owned): isotonic, Platt, Beta, inductive Venn-Abers. All monotone in p."""
from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

EPS = 1e-6


def _logit(p):
    p = np.clip(np.asarray(p, float), EPS, 1 - EPS)
    return np.log(p / (1 - p))


class Isotonic:
    name = "isotonic"

    def fit(self, p, y):
        self.m = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(p, y)
        return self

    def predict(self, p):
        return np.clip(self.m.predict(np.asarray(p, float)), 0.0, 1.0)


class Platt:
    name = "platt"

    def fit(self, p, y):
        self.m = LogisticRegression(C=1e6, max_iter=1000).fit(_logit(p).reshape(-1, 1), y)
        return self

    def predict(self, p):
        return self.m.predict_proba(_logit(p).reshape(-1, 1))[:, 1]


class BetaCal:
    """Beta calibration (Kull et al.): logistic regression on [ln p, -ln(1-p)] (3 parameters)."""
    name = "beta"

    @staticmethod
    def _x(p):
        p = np.clip(np.asarray(p, float), EPS, 1 - EPS)
        return np.column_stack([np.log(p), -np.log(1 - p)])

    def fit(self, p, y):
        self.m = LogisticRegression(C=1e6, max_iter=1000).fit(self._x(p), y)
        return self

    def predict(self, p):
        return self.m.predict_proba(self._x(p))[:, 1]


class VennAbers:
    """Inductive Venn-Abers: two isotonic fits with the query point added as label 0 and 1; returns p1 / (1 - p0 + p1)."""
    name = "venn_abers"

    def fit(self, p, y):
        self.p, self.y = np.asarray(p, float), np.asarray(y, float)
        return self

    def predict(self, q):
        out = []
        for x in np.asarray(q, float):
            pp, yy = np.append(self.p, x), None
            lo = IsotonicRegression(out_of_bounds="clip").fit(pp, np.append(self.y, 0.0)).predict([x])[0]
            hi = IsotonicRegression(out_of_bounds="clip").fit(pp, np.append(self.y, 1.0)).predict([x])[0]
            out.append(hi / (1.0 - lo + hi))
        return np.clip(np.asarray(out), 0.0, 1.0)


CALIBRATORS = {"isotonic": Isotonic, "platt": Platt, "beta": BetaCal, "venn_abers": VennAbers}


def fit_all(p_val, y_val) -> dict[str, Any]:
    y = np.asarray(y_val)
    if len(np.unique(y)) < 2:
        return {}
    return {n: c().fit(p_val, y) for n, c in CALIBRATORS.items()}
