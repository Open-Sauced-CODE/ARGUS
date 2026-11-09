"""Certify the auto-apply threshold on the CAL partition (Shaurya-owned). Uses ltt.py unchanged. No silent fallback:
if fewer than rule_of_n natural clusters exist, certified=false and autonomy stays OFF."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from ml.train_m2.risk import ltt
from ml.train_m2.risk.decisions import select_decisions


def calibrate(scores, wrong, alpha: float = 0.05, delta: float = 0.05) -> dict[str, Any]:
    scores, wrong = np.asarray(scores, float), np.asarray(wrong, int)
    n_min = ltt.rule_of_n(alpha, delta)
    res = ltt.ltt_threshold(scores, wrong, alpha=alpha, delta=delta)
    out: dict[str, Any] = {"alpha": alpha, "delta": delta, "n_total": int(len(scores)), "n_min": int(n_min),
                           "certified": bool(res.certified and len(scores) >= n_min), "tau": res.tau if res.certified else None,
                           "ucb": res.ucb, "coverage": res.coverage, "n_accepted": res.n_accepted, "n_errors": res.n_errors}
    if len(scores) < n_min:
        out["certified"], out["tau"] = False, None
        out["message"] = (f"only {len(scores)} calibration clusters; need >= {n_min} for alpha={alpha}, delta={delta}: "
                          "autonomy stays OFF (no certified threshold)")
    out["grid_sha256"] = hashlib.sha256(json.dumps(list(ltt.GRID)).encode()).hexdigest()
    return out


def run(frame, art: dict[str, Any], splits_sha: str, alpha: float = 0.05, delta: float = 0.05, generator: str = "sft") -> dict[str, Any]:
    """frame: CAL-partition rows with columns input_key, sample_idx, generator, score, y (1 = strictly correct)."""
    from ml.train_m2.features import registry as R
    if art["splits_sha256"] != splits_sha:
        raise AssertionError("splits hash differs from the model card: refusing to calibrate")
    if art["spec_hash"] != R.spec_hash():
        raise AssertionError("feature spec hash differs from the model card: refusing to calibrate")
    sel = select_decisions(frame[frame["generator"] == generator])
    out = calibrate(sel["score"].to_numpy(), (1 - sel["y"]).to_numpy(), alpha, delta)
    out.update({"generator": generator, "splits_sha256": splits_sha, "feature_spec_hash": art["spec_hash"],
                "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "n_clusters_without_candidate": None})
    return out


def write(out: dict[str, Any], path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(out, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8", newline="\n")
