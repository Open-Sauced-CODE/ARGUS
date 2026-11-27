"""Unit tests for ml/train_m2/eval/preflight_heldout.py (P6h).

Verifies:
  - Each individual failing condition makes preflight exit non-zero / report failure
  - All-pass case succeeds (exit 0)
  - Preflight NEVER opens or reads any held-out file (verified via monkeypatched open)
  - run_once integration requires preflight pass
"""
from __future__ import annotations

import builtins
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from ml.train_m2.common import repo_root
from ml.train_m2.eval import preflight_heldout as PH
from ml.train_m2.eval import run_once as RO
from ml.train_m2.splits import splits_hash


@pytest.fixture
def clean_preflight_env(tmp_path: Path) -> dict[str, Any]:
    """Sets up a minimal valid synthetic repository tree for preflight testing."""
    root = tmp_path / "repo"
    root.mkdir()

    # 1. RUN_LOG_M2 absent by default
    eval_dir = root / "ml" / "train_m2" / "eval"
    eval_dir.mkdir(parents=True)

    # 2. Artifacts and PREFLIGHT_HASHES
    m2_out = root / "ml" / "train_m2" / "out" / "m2"
    m2_out.mkdir(parents=True)
    out_dir = root / "ml" / "train_m2" / "out"

    (m2_out / "m2.joblib").write_bytes(b"dummy_m2_binary_content")
    (m2_out / "model_card.json").write_text('{"model": "card"}', encoding="utf-8")
    (m2_out / "val_metrics.json").write_text('{"auroc": 0.9}', encoding="utf-8")
    (out_dir / "tau_star.json").write_text('{"certified": false}', encoding="utf-8")

    # Minimal valid splits with matching hash
    valid_splits = {
        "parts": {"train": ["k1"], "val": ["k2"], "cal": ["k3"], "test": ["k4"]},
        "family": {"k1": "fam", "k2": "fam", "k3": "fam", "k4": "fam"},
        "seed": 1337,
        "fracs": [0.6, 0.2, 0.2],
    }
    s_hash = splits_hash(valid_splits)
    valid_splits["sha256"] = s_hash
    (m2_out / "splits.json").write_text(json.dumps(valid_splits), encoding="utf-8")

    # PREFLIGHT_HASHES.json
    docs_dir = root / "docs" / "phase6_shaurya"
    docs_dir.mkdir(parents=True)
    import hashlib
    hashes = {
        "m2.joblib": {"path": "ml/train_m2/out/m2/m2.joblib", "sha256": hashlib.sha256(b"dummy_m2_binary_content").hexdigest().upper()},
        "model_card.json": {"path": "ml/train_m2/out/m2/model_card.json", "sha256": hashlib.sha256(b'{"model": "card"}').hexdigest().upper()},
        "splits.json": {"path": "ml/train_m2/out/m2/splits.json", "sha256": hashlib.sha256(json.dumps(valid_splits).encode("utf-8")).hexdigest().upper()},
        "val_metrics.json": {"path": "ml/train_m2/out/m2/val_metrics.json", "sha256": hashlib.sha256(b'{"auroc": 0.9}').hexdigest().upper()},
        "tau_star.json": {"path": "ml/train_m2/out/tau_star.json", "sha256": hashlib.sha256(b'{"certified": false}').hexdigest().upper()},
    }
    (docs_dir / "PREFLIGHT_HASHES.json").write_text(json.dumps(hashes), encoding="utf-8")

    # HELDOUT_DECISION.md (human-authored in production; synthetic fixture here)
    decision_text = (
        "# Held-Out Decision\n"
        "Decided by: Shaurya (human)\n"
        "Decision: PATH B (S4 not certified)\n"
        "Date: 2026-11-23\n"
        "Clean Cluster Count: 15\n"
    )
    (docs_dir / "HELDOUT_DECISION.md").write_text(decision_text, encoding="utf-8")

    # EXPERIMENT_PLAN_M2.md
    plan_text = "# Experiment Plan\n## 12. Change log\n- Log entry\n## 13. Appendix A\n"
    plan_path = root / "ml" / "train_m2" / "EXPERIMENT_PLAN_M2.md"
    plan_path.write_text(plan_text, encoding="utf-8")

    return {
        "root": root,
        "valid_splits": valid_splits,
        "expected_splits_hash": s_hash,
    }


