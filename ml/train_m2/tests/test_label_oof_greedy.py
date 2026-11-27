"""Unit tests for ml/train_m2/eval/label_oof_greedy.py (P6i)."""
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
