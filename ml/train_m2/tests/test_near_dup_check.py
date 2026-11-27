"""Unit tests for ml/train_m2/eval/near_dup_check.py (P6i)."""
from __future__ import annotations

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