def test_preflight_all_pass_synthetic(clean_preflight_env: dict[str, Any]):
    """Synthetic environment with all valid conditions passes preflight."""
    root = clean_preflight_env["root"]
    s_hash = clean_preflight_env["expected_splits_hash"]

    with patch("ml.train_m2.eval.preflight_heldout.EXPECTED_PLAN_SPLITS_SHA", s_hash):
        passed, results = PH.run_preflight(
            root=root,
            skip_test_suites=True,
            skip_git_checks=True,
        )
        assert passed, f"Preflight failed unexpectedly: {[r for r in results if not r.passed]}"
        assert all(r.passed for r in results)


def test_preflight_fails_if_run_log_exists(clean_preflight_env: dict[str, Any]):
    """Preflight fails if RUN_LOG_M2.md exists."""
    root = clean_preflight_env["root"]
    (root / "ml" / "train_m2" / "eval" / "RUN_LOG_M2.md").write_text("entry", encoding="utf-8")

    res = PH.check_run_log_absent(root)
    assert not res.passed
    assert "RUN_LOG_M2.md exists" in res.detail


def test_preflight_fails_if_unallowed_dirty_file(tmp_path: Path):
    """Preflight fails if working tree contains unallowed dirty files."""
    fake_proc = MagicMock()
    fake_proc.stdout = " M ml/train_m2/some_file.py\n"

    with patch("subprocess.run", return_value=fake_proc):
        res = PH.check_working_tree_clean(tmp_path)
        assert not res.passed
        assert "Unallowed dirty files" in res.detail


def test_preflight_allows_crossfit_notebook_in_working_tree(tmp_path: Path):
    """Preflight ignores the permitted crossfit notebook."""
    fake_proc = MagicMock()
    fake_proc.stdout = " M ml/train_m1/notebooks/01_sft_crossfit.ipynb\n"

    with patch("subprocess.run", return_value=fake_proc):
        res = PH.check_working_tree_clean(tmp_path)
        assert res.passed


def test_preflight_fails_if_artifact_hash_mismatches(clean_preflight_env: dict[str, Any]):
    """Preflight fails if an artifact hash on disk does not match PREFLIGHT_HASHES.json."""
    root = clean_preflight_env["root"]
    (root / "ml" / "train_m2" / "out" / "m2" / "m2.joblib").write_bytes(b"tampered_binary")

    res = PH.check_artifact_hashes(root)
    assert not res.passed
    assert "Hash mismatch" in res.detail


def test_preflight_fails_if_splits_hash_corrupted(clean_preflight_env: dict[str, Any]):
    """Preflight fails if splits.json internal hash is mismatched."""
    root = clean_preflight_env["root"]
    splits_file = root / "ml" / "train_m2" / "out" / "m2" / "splits.json"
    splits = json.loads(splits_file.read_text(encoding="utf-8"))
    splits["sha256"] = "wrong_sha256"
    splits_file.write_text(json.dumps(splits), encoding="utf-8")

    res = PH.check_splits_hash(root)
    assert not res.passed
    assert "Splits internal hash mismatch" in res.detail


def test_preflight_fails_if_heldout_decision_missing(clean_preflight_env: dict[str, Any]):
    """Preflight fails if HELDOUT_DECISION.md is missing."""
    root = clean_preflight_env["root"]
    (root / "docs" / "phase6_shaurya" / "HELDOUT_DECISION.md").unlink()

    res = PH.check_heldout_decision(root)
    assert not res.passed
    assert "HELDOUT_DECISION.md not found" in res.detail


