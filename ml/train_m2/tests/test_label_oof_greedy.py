"""Unit tests for ml/train_m2/eval/label_oof_greedy.py (P6i/P6J)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ml.train_m2.common import jsonl_write_atomic
from ml.train_m2.eval import label_oof_greedy as LOG_MOD


def _synthetic_fixture(n_clean_per_fold: int, k_errors: int):
    """Build synthetic fold preds, fold membership, flags, ref_map, and fake score_fn."""
    fold_membership: dict[str, int] = {}
    key_flags: dict[str, dict[str, bool]] = {}
    ref_map: dict[str, dict[str, Any]] = {}
    preds_by_fold: dict[int, list[dict[str, Any]]] = {}

    # 3 folds: 0, 1, 2
    idx = 0
    wrong_remaining = k_errors
    for f in (0, 1, 2):
        rows = []
        for _ in range(n_clean_per_fold):
            ik = f"clean_{idx}"
            idx += 1
            fold_membership[ik] = f
            key_flags[ik] = {"in_heldout": False, "in_a_val": False}
            fid = f"F-{idx}"
            rec = {"finding_id": fid, "rule_id": "dpdp.rule6a", "resource_ref": "R1"}
            ref = {"finding_id": fid, "resource_ref": "R1", "ops": [{"op": "enable_feature", "attr": "mfa", "value": True}], "rationale_ref": "dpdp.rule6a"}
            ref_map[ik] = {"record": rec, "reference": ref, "route": "fix"}

            if wrong_remaining > 0:
                wrong_remaining -= 1
                pred_patch = {"finding_id": fid, "resource_ref": "R1", "ops": [{"op": "set_attr", "attr": "x", "value": 1}], "rationale_ref": "dpdp.rule6a", "_err": True}
            else:
                pred_patch = dict(ref)
            rows.append({"input_key": ik, "content": json.dumps(pred_patch)})

        # Add held-out and A_val clusters that MUST NEVER be scored
        ho_ik = f"ho_{f}"
        av_ik = f"aval_{f}"
        fold_membership[ho_ik] = f
        fold_membership[av_ik] = f
        key_flags[ho_ik] = {"in_heldout": True, "in_a_val": False}
        key_flags[av_ik] = {"in_heldout": False, "in_a_val": True}
        rows.append({"input_key": ho_ik, "content": "{}"})
        rows.append({"input_key": av_ik, "content": "{}"})

        preds_by_fold[f] = rows

    scored_keys: list[str] = []

    def fake_score_inputs(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for it in items:
            fid = it["record"]["finding_id"]
            scored_keys.append(fid)
            patch = json.loads(it["contents"][0])
            if patch.get("_err"):
                hidden = {"full_equivalence": False, "minimal_patch": False, "decoys_untouched": True, "no_side_effects": True}
                out.append({"candidates": [{"gate_passed": True, "outcome": "fixed", "hidden": hidden, "hidden_ok": False}]})
            else:
                hidden = {"full_equivalence": True, "minimal_patch": True, "decoys_untouched": True, "no_side_effects": True}
                out.append({"candidates": [{"gate_passed": True, "outcome": "fixed", "hidden": hidden, "hidden_ok": True}]})
        return out

    return preds_by_fold, fold_membership, key_flags, ref_map, fake_score_inputs, scored_keys


def test_label_oof_greedy_k0_sufficient() -> None:
    """With 45 clean OOF + 15 existing = 60 and k=0 (min_n=59), verdict is SUFFICIENT and held-out/A_val never scored."""
    preds, fm, flags, rmap, score_fn, scored_fids = _synthetic_fixture(15, k_errors=0)
    res = LOG_MOD.label_clean_oof_greedy(preds, fm, flags, rmap, score_fn=score_fn)

    assert res["totals"]["clean_clusters"] == 45
    assert res["totals"]["excluded_heldout_or_aval"] == 6
    assert res["clean_k"] == 0
    assert res["total_clean_n"] == 60
    assert res["cp_min_n"] == 59
    assert res["verdict"] == "SUFFICIENT"
    # Held-out and A_val keys were not in ref_map and never scored
    assert len(scored_fids) == 45


def test_label_oof_greedy_k1_sufficient_vs_need_more() -> None:
    """With k=1 (min_n=93): 30*3+15=105 -> SUFFICIENT; 20*3+15=75 -> NEED 18 MORE."""
    preds_suf, fm, flags, rmap, score_fn, _ = _synthetic_fixture(30, k_errors=1)
    res_suf = LOG_MOD.label_clean_oof_greedy(preds_suf, fm, flags, rmap, score_fn=score_fn)
    assert res_suf["clean_k"] == 1
    assert res_suf["total_clean_n"] == 105
    assert res_suf["cp_min_n"] == 93
    assert res_suf["verdict"] == "SUFFICIENT"

    preds_need, fm2, flags2, rmap2, score_fn2, _ = _synthetic_fixture(20, k_errors=1)
    res_need = LOG_MOD.label_clean_oof_greedy(preds_need, fm2, flags2, rmap2, score_fn=score_fn2)
    assert res_need["clean_k"] == 1
    assert res_need["total_clean_n"] == 75
    assert res_need["cp_min_n"] == 93
    assert res_need["verdict"] == "NEED 18 MORE CLEAN CLUSTERS"


def test_label_oof_greedy_k3_need_more() -> None:
    """With 40*3+15=135 clean clusters and k=3 (min_n=153), verdict is NEED 18 MORE CLEAN CLUSTERS."""
    preds, fm, flags, rmap, score_fn, _ = _synthetic_fixture(40, k_errors=3)
    res = LOG_MOD.label_clean_oof_greedy(preds, fm, flags, rmap, score_fn=score_fn)
    assert res["clean_k"] == 3
    assert res["total_clean_n"] == 135
    assert res["cp_min_n"] == 153
    assert res["verdict"] == "NEED 18 MORE CLEAN CLUSTERS"


def test_label_oof_greedy_stops_when_preds_dir_missing(tmp_path: Path) -> None:
    """CLI exits non-zero when explicitly given preds dir contains no fold*_preds.jsonl."""
    rc = LOG_MOD.main(["--preds-dir", str(tmp_path / "missing_dir")])
    assert rc == 1


def _make_zero_schema_preds_file(tmp_path: Path, fold_id: int, n_rows: int) -> Path:
    """Write a fold file where every content is NOT schema-valid (chat-template leakage simulation)."""
    out = tmp_path / f"fold{fold_id}_preds.jsonl"
    rows = []
    for i in range(n_rows):
        # Simulate the chat-template leakage artifact: valid JSON followed by assistant continuation
        content = (
            '{"finding_id":"F-0","resource_ref":"R1","ops":[{"op":"escalate","reason":"test"}],'
            '"rationale_ref":"dpdp.rule6a"}\nassistant\n<think>\n</think>\n'
            '{"finding_id":"F-X","bad":"content leaking"}'
        )
        rows.append({"input_key": f"key_{fold_id}_{i}", "content": content})
    with out.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return out


def test_validate_preds_layout_skips_invalid_folds(tmp_path: Path) -> None:
    """validate_preds_layout silently skips folds listed as invalid; never loads or labels them."""
    # Fold 0 is VALID; fold 1 is INVALID (0% schema-valid, simulates fold2/fold4 situation)
    fold0_rows = [{"input_key": f"k0_{i}", "content": "{}"} for i in range(3)]
    fold1_rows = [{"input_key": f"k1_{i}", "content": "not valid"} for i in range(2)]

    f0 = tmp_path / "fold0_preds.jsonl"
    f1 = tmp_path / "fold1_preds.jsonl"
    for path, rows in [(f0, fold0_rows), (f1, fold1_rows)]:
        with path.open("w") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")

    fold_paths = {0: f0, 1: f1}
    folds_data: dict = {
        "folds": {
            "0": {"input_keys": [f"k0_{i}" for i in range(3)]},
            "1": {"input_keys": [f"k1_{i}" for i in range(2)]},
        }
    }

    # With fold 1 marked INVALID: only fold 0 is loaded
    result = LOG_MOD.validate_preds_layout(
        fold_paths, folds_data, invalid_folds=frozenset({1})
    )
    assert 0 in result
    assert 1 not in result
    assert len(result[0]) == 3


def test_load_invalid_folds_from_manifest(tmp_path: Path) -> None:
    """load_invalid_folds correctly parses INVALID entries from OOF_PREDS_MANIFEST.json."""
    manifest = {
        "folds": {
            "2": {"status": "INVALID", "file": "fold2_preds.jsonl"},
            "4": {"status": "INVALID", "file": "fold4_preds.jsonl"},
            "0": {"status": "VALID", "file": "fold0_preds.jsonl"},
        }
    }
    manifest_path = tmp_path / "OOF_PREDS_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    invalid = LOG_MOD.load_invalid_folds(manifest_path)
    assert invalid == frozenset({2, 4})


def test_load_invalid_folds_missing_manifest_returns_empty(tmp_path: Path) -> None:
    """load_invalid_folds returns empty frozenset if manifest does not exist."""
    invalid = LOG_MOD.load_invalid_folds(tmp_path / "no_such_file.json")
    assert invalid == frozenset()


def test_validate_preds_layout_invalid_fold_zero_schema_valid_not_labeled(tmp_path: Path) -> None:
    """A fold file with 0% schema-valid content, once marked INVALID, is excluded from labeling.

    This is the synthetic fixture for fold2/fold4: the content column contains
    chat-template leakage (reference_json + assistant + think tags), making every row
    fail schema validation. The test confirms validate_preds_layout drops it completely
    when invalid_folds includes that fold ID.
    """
    # Build a fold with 0% schema-valid rows (simulating fold2 / fold4 chat-template leakage)
    zero_schema_file = _make_zero_schema_preds_file(tmp_path, fold_id=2, n_rows=43)

    # Build a valid fold for comparison
    valid_rows = [{"input_key": f"valid_key_{i}", "content": "{}"} for i in range(5)]
    valid_file = tmp_path / "fold0_preds.jsonl"
    with valid_file.open("w") as fh:
        for r in valid_rows:
            fh.write(json.dumps(r) + "\n")

    fold_paths = {0: valid_file, 2: zero_schema_file}
    folds_data: dict = {
        "folds": {
            "0": {"input_keys": [f"valid_key_{i}" for i in range(5)]},
            "2": {"input_keys": [f"key_2_{i}" for i in range(43)]},
        }
    }

    # Mark fold 2 INVALID: it must be entirely excluded
    result = LOG_MOD.validate_preds_layout(
        fold_paths, folds_data, invalid_folds=frozenset({2})
    )
    assert 2 not in result, "INVALID fold must not be loaded or labeled"
    assert 0 in result
    assert len(result[0]) == 5


def test_resolve_preds_files_finds_crossfit_oof_preds(tmp_path: Path) -> None:
    """resolve_preds_files finds fold files in docs/phase6_shaurya/crossfit/oof_preds/."""
    oof_dir = tmp_path / "docs" / "phase6_shaurya" / "crossfit" / "oof_preds"
    oof_dir.mkdir(parents=True)
    (oof_dir / "fold0_preds.jsonl").write_text("{}\n", encoding="utf-8")
    (oof_dir / "fold1_preds.jsonl").write_text("{}\n", encoding="utf-8")

    resolved_dir, fold_paths = LOG_MOD.resolve_preds_files(tmp_path)
    assert resolved_dir is not None
    assert 0 in fold_paths
    assert 1 in fold_paths


def test_resolve_preds_files_five_file_layout_and_resolution_order(tmp_path: Path) -> None:
    """Resolution order: harvest_out/sft_oof_greedy/ -> docs/phase6_shaurya/crossfit/oof_preds/ -> root."""
    harvest_dir = tmp_path / "ml" / "train_m2" / "harvest_out" / "sft_oof_greedy"
    oof_dir = tmp_path / "docs" / "phase6_shaurya" / "crossfit" / "oof_preds"
    harvest_dir.mkdir(parents=True)
    oof_dir.mkdir(parents=True)

    for f in range(5):
        (harvest_dir / f"fold{f}_preds.jsonl").write_text("{}\n", encoding="utf-8")
    for f in (0, 1, 3):
        (oof_dir / f"fold{f}_preds.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "fold0_preds.jsonl").write_text("{}\n", encoding="utf-8")

    # 1. harvest_out/sft_oof_greedy wins first and sees all 5 folds
    d1, p1 = LOG_MOD.resolve_preds_files(tmp_path)
    assert d1 == harvest_dir
    assert sorted(p1.keys()) == [0, 1, 2, 3, 4]

    # 2. Without harvest_out/sft_oof_greedy, docs/phase6_shaurya/crossfit/oof_preds/ wins
    for fp in harvest_dir.glob("*.jsonl"):
        fp.unlink()
    d2, p2 = LOG_MOD.resolve_preds_files(tmp_path)
    assert d2 == oof_dir
    assert sorted(p2.keys()) == [0, 1, 3]

    # 3. Without oof_preds/, repo root wins
    for fp in oof_dir.glob("*.jsonl"):
        fp.unlink()
    d3, p3 = LOG_MOD.resolve_preds_files(tmp_path)
    assert d3 == tmp_path
    assert sorted(p3.keys()) == [0]


def test_zero_schema_valid_fold_rejected_even_without_manifest(tmp_path: Path) -> None:
    """Synthetic fixture: a file with 0% schema-valid output is rejected and NOT labeled."""
    zero_file = _make_zero_schema_preds_file(tmp_path, fold_id=4, n_rows=6)
    valid_patch = json.dumps({
        "finding_id": "F-0",
        "resource_ref": "RESOURCE_1",
        "ops": [{"op": "set_attr", "attr": "logging_enabled", "value": True}],
        "rationale_ref": "dpdp.rule6_logging",
    })
    valid_file = tmp_path / "fold0_preds.jsonl"
    with valid_file.open("w", encoding="utf-8") as fh:
        for i in range(4):
            fh.write(json.dumps({"input_key": f"k0_{i}", "content": valid_patch}) + "\n")

    folds_data: dict[str, Any] = {
        "folds": {
            "0": {"input_keys": [f"k0_{i}" for i in range(4)]},
            "4": {"input_keys": [f"key_4_{i}" for i in range(6)]},
        }
    }
    loaded = LOG_MOD.validate_preds_layout(
        {0: valid_file, 4: zero_file},
        folds_data,
        min_schema_valid_frac=0.90,
    )
    assert sorted(loaded.keys()) == [0]
    assert 4 not in loaded

    # Verify rejected fold is never passed to score_fn or labeled
    scored_keys: list[str] = []
    fold_membership = {f"k0_{i}": 0 for i in range(4)}
    fold_membership.update({f"key_4_{i}": 4 for i in range(6)})
    key_flags = {ik: {"in_heldout": False, "in_a_val": False} for ik in fold_membership}
    ref_map = {
        f"k0_{i}": {
            "record": {"finding_id": "F-0", "rule_id": "dpdp.rule6_logging", "resource_ref": "RESOURCE_1"},
            "reference": json.loads(valid_patch),
            "route": "fix",
        }
        for i in range(4)
    }

    def fake_score(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for it in items:
            scored_keys.append(it["record"]["finding_id"])
            out.append({"candidates": [{"gate_passed": True, "outcome": "fixed", "hidden": {"full_equivalence": True, "minimal_patch": True, "decoys_untouched": True, "no_side_effects": True}, "hidden_ok": True}]})
        return out

    res = LOG_MOD.label_clean_oof_greedy(loaded, fold_membership, key_flags, ref_map, score_fn=fake_score)
    assert len(scored_keys) == 4
    assert [r["fold"] for r in res["per_fold"]] == [0]
    assert res["totals"]["clean_clusters"] == 4
