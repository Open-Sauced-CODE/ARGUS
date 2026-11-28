"""Unit tests for ml/train_m2/eval/near_dup_check.py (P6i)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ml.train_m2.eval import near_dup_check as ND


def test_normalize_replaces_identifiers_and_numbers_preserves_structure() -> None:
    """Records differing only in account/resource IDs and port numbers normalize identically."""
    r1 = {
        "finding_id": "F-10",
        "rule_id": "cis.sg_open_ingress",
        "resource_ref": "RESOURCE_1",
        "fields": {"fromport": 443, "toport": 443, "protocol": "tcp", "ip_range": "10.0.1.5/32"},
    }
    r2 = {
        "finding_id": "F-99",
        "rule_id": "cis.sg_open_ingress",
        "resource_ref": "RESOURCE_2",
        "fields": {"fromport": 8443, "toport": 8443, "protocol": "tcp", "ip_range": "192.168.10.2/32"},
    }
    r3 = {
        "finding_id": "F-11",
        "rule_id": "cis.sg_open_ingress",
        "resource_ref": "RESOURCE_3",
        "fields": {"fromport": 22, "toport": 22, "protocol": "tcp", "ip_range": "0.0.0.0/0"},
    }

    assert ND.normalized_signature(r1) == ND.normalized_signature(r2)
    assert ND.normalized_signature(r1) != ND.normalized_signature(r3)


def test_near_dup_check_triggers_alert_over_20_percent_and_compares_pass_rates() -> None:
    """Verify >20% near-dup rate triggers exact warning and reports remaining clusters + pass rates."""
    folds_data = {
        "folds": {
            "0": {"input_keys": ["oof_dup", "oof_uniq", "oof_ho"]},
            "1": {"input_keys": ["tr_match", "tr_other"]},
        }
    }
    records_by_key = {
        "oof_dup": {"rule_id": "cis.sg_open_ingress", "fields": {"fromport": 443, "protocol": "tcp", "ip_range": "10.0.0.1/32"}},
        "tr_match": {"rule_id": "cis.sg_open_ingress", "fields": {"fromport": 8080, "protocol": "tcp", "ip_range": "172.16.0.5/32"}},
        "oof_uniq": {"rule_id": "dpdp.rule6a", "fields": {"encryption": False, "kms_key": "RESOURCE_9"}},
        "oof_ho": {"rule_id": "dpdp.rule6a", "fields": {"encryption": False}},
        "tr_other": {"rule_id": "dpdp.rule15_region", "fields": {"region": "us-east-1"}},
    }
    key_flags = {
        "oof_dup": {"in_heldout": False, "in_a_val": False},
        "oof_uniq": {"in_heldout": False, "in_a_val": False},
        "oof_ho": {"in_heldout": True, "in_a_val": False},
        "tr_match": {"in_heldout": False, "in_a_val": False},
        "tr_other": {"in_heldout": False, "in_a_val": False},
    }
    clean_labels = {
        "oof_dup": {"gate_pass": True, "oracle_class": "minimal_correct"},
        "oof_uniq": {"gate_pass": False, "oracle_class": "wrong"},
    }

    res = ND.analyze_near_duplicates(
        folds_data,
        records_by_key,
        key_flags,
        clean_labels=clean_labels,
        folds_subset=[0],
    )

    assert res["total_clean_clusters"] == 2
    assert res["identical_norm_signature_count"] == 1
    assert res["near_duplicate_count"] == 1
    assert res["near_duplicate_rate"] == 0.5
    assert res["remaining_after_removal"] == 1
    assert res["alert_triggered"] is True
    assert res["alert_message"] == "OOF clusters are not independent of training; clean counts overstate unseen clusters"
    assert res["oof_pass_comparison"]["with_near_dup"]["gate_pass_rate"] == 1.0
    assert res["oof_pass_comparison"]["without_near_dup"]["gate_pass_rate"] == 0.0
    assert res["oof_pass_comparison"]["gate_pass_rate_diff"] == 1.0

    md = ND.render_near_dup_report(res)
    assert "OOF clusters are not independent of training; clean counts overstate unseen clusters" in md
    assert "cis.sg_open_ingress" not in md  # Counts only; zero input content in report


def test_near_dup_check_triggers_alert_if_single_fold_exceeds_20_percent() -> None:
    """Alert triggers if any single fold's near-duplicate rate exceeds 20% even when total <= 20%."""
    folds_data = {
        "folds": {
            "0": {"input_keys": ["oof_0_dup", "oof_0_uniq"]},  # Fold 0: 50% (> 20%)
            "1": {"input_keys": [f"oof_1_{i}" for i in range(8)]},  # Fold 1: 0%
            "2": {"input_keys": ["tr_2_match"]},  # Training cluster in fold 2
        }
    }
    records_by_key = {
        "oof_0_dup": {"rule_id": "cis.sg_open_ingress", "fields": {"fromport": 443, "ip_range": "10.0.0.1/32"}},
        "tr_2_match": {"rule_id": "cis.sg_open_ingress", "fields": {"fromport": 8443, "ip_range": "172.16.0.1/32"}},
        "oof_0_uniq": {"rule_id": "dpdp.rule6a", "fields": {"encryption": False}},
        **{
            f"oof_1_{i}": {"rule_id": "dpdp.rule15_region", "fields": {"region": f"r-{i}", "flag": i % 2 == 0}}
            for i in range(8)
        },
    }
    key_flags = {k: {"in_heldout": False, "in_a_val": False} for k in records_by_key}

    res = ND.analyze_near_duplicates(folds_data, records_by_key, key_flags, folds_subset=[0, 1])
    assert res["total_clean_clusters"] == 10
    assert res["near_duplicate_count"] == 1
    assert res["near_duplicate_rate"] == 0.10
    assert res["per_fold"][0]["near_dup_rate"] == 0.50
    assert res["alert_triggered"] is True
    assert res["alert_message"] == "OOF clusters are not independent of training; clean counts overstate unseen clusters"
    assert res["remaining_after_removal"] == 9