def test_preflight_fails_if_heldout_decision_ambiguous(clean_preflight_env: dict[str, Any]):
    """Preflight fails if HELDOUT_DECISION.md contains both PATH A and PATH B."""
    root = clean_preflight_env["root"]
    (root / "docs" / "phase6_shaurya" / "HELDOUT_DECISION.md").write_text(
        "Decided by: Shaurya (human)\nPATH A (OOF ingested)\nPATH B (S4 not certified)\nDate: 2026-11-23\nCount: 15\n",
        encoding="utf-8",
    )

    res = PH.check_heldout_decision(root)
    assert not res.passed
    assert "Must state exactly one" in res.detail


def test_preflight_fails_without_decided_by_line(clean_preflight_env: dict[str, Any]):
    """Preflight fails if HELDOUT_DECISION.md lacks 'Decided by: Shaurya (human)'."""
    root = clean_preflight_env["root"]
    (root / "docs" / "phase6_shaurya" / "HELDOUT_DECISION.md").write_text(
        "PATH B (S4 not certified)\nDate: 2026-11-23\nClean Cluster Count: 15\n",
        encoding="utf-8",
    )

    res = PH.check_heldout_decision(root)
    assert not res.passed
    assert "Decided by: Shaurya (human)" in res.detail


def test_preflight_fails_with_path_b_alone(clean_preflight_env: dict[str, Any]):
    """Preflight fails if HELDOUT_DECISION.md contains PATH B alone."""
    root = clean_preflight_env["root"]
    (root / "docs" / "phase6_shaurya" / "HELDOUT_DECISION.md").write_text(
        "PATH B (S4 not certified)\n",
        encoding="utf-8",
    )

    res = PH.check_heldout_decision(root)
    assert not res.passed


def test_preflight_fails_without_date_line(clean_preflight_env: dict[str, Any]):
    """Preflight fails if HELDOUT_DECISION.md lacks a Date: YYYY-MM-DD line."""
    root = clean_preflight_env["root"]
    (root / "docs" / "phase6_shaurya" / "HELDOUT_DECISION.md").write_text(
        "Decided by: Shaurya (human)\nPATH B (S4 not certified)\nClean Cluster Count: 15\n",
        encoding="utf-8",
    )

    res = PH.check_heldout_decision(root)
    assert not res.passed
    assert "Date:" in res.detail


def test_preflight_fails_if_path_a_missing_report(clean_preflight_env: dict[str, Any]):
    """Preflight fails if PATH A is selected but no ingest_oof report exists."""
    root = clean_preflight_env["root"]
    (root / "docs" / "phase6_shaurya" / "HELDOUT_DECISION.md").write_text(
        "Decided by: Shaurya (human)\n**Decision:** PATH A (OOF ingested)\nDate: 2026-11-23\n**Clean Cluster Count:** 72\n",
        encoding="utf-8",
    )

    res = PH.check_heldout_decision(root)
    assert not res.passed
    assert "no ingest_oof report found" in res.detail


def test_preflight_fails_if_path_a_clean_clusters_below_claimed(clean_preflight_env: dict[str, Any]):
    """Preflight fails if PATH A report has fewer clean clusters than claimed."""
    root = clean_preflight_env["root"]
    (root / "docs" / "phase6_shaurya" / "HELDOUT_DECISION.md").write_text(
        "Decided by: Shaurya (human)\n**Decision:** PATH A (OOF ingested)\nDate: 2026-11-23\n**Clean Cluster Count:** 72\n",
        encoding="utf-8",
    )
    rep_dir = root / "ml" / "train_m2" / "out" / "reports"
    rep_dir.mkdir(parents=True, exist_ok=True)
    (rep_dir / "oof_unseen_clean.json").write_text(
        json.dumps({"unseen_clean_count": 50}), encoding="utf-8"
    )

    res = PH.check_heldout_decision(root)
    assert not res.passed
    assert "clean clusters 50 < claimed 72" in res.detail


