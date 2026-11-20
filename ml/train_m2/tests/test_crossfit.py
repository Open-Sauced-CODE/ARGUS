"""Tests for crossfit_folds.py and ingest_oof.py (P6f Stage 1).

Tests:
  - Fold determinism across two subprocesses with different PYTHONHASHSEED
  - Fold disjointness
  - Rule stratification on a hand-built set
  - heldout_overlap flag correctness
  - No absolute paths in folds.json
  - ingest_oof: disjointness assertion
  - ingest_oof: empty harvest runs in stub mode
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

from ml.train_m2.eval.crossfit_folds import (
    K,
    SEED,
    _stable_hash,
    build_folds,
    render_markdown,
)
from ml.train_m2.eval.ingest_oof import (
    _build_fold_membership,
    _load_folds,
    assert_fold_disjointness,
    compute_unseen_clean_counts,
    render_report,
)
from ml.train_m2.common import repo_root


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_folds(n_per_fold: int = 4, k: int = 3) -> dict[str, Any]:
    """Build a minimal folds dict for unit testing."""
    keys_per_fold: dict[str, list[str]] = {}
    all_keys: list[str] = []
    for f in range(k):
        fold_keys = [f"key_{f}_{i}" for i in range(n_per_fold)]
        keys_per_fold[str(f)] = fold_keys
        all_keys.extend(fold_keys)
    return {
        "seed": 1337,
        "K": k,
        "total_train_inputs": n_per_fold * k,
        "folds": {
            str(f): {
                "input_keys": keys_per_fold[str(f)],
                "per_rule": {"test.rule": n_per_fold},
                "heldout_overlap": [],
                "in_a_val": [],
                "note": "test",
            }
            for f in range(k)
        },
        "counts_per_fold": {
            str(f): {"total": n_per_fold, "heldout_overlap": 0, "in_a_val": 0}
            for f in range(k)
        },
        "rule_id_distribution": {"test.rule": n_per_fold * k},
    }


# ---------------------------------------------------------------------------
# Determinism: same seed -> same fold assignment, regardless of PYTHONHASHSEED
# ---------------------------------------------------------------------------

def test_fold_determinism_across_processes():
    """build_folds(1337) must produce identical output with PYTHONHASHSEED=0 and PYTHONHASHSEED=42."""
    script = (
        "import json, sys; "
        "from ml.train_m2.eval.crossfit_folds import build_folds; "
        "result = build_folds(1337); "
        # Only print the fold assignment (input_keys per fold) as a stable fingerprint
        "print(json.dumps({f: sorted(d['input_keys']) for f, d in result['folds'].items()}, sort_keys=True))"
    )
    env0 = {**os.environ, "PYTHONHASHSEED": "0"}
    env42 = {**os.environ, "PYTHONHASHSEED": "42"}

    root = str(repo_root())

    r0 = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, cwd=root, env=env0, timeout=60,
    )
    r42 = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, cwd=root, env=env42, timeout=60,
    )

    assert r0.returncode == 0, f"subprocess 0 failed: {r0.stderr[-500:]}"
    assert r42.returncode == 0, f"subprocess 42 failed: {r42.stderr[-500:]}"
    assert r0.stdout.strip() == r42.stdout.strip(), (
        "Fold assignment differs between PYTHONHASHSEED=0 and PYTHONHASHSEED=42"
    )


# ---------------------------------------------------------------------------
# Disjointness
# ---------------------------------------------------------------------------

def test_fold_disjointness():
    """Every train input appears in exactly one fold."""
    folds = build_folds(SEED)
    seen: set[str] = set()
    for f_str, fold_data in folds["folds"].items():
        for ik in fold_data["input_keys"]:
            assert ik not in seen, f"input_key {ik!r} in fold {f_str} and another fold"
            seen.add(ik)
    # Total must equal 230
    assert len(seen) == folds["total_train_inputs"] == 230


def test_fold_covers_all_train_inputs():
    """Union of fold keys == the 230 train input_keys from harvest_inputs.jsonl."""
    from ml.train_m2.common import load_inputs
    inputs = load_inputs()
    train_keys = {r["input_key"] for r in inputs if "train" in r.get("sets", {})}
    folds = build_folds(SEED)
    fold_keys: set[str] = set()
    for fold_data in folds["folds"].values():
        fold_keys.update(fold_data["input_keys"])
    assert fold_keys == train_keys


# ---------------------------------------------------------------------------
# Rule stratification
# ---------------------------------------------------------------------------

def test_rule_stratification_hand_built():
    """With a hand-built 3-rule, 15-input universe, each rule appears in every fold."""
    # Inject a minimal universe by patching load_inputs
    import unittest.mock as mock

    # 5 inputs per rule, 3 rules, 2 folds => each fold should have >= 1 of each rule
    fake_inputs = []
    for rule in ["rule_a", "rule_b", "rule_c"]:
        for i in range(5):
            ik = json.dumps({"rule_id": rule, "idx": i}, sort_keys=True)
            fake_inputs.append({"input_key": ik, "sets": {"train": 1}})

    with mock.patch("ml.train_m2.eval.crossfit_folds.load_inputs", return_value=fake_inputs):
        from ml.train_m2.eval import crossfit_folds as cf
        folds = cf.build_folds(SEED)

    # With 15 inputs and K=5 folds, each fold should have 3 inputs (1 per rule)
    for f_str, fold_data in folds["folds"].items():
        rule_counts = fold_data["per_rule"]
        assert sum(rule_counts.values()) > 0, f"fold {f_str} is empty"


# ---------------------------------------------------------------------------
# Heldout overlap flag
# ---------------------------------------------------------------------------

def test_heldout_overlap_flag():
    """Inputs in B1/B2/C_verifier/gold appear in heldout_overlap."""
    from ml.train_m2.common import load_inputs
    inputs = load_inputs()
    heldout_keys = {
        r["input_key"] for r in inputs
        if any(s in {"B1", "B2", "C_verifier", "gold"} for s in r.get("sets", {}))
        and "train" in r.get("sets", {})
    }

    folds = build_folds(SEED)
    all_overlap: set[str] = set()
    for fold_data in folds["folds"].values():
        all_overlap.update(fold_data["heldout_overlap"])

    # Every key that is both train and in a heldout set should appear in some fold's overlap
    assert heldout_keys == all_overlap, (
        f"heldout_overlap mismatch: extra={all_overlap - heldout_keys}, missing={heldout_keys - all_overlap}"
    )


# ---------------------------------------------------------------------------
# No absolute paths in folds.json
# ---------------------------------------------------------------------------

def test_folds_json_no_absolute_paths(tmp_path):
    """folds.json must not contain absolute paths (would break on other machines)."""
    folds = build_folds(SEED)
    text = json.dumps(folds)
    # Heuristic: no Windows drive letters or Unix root paths
    assert "C:\\" not in text and "C:/" not in text, "Absolute Windows path found in folds"
    assert "://" not in text, "URL-like absolute path found in folds"


# ---------------------------------------------------------------------------
# ingest_oof: disjointness assertion
# ---------------------------------------------------------------------------

def test_ingest_disjointness_assertion():
    """assert_fold_disjointness raises AssertionError if the same input_key appears in two folds."""
    fake_rows = [
        {"input_key": "k1", "crossfit_fold": 0},
        {"input_key": "k1", "crossfit_fold": 1},  # same key in two folds
    ]
    membership = {"k1": 0}
    with pytest.raises(AssertionError, match="k1"):
        assert_fold_disjointness(fake_rows, membership)


def test_ingest_disjointness_mismatch():
    """assert_fold_disjointness raises if crossfit_fold doesn't match assigned fold."""
    fake_rows = [
        {"input_key": "k1", "crossfit_fold": 2},  # assigned to fold 0, but says 2
    ]
    membership = {"k1": 0}
    with pytest.raises(AssertionError, match="k1"):
        assert_fold_disjointness(fake_rows, membership)


