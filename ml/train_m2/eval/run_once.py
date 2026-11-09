"""One-shot held-out evaluation (Shaurya-owned). Held-out sets are scored ONLY through run_once().

Refuses to run unless the pre-registration file exists, and refuses a second run of the same (model, set) without
--repeat-reason. Every run appends one line to ml/train_m2/eval/RUN_LOG_M2.md. Nothing here may be used to choose a
model, feature, threshold, calibrator or hyperparameter.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np

from ml.train_m2.models import metrics as M

LOG = Path(__file__).parent / "RUN_LOG_M2.md"
PREREG = Path(__file__).resolve().parents[1] / "PREREG_M2.md"


class RunOnceError(RuntimeError):
    pass


def _previous(log: Path, model: str, set_name: str) -> int:
    if not log.exists():
        return 0
    key = f"| {model} | {set_name} |"
    return sum(1 for l in log.read_text(encoding="utf-8").splitlines() if key in l)


def run_once(model_name: str, set_name: str, evaluator: Callable[[], dict[str, Any]], repeat_reason: str | None = None,
             log: Path = LOG, prereg: Path = PREREG) -> dict[str, Any]:
    if not prereg.exists() or not prereg.read_text(encoding="utf-8").strip():
        raise RunOnceError(f"pre-registration {prereg.name} is missing: commit it before any held-out evaluation")
    if _previous(log, model_name, set_name) and not repeat_reason:
        raise RunOnceError(f"({model_name}, {set_name}) was already evaluated; pass a repeat reason to run again")
    result = evaluator()
    log.parent.mkdir(parents=True, exist_ok=True)
    if not log.exists():
        log.write_text("# M2 held-out run log (append-only)\n\n", encoding="utf-8", newline="\n")
    line = (f"- {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} | {model_name} | {set_name} | "
            f"{json.dumps(result, sort_keys=True, default=str)} | repeat_reason={repeat_reason or '-'}\n")
    with open(log, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(line)
    return result


def evaluate_selected(scores, y, clusters, tau: float | None, reps: int = 1000) -> dict[str, Any]:
    """Metrics on ONE decision per cluster (already selected): AUROC, ECE, and selective risk at tau with a cluster bootstrap CI."""
    scores, y, clusters = np.asarray(scores, float), np.asarray(y, int), np.asarray(clusters)
    out: dict[str, Any] = {"n_clusters": int(len(np.unique(clusters))), "n_decisions": int(len(scores)),
                           "base_error_rate": float(1 - y.mean()) if len(y) else None, "auroc": M.auroc(scores, y),
                           "ece": M.ece(scores, y), "brier": M.brier(scores, y), "tau": tau}
    if tau is None:
        out["autonomy"] = "OFF (no certified threshold)"
        return out
    acc = scores >= tau
    out["n_accepted"] = int(acc.sum())
    out["coverage"] = float(acc.mean()) if len(acc) else None
    if acc.sum():
        wrong = 1 - y
        sr = lambda w, a: float(w[a].mean()) if a.sum() else float("nan")
        pt, lo, hi = M.cluster_bootstrap(lambda w, a: sr(w, a), clusters, wrong, acc, reps=reps)
        out["selective_risk"], out["selective_risk_ci95"] = pt, [lo, hi]
    return out
