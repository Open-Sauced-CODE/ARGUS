"""Tests for sft_oof -> sft feature-time remap and label pipeline integration (P6i)."""
from __future__ import annotations

import json
from pathlib import Path

from ml.train_m2.common import jsonl_write_atomic
from ml.train_m2.features import registry as R
from ml.train_m2.features.compute import compute_features
from ml.train_m2.labels import build_labels as BL
from ml.train_m2.labels import harvest_labeler as HL
from ml.train_m2.models import dataset as DS

EXPECTED_FROZEN_SPEC_HASH = "0c099708cff3be6d30e2dadeccd7467d7fd4a452088ec81b4600994310959e50"

SAMPLE_PATCH = json.dumps({
    "finding_id": "F-0",
    "resource_ref": "RESOURCE_1",
    "ops": [{"op": "set_attr", "attr": "a", "value": True}],
    "rationale_ref": "dpdp.rule6a",
})


def test_sft_oof_row_yields_gen_sft_1_and_gen_sft_oof_0_and_spec_hash_unchanged() -> None:
    """Fixture sft_oof row must yield gen_sft=1.0, gen_sft_oof=0.0, and frozen spec_hash."""
    assert R.spec_hash() == EXPECTED_FROZEN_SPEC_HASH
    row = {
        "content": SAMPLE_PATCH,
        "tokens": [{"t": "{", "lp": -0.05, "top": [["{", -0.05], ["[", -3.0]]}],
        "generator": "sft_oof",
        "sample_idx": 0,
        "crossfit_fold": 2,
    }
    ctx = {"rule_id": "dpdp.rule6a", "route": "fix"}
    feats = compute_features(row, [row], ctx)

    assert feats["gen_sft"] == 1.0
    assert feats["gen_sft_oof"] == 0.0
    assert feats["gen_zeroshot"] == 0.0
    assert feats["gen_rft"] == 0.0
    assert feats["gen_rft_v2"] == 0.0
    assert feats["spec_hash"] == EXPECTED_FROZEN_SPEC_HASH
    # Original row dict is not mutated
    assert row["generator"] == "sft_oof"
    assert row["crossfit_fold"] == 2


def test_build_frame_remaps_sft_oof_for_features_and_keeps_provenance() -> None:
    """dataset.build_frame sets X['gen_sft']=1 and meta['generator']='sft' while preserving provenance."""
    ik = "test_ik_oof_0"
    hv = {
        "sft_oof": {
            (ik, 0): {
                "input_key": ik,
                "content": SAMPLE_PATCH,
                "tokens": [{"t": "{", "lp": -0.05, "top": [["{", -0.05], ["[", -3.0]]}],
                "generator": "sft_oof",
                "sample_idx": 0,
                "crossfit_fold": 1,
            }
        }
    }
    label_rows = [
        {
            "input_key": ik,
            "generator": "sft_oof",
            "sample_idx": 0,
            "gate_pass": True,
            "outcome": "fixed",
            "oracle_class": "minimal_correct",
            "source": "scored_log",
            "crossfit_fold": 1,
        }
    ]
    info = {ik: {"rule_id": "dpdp.rule6a", "route": "fix"}}
    X, meta = DS.build_frame(label_rows, hv, info)

    assert len(X) == 1
    assert float(X.loc[0, "gen_sft"]) == 1.0
    assert float(X.loc[0, "gen_sft_oof"]) == 0.0
    assert meta.loc[0, "generator"] == "sft"
    assert meta.loc[0, "source_generator"] == "sft_oof"
    assert int(meta.loc[0, "crossfit_fold"]) == 1


def test_build_labels_and_harvest_labeler_include_sft_oof(tmp_path: Path) -> None:
    """build_labels and harvest_labeler include sft_oof and keep generator=sft_oof + crossfit_fold in provenance."""
    assert "sft_oof" in BL.HARVEST_GENERATORS
    assert "sft_oof" in HL.HARVEST_GENERATORS
    assert BL.remap_generator_for_features("sft_oof") == "sft"
    assert HL.remap_generator_for_features("sft_oof") == "sft"

    # Synthetic sft_oof harvest folder
    ik = '{"fields":{"ip_range":"0.0.0.0/0","resource_type":"AWSIpPermissionInbound"},"resource_ref":"RESOURCE_1","rule_id":"cis.sg_open_ingress"}'
    h_dir = tmp_path / "ml" / "train_m2" / "harvest_out" / "sft_oof" / "A"
    h_dir.mkdir(parents=True)
    contract_dir = tmp_path / "ml" / "train_m2" / "contract"
    contract_dir.mkdir(parents=True)

    rec = {
        "finding_id": "F-0",
        "rule_id": "cis.sg_open_ingress",
        "resource_id": "RESOURCE_1",
        "resource_ref": "RESOURCE_1",
        "fields": {"fromport": 0, "ip_range": "0.0.0.0/0", "protocol": "-1", "resource_type": "AWSIpPermissionInbound", "toport": 0},
    }
    ref = {
        "finding_id": "F-0",
        "resource_ref": "RESOURCE_1",
        "rationale_ref": "cis.sg_open_ingress",
        "ops": [{"op": "restrict_cidr", "attr": "ip_range", "value": "INTERNAL_CIDR"}],
    }
    jsonl_write_atomic(contract_dir / "harvest_inputs.jsonl", [{"input_key": ik, "record": rec, "sets": {"train": True}}])

    patch_txt = json.dumps(ref)
    jsonl_write_atomic(h_dir / "part-0000.jsonl", [{
        "input_key": ik,
        "generator": "sft_oof",
        "profile": "A",
        "sample_idx": 0,
        "crossfit_fold": 3,
        "content": patch_txt,
        "tokens": [{"t": "{", "lp": -0.01, "top": [["{", -0.01], ["[", -4.0]]}],
    }])

    out_dir = tmp_path / "labels_out"
    ps = {"phase5_train": {ik}, "a_val": set(), "v2_train": set()}

    from unittest.mock import patch as mock_patch
    fake_score = [{"candidates": [{"gate_passed": True, "outcome": "fixed", "hidden": {
        "full_equivalence": True, "minimal_patch": True, "decoys_untouched": True, "no_side_effects": True
    }, "hidden_ok": True}]}]
    with mock_patch("ml.train_m1.eval.score.score_inputs", return_value=fake_score):
        stats = HL.label_harvest(
            generator="sft_oof",
            root=tmp_path,
            ref_map={ik: {"record": rec, "reference": ref, "route": "fix"}},
            hi_map={ik: rec},
            partition_sets=ps,
            out_dir=out_dir,
            seed=1337,
        )

    assert stats["rows"] == 1
    out_file = out_dir / "harvest" / "sft_oof.jsonl"
    assert out_file.is_file()
    rows = [json.loads(ln) for ln in out_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert rows[0]["generator"] == "sft_oof"
    assert rows[0]["crossfit_fold"] == 3
    assert rows[0]["feature_generator"] == "sft"

    prov_file = out_dir / "harvest" / "sft_oof.jsonl.provenance.json"
    prov = json.loads(prov_file.read_text(encoding="utf-8").splitlines()[0])
    assert prov["extra"]["generator"] == "sft_oof"
    assert prov["extra"]["feature_generator"] == "sft"
    assert prov["extra"]["crossfit_folds"] == [3]