def test_existing_clean_near_dup_and_both_cert_versions() -> None:
    """Verify 15-existing near-dup check and BOTH (a) all-clean and (b) non-near-dup cert verdicts."""
    folds_data = {
        "folds": {
            "0": {"input_keys": ["oof_dup", "oof_uniq"]},
            "1": {"input_keys": ["tr_match", "tr_other"]},
        }
    }
    records_by_key = {
        "oof_dup": {"rule_id": "cis.sg_open_ingress", "fields": {"fromport": 443, "ip_range": "10.0.0.1/32"}},
        "tr_match": {"rule_id": "cis.sg_open_ingress", "fields": {"fromport": 8443, "ip_range": "172.16.0.1/32"}},
        "oof_uniq": {"rule_id": "dpdp.rule6a", "fields": {"encryption": False}},
        "tr_other": {"rule_id": "dpdp.rule15_region", "fields": {"region": "us-east-1"}},
        "ex_uniq": {"rule_id": "dpdp.rule6_logging", "fields": {"logging_enabled": False}},
        "ex_dup": {"rule_id": "cis.sg_open_ingress", "fields": {"fromport": 9000, "ip_range": "10.1.0.2/32"}},
    }
    key_flags = {
        "oof_dup": {"in_heldout": False, "in_a_val": False, "in_train": True},
        "oof_uniq": {"in_heldout": False, "in_a_val": False, "in_train": True},
        "tr_match": {"in_heldout": False, "in_a_val": False, "in_train": True},
        "tr_other": {"in_heldout": False, "in_a_val": False, "in_train": True},
        "ex_uniq": {"in_heldout": False, "in_a_val": True, "in_train": False},
        "ex_dup": {"in_heldout": False, "in_a_val": True, "in_train": False},
    }
    clean_labels = {
        "oof_dup": {"gate_pass": True, "oracle_class": "wrong"},
        "oof_uniq": {"gate_pass": True, "oracle_class": "minimal_correct"},
    }

    res = ND.analyze_near_duplicates(
        folds_data,
        records_by_key,
        key_flags,
        clean_labels=clean_labels,
        folds_subset=[0],
        existing_clean_count=15,
    )
    ex_nd = res["existing_clean_near_dups"]
    assert ex_nd["existing_clean_count"] == 2
    assert ex_nd["near_dup_count"] == 1
    assert ex_nd["remaining_independent"] == 1
    assert ex_nd["has_near_duplicates"] is True

    cert = res["certification_comparison"]
    # (a) all clean: 2 + 15 = 17, k = 1 -> cp_min_n = 93, margin = -76
    assert cert["all_clean"]["n"] == 17
    assert cert["all_clean"]["k"] == 1
    assert cert["all_clean"]["cp_min_n"] == 93
    assert cert["all_clean"]["margin"] == -76
    # (b) after removing near-dups: 1 + 15 = 16, k = 0 -> cp_min_n = 59, margin = -43
    assert cert["after_removing_near_dups"]["n"] == 16
    assert cert["after_removing_near_dups"]["k"] == 0
    assert cert["after_removing_near_dups"]["cp_min_n"] == 59
    assert cert["after_removing_near_dups"]["margin"] == -43
    assert "accepted drafts at tau" in cert["note"]

    md = ND.render_near_dup_report(res)
    assert "Existing Clean Clusters vs All Training Folds" in md
    assert "Clopper-Pearson Certification Comparison" in md
    assert "accepted drafts at tau" in md