def test_preflight_fails_if_target_pair_already_in_ledger(clean_preflight_env: dict[str, Any]):
    """Preflight fails if target (model, set) pair is already in RUN_LOG_M2.md."""
    root = clean_preflight_env["root"]
    log = root / "ml" / "train_m2" / "eval" / "RUN_LOG_M2.md"
    log.write_text("- 2026-11-23T00:00:00Z | sft | B1 | {}\n", encoding="utf-8")

    res = PH.check_ledger_pairs(root, pairs=[("sft", "B1")])
    assert not res.passed
    assert "already contains entry" in res.detail


def test_preflight_fails_if_diff_outside_section12(clean_preflight_env: dict[str, Any]):
    """Preflight fails if EXPERIMENT_PLAN_M2.md diff touches lines before or after Section 12."""
    root = clean_preflight_env["root"]

    # 1. Diff before Section 12 fails
    diff_before = "@@ -1,1 +1,1 @@\n- old line\n+ new line\n"
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=diff_before, returncode=0)
        res = PH.check_plan_diff_section12(root)
        assert not res.passed
        assert "before Section 12" in res.detail

    # 2. Diff after Section 12 (in Section 13) fails
    diff_after = "@@ -4,1 +4,1 @@\n- old line\n+ new line\n"
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=diff_after, returncode=0)
        res = PH.check_plan_diff_section12(root)
        assert not res.passed
        assert "beyond Section 12" in res.detail

    # 3. Diff strictly inside Section 12 passes
    diff_inside = "@@ -3,1 +3,1 @@\n- Log entry\n+ Log entry 2\n"
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=diff_inside, returncode=0)
        res = PH.check_plan_diff_section12(root)
        assert res.passed
        assert "contained within Section 12" in res.detail


def test_preflight_never_opens_any_heldout_file(clean_preflight_env: dict[str, Any]):
    """Preflight MUST NEVER open or read any held-out data file."""
    root = clean_preflight_env["root"]
    s_hash = clean_preflight_env["expected_splits_hash"]

    orig_open = builtins.open
    heldout_tokens = ["held_out", "tierb", "tierc", "c_verifier", "gold", "c-human"]

    def guarded_open(file, *args, **kwargs):
        path_str = str(file).lower().replace("\\", "/")
        for token in heldout_tokens:
            if token in path_str and not path_str.endswith("heldout_decision.md"):
                raise AssertionError(f"Preflight attempted to open forbidden held-out path: {file}")
        return orig_open(file, *args, **kwargs)

    with patch("builtins.open", side_effect=guarded_open), \
         patch("ml.train_m2.eval.preflight_heldout.EXPECTED_PLAN_SPLITS_SHA", s_hash):
        passed, results = PH.run_preflight(
            root=root,
            skip_test_suites=True,
            skip_git_checks=True,
        )
        assert passed


def test_run_once_calls_preflight_and_blocks_scoring(clean_preflight_env: dict[str, Any]):
    """run_once calls require_preflight_pass and aborts before executing evaluator if checks fail."""
    root = clean_preflight_env["root"]
    eval_called = False

    def dummy_evaluator():
        nonlocal eval_called
        eval_called = True
        return {"metric": 1.0}

    # Preflight fails because RUN_LOG_M2.md exists
    (root / "ml" / "train_m2" / "eval" / "RUN_LOG_M2.md").write_text("existing log", encoding="utf-8")

    with patch("ml.train_m2.eval.run_once.LOG", root / "ml" / "train_m2" / "eval" / "RUN_LOG_M2.md"), \
         patch("ml.train_m2.eval.run_once.PREREG", root / "ml" / "train_m2" / "PREREG_M2.md"), \
         pytest.raises(RO.RunOnceError, match="Preflight held-out checks failed"):
        RO.run_once(
            "sft",
            "B1",
            dummy_evaluator,
            root=root,
            require_preflight=True,
            skip_test_suites_in_preflight=True,
        )

    assert not eval_called, "Evaluator was called despite preflight failure!"
