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
    if tau:
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
    if tau:
        assert str(tau["n_total"]) in md
        assert str(tau["n_min"]) in md
    else:
        assert "tau_star.json not available." in md

    parity = load_parity_check(root)
    assert str(parity["total_rows_checked"]) in md


def test_synthetic_tau_star_rendered(tmp_path: Path):
    """When tau_star.json exists, its numbers are rendered into the report."""
    root = tmp_path
    tau_file = root / "ml" / "train_m2" / "out" / "tau_star.json"
    tau_file.parent.mkdir(parents=True, exist_ok=True)
    tau_file.write_text(
        json.dumps({
            "certified": False,
            "alpha": 0.05,
            "delta": 0.05,
            "n_total": 50,
            "n_min": 59,
            "tau": None,
            "message": "test-tau-msg",
        }),
        encoding="utf-8",
    )
    loaded = load_tau_star(root)
    assert loaded["alpha"] == 0.05
    assert loaded["n_min"] == 59

    md = render_phase6_results(root)
    assert "test-tau-msg" in md
    assert "50" in md
    assert "59" in md


def test_corrupt_files_handled_gracefully(tmp_path: Path):
    """Corrupted json files do not crash the loaders or renderer."""
    root = tmp_path
    reports_dir = root / "ml" / "train_m2" / "out" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    # Write broken JSON files
    (reports_dir / "mc_guarantee.json").write_text("{corrupt json", encoding="utf-8")
    (reports_dir / "parity_500.json").write_text("not json at all", encoding="utf-8")
    (reports_dir / "licence_audit.json").write_text("---broken---", encoding="utf-8")

    tau_file = root / "ml" / "train_m2" / "out" / "tau_star.json"
    tau_file.write_text("{'invalid': json}", encoding="utf-8")

    assert load_mc_guarantee(root) == []
    assert load_parity_check(root) == {}
    assert load_licence_audit(root) == {}
    assert load_tau_star(root) == {}

    # Renderer should succeed even with corrupted inputs
    md = render_phase6_results(root)
    assert "Phase 6 Results Summary" in md
    assert "tau_star.json not available." in md
    assert "parity_500.json not available." in md


def test_visible_pending_section_when_run_log_absent():
    """When RUN_LOG_M2.md is absent, render_phase6_results outputs a visible PENDING section for held-out and certification."""
    root = repo_root()
    run_log = root / "ml" / "train_m2" / "eval" / "RUN_LOG_M2.md"
    assert not run_log.exists(), "RUN_LOG_M2.md must not exist prior to Stage 3"

    md = render_phase6_results(root)
    assert "Held-Out Evaluation Status (PENDING)" in md
    assert "### Status: PENDING" in md
    assert "### Certification Status: PENDING" in md
    assert "Certification: PENDING" in md
    assert md.isascii()