def test_near_dup_check_main_skips_invalid_folds_from_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """near_dup_check CLI skips folds marked INVALID in manifest and never loads or labels them."""
    import json
    from ml.train_m2.eval import label_oof_greedy as LOG_MOD

    # Set up fake repo with 5 fold files where folds 2 and 4 are marked INVALID (0% schema-valid)
    harvest_dir = tmp_path / "ml" / "train_m2" / "harvest_out" / "sft_oof_greedy"
    harvest_dir.mkdir(parents=True)
    valid_patch = json.dumps({
        "finding_id": "F-0",
        "resource_ref": "R1",
        "ops": [{"op": "set_attr", "attr": "logging_enabled", "value": True}],
        "rationale_ref": "dpdp.rule6_logging",
    })
    folds_obj: dict[str, Any] = {"folds": {}}
    records_by_key: dict[str, dict[str, Any]] = {}
    inputs_list: list[dict[str, Any]] = []

    for f in range(5):
        iks = [f"k_{f}_0", f"k_{f}_1"]
        folds_obj["folds"][str(f)] = {"input_keys": iks}
        for ik in iks:
            rec = {"finding_id": "F-0", "rule_id": "dpdp.rule6_logging", "resource_ref": "R1", "fields": {"logging_enabled": False}}
            records_by_key[ik] = rec
            inputs_list.append({"input_key": ik, "record": rec, "sets": {"train": True}})
        pred_file = harvest_dir / f"fold{f}_preds.jsonl"
        content = valid_patch if f in (0, 1, 3) else "broken{\nassistant\n<think>junk"
        with pred_file.open("w", encoding="utf-8") as fh:
            for ik in iks:
                fh.write(json.dumps({"input_key": ik, "content": content}) + "\n")

    folds_path = tmp_path / "folds.json"
    folds_path.write_text(json.dumps(folds_obj), encoding="utf-8")
    manifest_path = tmp_path / "OOF_PREDS_MANIFEST.json"
    manifest_path.write_text(json.dumps({
        "folds": {
            "0": {"status": "VALID"},
            "1": {"status": "VALID"},
            "2": {"status": "INVALID"},
            "3": {"status": "VALID"},
            "4": {"status": "INVALID"},
        }
    }), encoding="utf-8")

    # Need harvest_inputs.jsonl under tmp_path for provenance()
    contract_dir = tmp_path / "ml" / "train_m2" / "contract"
    contract_dir.mkdir(parents=True)
    (contract_dir / "harvest_inputs.jsonl").write_text("", encoding="utf-8")

    ref_map = {
        ik: {"record": rec, "reference": json.loads(valid_patch), "route": "fix"}
        for ik, rec in records_by_key.items()
    }
    monkeypatch.setattr(ND, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(LOG_MOD, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(ND, "load_inputs", lambda: inputs_list)
    monkeypatch.setattr(LOG_MOD, "load_train_reference_map", lambda root: ref_map)

    out_dir = tmp_path / "reports"
    rc = ND.main([
        "--folds", str(folds_path),
        "--manifest", str(manifest_path),
        "--out-dir", str(out_dir),
    ])
    assert rc == 0
    rep = json.loads((out_dir / "near_dup_oof.json").read_text(encoding="utf-8"))
    assert rep["folds_analyzed"] == [0, 1, 3]
    assert rep["invalid_folds_excluded"] == [2, 4]
    assert rep["total_clean_clusters"] == 6
