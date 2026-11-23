"""Tests for ml/train_m2/eval/post_oof.py (P6g post-OOF dry-run pipeline).

Tests:
  - End-to-end execution on synthetic fixture in dry-run mode
  - Case: cal clusters < rule_of_n (n < 59) -> certified false -> auto-apply OFF
  - Case: cal clusters >= rule_of_n (n >= 59) -> certified true -> tau certified
  - Real mode refuses to run without --i-understand
  - Real mode refuses to run if RUN_LOG_M2.md exists
  - No writes occur outside the specified out_dir in dry-run mode
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ml.train_m2.common import repo_root
from ml.train_m2.eval.post_oof import (
    check_execution_guards,
    emit_changelog_entry,
    ingest_step,
    load_base_splits,
    main,
    resplit_proposal_step,
    run_post_oof,
)
from ml.train_m2.features import registry as R


@pytest.fixture
def synthetic_base_splits() -> dict:
    """Fixture providing minimal valid splits dictionary."""
    clusters = {f"k_{i}": "cis.iam_no_full_admin" for i in range(100)}
    train_keys = [f"k_{i}" for i in range(50)]
    val_keys = [f"k_{i}" for i in range(50, 70)]
    cal_keys = [f"k_{i}" for i in range(70, 90)]
    test_keys = [f"k_{i}" for i in range(90, 100)]

    splits = {
        "parts": {"train": train_keys, "val": val_keys, "cal": cal_keys, "test": test_keys},
        "family": clusters,
        "seed": 1337,
        "fracs": [0.6, 0.2, 0.2],
        "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    }
    return splits


@pytest.fixture
def synthetic_train_data() -> dict:
    """Synthetic feature frames for model fitting."""
    feature_names = [s.name for s in R.REGISTRY]
    rng = np.random.RandomState(1337)
    n_tr, n_va = 30, 15

    X_tr = pd.DataFrame(rng.randn(n_tr, len(feature_names)), columns=feature_names)
    y_tr = rng.choice([0, 1], size=n_tr, p=[0.2, 0.8])

    X_va = pd.DataFrame(rng.randn(n_va, len(feature_names)), columns=feature_names)
    y_va = rng.choice([0, 1], size=n_va, p=[0.2, 0.8])
    meta_va = pd.DataFrame({"input_key": [f"va_{i}" for i in range(n_va)], "y": y_va})

    return {
        "X_tr": X_tr,
        "y_tr": y_tr,
        "X_va": X_va,
        "y_va": y_va,
        "meta_va": meta_va,
    }


def test_post_oof_dry_run_cal_clusters_below_rule_of_n(
    tmp_path: Path, synthetic_base_splits: dict, synthetic_train_data: dict
):
    """Case 1: cal clusters < rule_of_n (n=30 < 59) -> certified False -> auto-apply OFF."""
    out_dir = tmp_path / "dry_run_out"
    cal_scores = np.linspace(0.80, 0.99, 30)
    cal_wrong = np.zeros(30, dtype=int)  # 0 errors

    fixture = {
        "counts": {
            "total_clusters": 5,
            "unseen_clean_count": 5,
            "unseen_clean_clusters": [f"k_{i}" for i in range(5)],
        },
        "base_splits": synthetic_base_splits,
        "train_data": synthetic_train_data,
        "cal_data": {
            "scores": cal_scores,
            "wrong": cal_wrong,
        },
    }

    result = run_post_oof(
        dry_run=True,
        out_dir=out_dir,
        generator="sft",
        synthetic_fixture=fixture,
    )

    # 1. Output files exist in out_dir
    assert (out_dir / "oof_unseen_clean.json").is_file()
    assert (out_dir / "re_split_proposal.json").is_file()
    assert (out_dir / "re_split_proposal.md").is_file()
    assert (out_dir / "m2" / "m2.joblib").is_file()
    assert (out_dir / "m2" / "model_card.json").is_file()
    assert (out_dir / "tau_star.json").is_file()

    # 2. Check tau_star results: certified must be False because 30 < 59
    tau_info = result["tau_info"]
    assert tau_info["certified"] is False
    assert tau_info["tau"] is None
    assert tau_info["n_total"] == 30
    assert tau_info["n_min"] == 59
    assert "autonomy stays OFF" in tau_info["message"]

    # 3. Changelog entry reflects certified: false
    changelog = result["changelog_entry"]
    assert "tau certified: false" in changelog
    assert "n_cal=30" in changelog
    assert "tau=null" in changelog


def test_post_oof_dry_run_cal_clusters_meeting_rule_of_n(
    tmp_path: Path, synthetic_base_splits: dict, synthetic_train_data: dict
):
    """Case 2: cal clusters >= rule_of_n (n=65 >= 59) with 0 errors -> certified True."""
    out_dir = tmp_path / "dry_run_out_certified"
    cal_scores = np.linspace(0.85, 0.99, 65)
    cal_wrong = np.zeros(65, dtype=int)  # 0 errors on clean calibration set

    fixture = {
        "counts": {
            "total_clusters": 10,
            "unseen_clean_count": 10,
            "unseen_clean_clusters": [f"k_{i}" for i in range(10)],
        },
        "base_splits": synthetic_base_splits,
        "train_data": synthetic_train_data,
        "cal_data": {
            "scores": cal_scores,
            "wrong": cal_wrong,
        },
    }

    result = run_post_oof(
        dry_run=True,
        out_dir=out_dir,
        generator="sft",
        synthetic_fixture=fixture,
    )

    tau_info = result["tau_info"]
    assert tau_info["certified"] is True
    assert tau_info["tau"] is not None
    assert isinstance(tau_info["tau"], float)
    assert tau_info["n_total"] == 65

    changelog = result["changelog_entry"]
    assert "tau certified: true" in changelog
    assert "n_cal=65" in changelog


def test_real_mode_refuses_without_i_understand(tmp_path: Path):
    """Real mode (--no-dry-run) must raise RuntimeError if --i-understand is absent."""
    with pytest.raises(RuntimeError, match="--i-understand is required"):
        check_execution_guards(dry_run=False, i_understand=False, root=tmp_path)


def test_real_mode_refuses_if_run_log_exists(tmp_path: Path):
    """Real mode must raise RuntimeError if RUN_LOG_M2.md already exists."""
    run_log = tmp_path / "ml" / "train_m2" / "eval" / "RUN_LOG_M2.md"
    run_log.parent.mkdir(parents=True, exist_ok=True)
    run_log.write_text("existing log entry\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="RUN_LOG_M2.md already exists"):
        check_execution_guards(dry_run=False, i_understand=True, root=tmp_path)


def test_dry_run_does_not_modify_production_m2_out(tmp_path: Path, synthetic_base_splits: dict, synthetic_train_data: dict):
    """Verify dry-run mode never touches files under ml/train_m2/out/m2/."""
    out_dir = tmp_path / "custom_out"
    fixture = {
        "counts": {"total_clusters": 0, "unseen_clean_count": 0, "unseen_clean_clusters": []},
        "base_splits": synthetic_base_splits,
        "train_data": synthetic_train_data,
        "cal_data": {"scores": np.array([0.9]), "wrong": np.array([0])},
    }

    run_post_oof(
        dry_run=True,
        out_dir=out_dir,
        generator="sft",
        synthetic_fixture=fixture,
    )

    # Everything was written into out_dir
    assert (out_dir / "tau_star.json").is_file()
    assert (out_dir / "re_split_proposal.json").is_file()
    assert (out_dir / "m2" / "m2.joblib").is_file()


def test_emit_changelog_entry_format():
    """Verify changelog row matches EXPERIMENT_PLAN_M2.md section 12 table format."""
    entry = emit_changelog_entry(
        splits_sha="abcdef1234567890abcdef",
        tau_info={"certified": False, "n_total": 50, "tau": None},
        generator="sft",
        date_str="2026-11-22",
    )
    assert entry.startswith("| 2026-11-22 |")
    assert "Re-split post-OOF harvest (splits sha256 abcdef1234567890)" in entry
    assert "tau certified: false (n_cal=50, tau=null)" in entry
    assert "OOF harvest ingested to close S4" in entry
    assert entry.endswith("| no |")


def test_resplit_proposal_empty_clean_clusters_matches_base_splits(tmp_path: Path):
    """When zero new clean clusters are provided, re-split proposal reproduces base splits exactly."""
    root = repo_root()
    base_splits = load_base_splits(root)
    out_dir = tmp_path / "resplit_identity"

    prop = resplit_proposal_step(base_splits, [], out_dir)

    assert prop["sha256"] == base_splits["sha256"]
    assert len(prop["parts"]["train"]) == len(base_splits["parts"]["train"]) == 105
    assert len(prop["parts"]["val"]) == len(base_splits["parts"]["val"]) == 34
    assert len(prop["parts"]["cal"]) == len(base_splits["parts"]["cal"]) == 50
    assert len(prop["parts"]["test"]) == len(base_splits["parts"]["test"]) == 132
    assert (out_dir / "re_split_proposal.json").is_file()
    assert (out_dir / "re_split_proposal.md").is_file()


def test_ingest_step_with_corrupt_harvest_raises_assertion(tmp_path: Path):
    """Corrupt OOF harvest where fold assignment is violated raises AssertionError."""
    root = repo_root()
    folds_path = root / "docs" / "phase6_shaurya" / "crossfit" / "folds.json"
    folds = json.loads(folds_path.read_text(encoding="utf-8"))
    # Pick a real train key assigned to fold 0
    fold_0_key = folds["folds"]["0"]["input_keys"][0]

    # Create corrupt harvest directory where fold_0_key claims crossfit_fold = 1
    harvest_dir = tmp_path / "corrupt_harvest"
    harvest_dir.mkdir(parents=True)
    corrupt_part = harvest_dir / "part-00000.jsonl"
    corrupt_row = {
        "input_key": fold_0_key,
        "crossfit_fold": 1,  # Mismatch: assigned to 0, claims 1
        "generator": "sft",
    }
    corrupt_part.write_text(json.dumps(corrupt_row) + "\n", encoding="utf-8")

    out_dir = tmp_path / "corrupt_out"
    with pytest.raises(AssertionError, match="crossfit_fold=1 but assigned to fold 0"):
        ingest_step(harvest_dir, folds_path, out_dir)


def test_compute_cp_min_n():
    """Verify Clopper-Pearson minimum n calculation matches analytical values."""
    from ml.train_m2.eval.post_oof import compute_cp_min_n
    assert compute_cp_min_n(0) == 59
    assert compute_cp_min_n(1) == 93
    assert compute_cp_min_n(2) == 124
    assert compute_cp_min_n(3) == 153
    assert compute_cp_min_n(4) == 181


def test_partial_oof_two_folds_k0_sufficient():
    """2 folds present with k=0 errors: 72 + 15 = 87 >= 59 -> SUFFICIENT."""
    from ml.train_m2.eval.post_oof import evaluate_partial_oof

    # 37 clean clusters for fold 0, 35 for fold 1
    fold_mem = {}
    key_flags = {}
    rows = []

    for i in range(37):
        ik = f"f0_clean_{i}"
        fold_mem[ik] = 0
        key_flags[ik] = {"in_heldout": False, "in_a_val": False}
        rows.append({"input_key": ik, "crossfit_fold": 0, "sample_idx": 0, "gate_pass": True, "oracle_class": "minimal_correct"})

    for i in range(35):
        ik = f"f1_clean_{i}"
        fold_mem[ik] = 1
        key_flags[ik] = {"in_heldout": False, "in_a_val": False}
        rows.append({"input_key": ik, "crossfit_fold": 1, "sample_idx": 0, "gate_pass": True, "oracle_class": "minimal_correct"})

    res = evaluate_partial_oof(rows, fold_mem, key_flags, existing_unseen_clean=15)
    assert res["folds_present"] == [0, 1]
    assert res["oof_clean_count"] == 72
    assert res["total_clean_clusters"] == 87
    assert res["k"] == 0
    assert res["cp_min_n"] == 59
    assert res["verdict"] == "SUFFICIENT"
    assert res["needed_more"] == 0
    assert res["remaining_folds"] == [2, 3, 4]
    assert res["covering_folds"] == []


def test_partial_oof_two_folds_k1_needs_more():
    """2 folds present with k=1 error: 87 < 93 -> NEED 6 MORE CLEAN CLUSTERS, covered by fold 2 (30)."""
    from ml.train_m2.eval.post_oof import evaluate_partial_oof

    fold_mem = {}
    key_flags = {}
    rows = []

    for i in range(37):
        ik = f"f0_clean_{i}"
        fold_mem[ik] = 0
        key_flags[ik] = {"in_heldout": False, "in_a_val": False}
        # 1 gate-passing wrong draft in fold 0
        oc = "wrong" if i == 0 else "minimal_correct"
        rows.append({"input_key": ik, "crossfit_fold": 0, "sample_idx": 0, "gate_pass": True, "oracle_class": oc})

    for i in range(35):
        ik = f"f1_clean_{i}"
        fold_mem[ik] = 1
        key_flags[ik] = {"in_heldout": False, "in_a_val": False}
        rows.append({"input_key": ik, "crossfit_fold": 1, "sample_idx": 0, "gate_pass": True, "oracle_class": "minimal_correct"})

    res = evaluate_partial_oof(rows, fold_mem, key_flags, existing_unseen_clean=15)
    assert res["folds_present"] == [0, 1]
    assert res["oof_clean_count"] == 72
    assert res["total_clean_clusters"] == 87
    assert res["k"] == 1
    assert res["cp_min_n"] == 93
    assert res["verdict"] == "NEED 6 MORE CLEAN CLUSTERS"
    assert res["needed_more"] == 6
    assert res["remaining_folds"] == [2, 3, 4]
    assert res["covering_folds"] == [2]
    assert "Remaining fold(s) [2] provide 30 clean clusters" in res["covering_status"]


def test_partial_oof_two_folds_k2_needs_more():
    """2 folds present with k=2 errors: 87 < 124 -> NEED 37 MORE CLEAN CLUSTERS, covered by folds [2, 3] (30+33=63)."""
    from ml.train_m2.eval.post_oof import evaluate_partial_oof

    fold_mem = {}
    key_flags = {}
    rows = []

    for i in range(37):
        ik = f"f0_clean_{i}"
        fold_mem[ik] = 0
        key_flags[ik] = {"in_heldout": False, "in_a_val": False}
        oc = "wrong" if i < 2 else "minimal_correct"
        rows.append({"input_key": ik, "crossfit_fold": 0, "sample_idx": 0, "gate_pass": True, "oracle_class": oc})

    for i in range(35):
        ik = f"f1_clean_{i}"
        fold_mem[ik] = 1
        key_flags[ik] = {"in_heldout": False, "in_a_val": False}
        rows.append({"input_key": ik, "crossfit_fold": 1, "sample_idx": 0, "gate_pass": True, "oracle_class": "minimal_correct"})

    res = evaluate_partial_oof(rows, fold_mem, key_flags, existing_unseen_clean=15)
    assert res["folds_present"] == [0, 1]
    assert res["oof_clean_count"] == 72
    assert res["total_clean_clusters"] == 87
    assert res["k"] == 2
    assert res["cp_min_n"] == 124
    assert res["verdict"] == "NEED 37 MORE CLEAN CLUSTERS"
    assert res["needed_more"] == 37
    assert res["remaining_folds"] == [2, 3, 4]
    assert res["covering_folds"] == [2, 3]
    assert "Remaining fold(s) [2, 3] provide 63 clean clusters" in res["covering_status"]


def test_partial_oof_five_folds_k2_sufficient():
    """5 folds present with k=2 errors: 168 + 15 = 183 >= 124 -> SUFFICIENT."""
    from ml.train_m2.eval.post_oof import evaluate_partial_oof

    fold_counts = {0: 37, 1: 35, 2: 30, 3: 33, 4: 33}
    fold_mem = {}
    key_flags = {}
    rows = []

    k_assigned = 0
    for fold_idx, n_clusters in fold_counts.items():
        for i in range(n_clusters):
            ik = f"f{fold_idx}_clean_{i}"
            fold_mem[ik] = fold_idx
            key_flags[ik] = {"in_heldout": False, "in_a_val": False}
            if k_assigned < 2:
                oc = "wrong"
                k_assigned += 1
            else:
                oc = "minimal_correct"
            rows.append({"input_key": ik, "crossfit_fold": fold_idx, "sample_idx": 0, "gate_pass": True, "oracle_class": oc})

    res = evaluate_partial_oof(rows, fold_mem, key_flags, existing_unseen_clean=15)
    assert res["folds_present"] == [0, 1, 2, 3, 4]
    assert res["oof_clean_count"] == 168
    assert res["total_clean_clusters"] == 183
    assert res["k"] == 2
    assert res["cp_min_n"] == 124
    assert res["verdict"] == "SUFFICIENT"
    assert res["remaining_folds"] == []


def test_partial_oof_heldout_and_aval_overlap_strictly_excluded():
    """Held-out overlap and A_val clusters are strictly excluded and never contribute to clean counts or k."""
    from ml.train_m2.eval.post_oof import evaluate_partial_oof

    fold_mem = {
        "c_clean": 0,
        "c_heldout": 0,
        "c_aval": 0,
    }
    key_flags = {
        "c_clean": {"in_heldout": False, "in_a_val": False},
        "c_heldout": {"in_heldout": True, "in_a_val": False},
        "c_aval": {"in_heldout": False, "in_a_val": True},
    }
    rows = [
        {"input_key": "c_clean", "crossfit_fold": 0, "sample_idx": 0, "gate_pass": True, "oracle_class": "minimal_correct"},
        # c_heldout has a gate-passing-wrong draft, but MUST be excluded
        {"input_key": "c_heldout", "crossfit_fold": 0, "sample_idx": 0, "gate_pass": True, "oracle_class": "wrong", "heldout_overlap": True},
        # c_aval has a gate-passing-wrong draft, but MUST be excluded
        {"input_key": "c_aval", "crossfit_fold": 0, "sample_idx": 0, "gate_pass": True, "oracle_class": "wrong", "in_a_val": True},
    ]

    res = evaluate_partial_oof(rows, fold_mem, key_flags, existing_unseen_clean=15)
    # Only c_clean is counted
    assert res["clean_unseen_clusters"] == ["c_clean"]
    assert res["oof_clean_count"] == 1
    assert res["total_clean_clusters"] == 16
    # k must NOT count the errors in c_heldout or c_aval
    assert res["k"] == 0
    assert res["cp_min_n"] == 59


def test_main_cli_dry_run_execution(tmp_path: Path):
    """Verify main() CLI execution succeeds in dry-run mode and writes artifacts."""
    out_dir = tmp_path / "cli_dry_run_out"
    exit_code = main(["--dry-run", "--out-dir", str(out_dir)])
    assert exit_code == 0
    assert (out_dir / "oof_unseen_clean.json").is_file()
    assert (out_dir / "re_split_proposal.json").is_file()
    assert (out_dir / "tau_star.json").is_file()
    assert (out_dir / "m2" / "m2.joblib").is_file()