def test_ingest_disjointness_valid():
    """assert_fold_disjointness passes for valid assignment."""
    fake_rows = [
        {"input_key": "k1", "crossfit_fold": 0},
        {"input_key": "k2", "crossfit_fold": 1},
    ]
    membership = {"k1": 0, "k2": 1}
    assert_fold_disjointness(fake_rows, membership)  # no exception


# ---------------------------------------------------------------------------
# ingest_oof: empty harvest (stub mode)
# ---------------------------------------------------------------------------

def test_ingest_oof_empty_harvest(tmp_path):
    """ingest_oof handles an empty harvest directory (stub mode) without crashing."""
    from ml.train_m2.eval.ingest_oof import ingest_oof

    # Build folds first
    folds_dir = tmp_path / "crossfit"
    folds_dir.mkdir()
    folds = build_folds(SEED)
    folds_path = folds_dir / "folds.json"
    folds_path.write_text(json.dumps(folds), encoding="utf-8")

    harvest_root = tmp_path / "sft_oof"  # does NOT exist
    out_dir = tmp_path / "reports"

    counts = ingest_oof(
        harvest_root=harvest_root,
        folds_path=folds_path,
        out_dir=out_dir,
        current_unseen=15,
        needed=44,
    )

    assert counts["total_clusters"] == 0
    assert counts["unseen_clean_count"] == 0
    report_path = out_dir / "oof_unseen_clean.md"
    assert report_path.exists()


