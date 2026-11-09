"""Model zoo for M2 (Shaurya-owned): standardised logistic regression and small monotone LightGBM. NaN handled natively/median."""
from __future__ import annotations

import numpy as np
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from ml.train_m2.features import registry as R


def fit_logistic(X, y, seed: int = 1337):
    pipe = Pipeline([("imp", SimpleImputer(strategy="median", keep_empty_features=True)), ("sc", StandardScaler()),
                     ("lr", LogisticRegression(C=1.0, max_iter=2000, random_state=seed))])
    return pipe.fit(X, y)


def predict_logistic(model, X) -> np.ndarray:
    return model.predict_proba(X)[:, 1]


def fit_lightgbm(X, y, X_val=None, y_val=None, seed: int = 1337):
    import lightgbm as lgb
    mono = R.monotone_vector(list(X.columns))
    params = dict(objective="binary", num_leaves=15, learning_rate=0.05, n_estimators=400, min_child_samples=5,
                  subsample=0.9, subsample_freq=1, colsample_bytree=0.9, reg_lambda=1.0, random_state=seed,
                  deterministic=True, force_row_wise=True, monotone_constraints=mono, verbose=-1, n_jobs=1)
    clf = lgb.LGBMClassifier(**params)
    if X_val is not None and len(np.unique(y_val)) == 2:
        clf.fit(X, y, eval_set=[(X_val, y_val)], eval_metric="binary_logloss",
                callbacks=[lgb.early_stopping(30, verbose=False)])
    else:
        clf.set_params(n_estimators=150).fit(X, y)
    return clf


def predict_lightgbm(model, X) -> np.ndarray:
    return model.predict_proba(X)[:, 1]
