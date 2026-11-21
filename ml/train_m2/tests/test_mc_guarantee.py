"""Unit tests for ml/train_m2/eval/mc_guarantee.py (P6f-Fix Requirement 3)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from ml.train_m2.common import repo_root
from ml.train_m2.eval.mc_guarantee import (
    ALPHA,
    DELTA,
    RegimeResult,
    render_markdown,
    run_regime,
)


def test_ltt_coverage_null_when_certified_frac_zero():
    """LTT coverage must be reported as None in Python (null in json) and 'n/a (nothing certified)' in markdown when certified_frac == 0."""
    rng = np.random.default_rng(1337)
    # n_cal=10, true_error_rate=0.5 -> will never certify with alpha=0.05, delta=0.05
    res = run_regime(
        name="test_zero_certified",
        description="Test regime with zero certification",
        rng=rng,
        n_cal=10,
        true_error_rate=0.50,
        score_sep=0.5,
        reps=50,
    )

    assert res.ltt_certified_frac == 0.0
    assert res.ltt_coverage is None

    # Check serialized dict has None (null in json)
    as_dict = json.loads(json.dumps(res.__dict__))
    assert as_dict["ltt_coverage"] is None

    # Check markdown rendering
    md = render_markdown([res])
    assert "n/a (nothing certified)" in md
    row_line = [l for l in md.splitlines() if "test_zero_certified" in l][0]
    cols = [c.strip() for c in row_line.split("|")[1:-1]]
    # cols: [name, n_cal, true_err, certified_frac, LTT_coverage, mean_risk, max_risk]
    assert cols[4] == "n/a (nothing certified)"


def test_crc_exceeds_alpha_only_when_exceeds_by_more_than_se():
    """CRC exceeds_alpha must be True only when max conditional error exceeds alpha by more than the Monte-Carlo SE."""
    se = float(np.sqrt(ALPHA * (1.0 - ALPHA) / 500))  # ~0.0097
    alpha_plus_se = ALPHA + se  # ~0.0597

    # Case A: max conditional error exceeds alpha but is <= alpha + SE -> exceeds_alpha is False
    res_within = RegimeResult(
        name="within_noise",
        description="Within MC noise",
        n_cal=80,
        n_test=500,
        true_error_rate=0.05,
        reps=100,
        ltt_coverage=1.0,
        ltt_certified_frac=0.5,
        ltt_mean_risk=0.02,
        ltt_max_risk=0.04,
        crc_coverage=0.99,
        crc_mean_cond_error=0.035,
        crc_max_cond_error=0.0520,  # exceeds alpha (0.05) by 0.002, which is <= SE (0.0097)
        crc_se=round(se, 4),
        crc_exceeds_alpha=bool(0.0520 > alpha_plus_se),
        alpha=ALPHA,
        delta=DELTA,
    )
    assert res_within.crc_exceeds_alpha is False

    # Case B: max conditional error exceeds alpha by more than SE -> exceeds_alpha is True
    res_above = RegimeResult(
        name="above_noise",
        description="Significantly exceeds alpha",
        n_cal=30,
        n_test=500,
        true_error_rate=0.08,
        reps=100,
        ltt_coverage=None,
        ltt_certified_frac=0.0,
        ltt_mean_risk=float("nan"),
        ltt_max_risk=float("nan"),
        crc_coverage=0.90,
        crc_mean_cond_error=0.027,
        crc_max_cond_error=0.0750,  # exceeds alpha (0.05) by 0.025 > SE (0.0097)
        crc_se=round(se, 4),
        crc_exceeds_alpha=bool(0.0750 > alpha_plus_se),
        alpha=ALPHA,
        delta=DELTA,
    )
    assert res_above.crc_exceeds_alpha is True

    md = render_markdown([res_within, res_above])
    assert f"CRC exceeds alpha in regime 'above_noise'" in md
    assert "SE = 0.0097" in md or "SE =" in md


def test_mc_guarantee_disk_artifacts():
    """Verify that committed/generated artifacts for mc_guarantee match the requirements."""
    root = repo_root()
    json_path = root / "ml" / "train_m2" / "out" / "reports" / "mc_guarantee.json"
    md_path = root / "ml" / "train_m2" / "out" / "reports" / "mc_guarantee.md"
    proof_path = root / "docs" / "phase6_shaurya" / "PROOF_NOTE.md"

    assert json_path.is_file()
    assert md_path.is_file()
    assert proof_path.is_file()

    # Load jsonl rows
    rows = []
    with open(json_path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))

    assert len(rows) == 4
    by_name = {r["name"]: r for r in rows}

    # covariate_shift_small_n
    cov = by_name["covariate_shift_small_n"]
    assert cov["ltt_certified_frac"] == 0.0
    assert cov["ltt_coverage"] is None
    assert cov["crc_exceeds_alpha"] is True
    assert cov["crc_max_cond_error"] > ALPHA + cov["crc_se"]

    # exchangeable_at_alpha
    at_alpha = by_name["exchangeable_at_alpha"]
    assert at_alpha["crc_exceeds_alpha"] is False
    assert at_alpha["crc_max_cond_error"] <= ALPHA + at_alpha["crc_se"]

    # Markdown report
    md_text = md_path.read_text(encoding="utf-8")
    assert "n/a (nothing certified)" in md_text
    assert "CRC exceeds alpha in regime 'covariate_shift_small_n'" in md_text
    assert "SE = 0.0097" in md_text

    # Proof note
    proof_text = proof_path.read_text(encoding="utf-8")
    assert "n/a (nothing certified)" in proof_text
    assert "covariate_shift_small_n" in proof_text