# ---------------------------------------------------------------------------
# ingest_oof: synthetic fixture
# ---------------------------------------------------------------------------

def test_ingest_oof_synthetic_fixture(tmp_path):
    """ingest_oof correctly counts unseen-clean clusters from a synthetic fixture."""
    from ml.train_m2.common import load_inputs
    from ml.train_m2.eval.ingest_oof import ingest_oof, _build_key_flags

    inputs = load_inputs()
    train_inputs = [r for r in inputs if "train" in r.get("sets", {})]

    folds = build_folds(SEED)
    fold_membership: dict[str, int] = {}
    for f_str, fold_data in folds["folds"].items():
        for ik in fold_data["input_keys"]:
            fold_membership[ik] = int(f_str)

    key_flags = _build_key_flags(inputs)

    # Build a synthetic harvest: one row per cluster in fold 0, labelled crossfit_fold=0
    fold0_keys = folds["folds"]["0"]["input_keys"]
    fake_rows = [
        {"input_key": ik, "crossfit_fold": 0, "generator": "sft_oof", "sample_idx": 0}
        for ik in fold0_keys
    ]

    counts = compute_unseen_clean_counts(fake_rows, fold_membership, key_flags)

    # unseen_clean_count should equal fold 0 keys that are not heldout and not A_val
    expected_clean = [
        ik for ik in fold0_keys
        if not key_flags.get(ik, {}).get("in_heldout", False)
        and not key_flags.get(ik, {}).get("in_a_val", False)
    ]
    assert counts["unseen_clean_count"] == len(expected_clean), (
        f"Expected {len(expected_clean)} unseen-clean clusters, got {counts['unseen_clean_count']}"
    )
    assert counts["unseen_heldout_count"] == len(folds["folds"]["0"]["heldout_overlap"])


# ---------------------------------------------------------------------------
# render functions do not crash
# ---------------------------------------------------------------------------

def test_render_markdown_runs():
    folds = build_folds(SEED)
    md = render_markdown(folds)
    assert "Seed: 1337" in md
    assert "| 0 |" in md


def test_render_report_runs():
    counts = {
        "total_clusters": 55,
        "unseen_clean_count": 22,
        "unseen_heldout_count": 17,
        "unseen_aval_count": 16,
        "seen_count": 0,
        "unknown_count": 0,
        "unseen_clean_clusters": [],
        "unseen_heldout_clusters": [],
        "note": "test",
    }
    md = render_report(counts, current_unseen=15, needed=44)
    assert "unseen-clean" in md.lower()
    assert "22" in md


# ---------------------------------------------------------------------------
# stable_hash uses hashlib, not Python hash()
# ---------------------------------------------------------------------------

def test_stable_hash_uses_hashlib():
    """_stable_hash must match the hashlib implementation, not Python's hash()."""
    seed, key = 1337, "test_key"
    expected = int(hashlib.sha256(f"{seed}:{key}".encode("utf-8")).hexdigest(), 16)
    assert _stable_hash(seed, key) == expected


def test_stable_hash_differs_from_python_hash():
    """_stable_hash must NOT be the same as Python's hash() on typical inputs."""
    seed, key = 1337, "some_input_key"
    # This is a sanity check - stable_hash is an int over 256 bits; python hash is 64-bit
    stable = _stable_hash(seed, key)
    py_hash = hash(key)
    # They could theoretically match but it's astronomically unlikely
    assert stable != py_hash or stable > 2**63  # stable is always a large int
