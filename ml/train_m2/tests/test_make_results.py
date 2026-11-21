"""Unit tests for ml/train_m2/eval/make_results.py (P6f Stage 2)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ml.train_m2.common import repo_root
from ml.train_m2.eval.make_results import (
    load_baseline_tests,
    load_crossfit_folds,
    load_heldout_results,
    load_licence_audit,
    load_mc_guarantee,
    load_parity_check,
    load_tau_star,
    render_phase6_results,
)


def test_load_functions_return_dicts_or_lists():
    root = repo_root()
    baseline = load_baseline_tests(root)
    assert isinstance(baseline, dict)
    assert "ml/tests" in baseline or "ml/train_m2/tests" in baseline

    folds = load_crossfit_folds(root)
    assert isinstance(folds, dict)
    assert folds.get("K") == 5

    tau = load_tau_star(root)
    assert isinstance(tau, dict)
    assert tau.get("alpha") == 0.05

    mc = load_mc_guarantee(root)
    assert isinstance(mc, list)
    assert len(mc) == 4

    parity = load_parity_check(root)
    assert isinstance(parity, dict)
    assert parity.get("status") == "PASS"

    lic = load_licence_audit(root)
    assert isinstance(lic, dict)
    assert "dependencies" in lic


def test_heldout_not_yet_run():
    root = repo_root()
    # Confirm held-out results do not exist in default state
    assert load_heldout_results(root) is None
    md = render_phase6_results(root)
    assert "held-out: not yet run" in md
    assert md.isascii()


def test_synthetic_heldout_rendered(tmp_path: Path):
    """When heldout results exist, they are rendered into the report."""
    root = tmp_path
    reports_dir = root / "ml" / "train_m2" / "out" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    heldout_file = reports_dir / "heldout_results.json"
    heldout_file.write_text(json.dumps({"eval_set": "B1", "auroc": 0.88}), encoding="utf-8")

    loaded = load_heldout_results(root)
    assert loaded == {"eval_set": "B1", "auroc": 0.88}

    md = render_phase6_results(root)
    assert "held-out: not yet run" not in md
    assert "eval_set" in md
    assert "0.88" in md


def test_numbers_come_from_input_files():
    root = repo_root()
    md = render_phase6_results(root)
    folds = load_crossfit_folds(root)
    assert str(folds["total_train_inputs"]) in md
    assert str(folds["seed"]) in md

    tau = load_tau_star(root)
    assert str(tau["n_total"]) in md
    assert str(tau["n_min"]) in md

    parity = load_parity_check(root)
    assert str(parity["total_rows_checked"]) in md
