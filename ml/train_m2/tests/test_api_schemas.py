"""Tests for ml/train_m2/api_schemas.py (P6f Stage 2).

Validates Pydantic schemas against 20 real non-test harvest rows evaluated
through decide.py (confidence and decide functions).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from ml.train_m2.api_schemas import (
    ConfidenceInput,
    ConfidenceOutput,
    ContributionSchema,
    DecideInput,
    DecideOutput,
    TrustRecord,
)
from ml.train_m2.common import jsonl_iter, load_inputs, repo_root
from ml.train_m2.decide import confidence, decide, load_model
from ml.train_m2.features.compute import compute_features

HELDOUT_SETS = {"B1", "B2", "C_verifier", "gold"}


@pytest.fixture(scope="module")
def decision_env():
    """Load config, model artifact, tau_info, and 20 real non-test harvest rows."""
    root = repo_root()
    cfg_path = root / "ml" / "train_m2" / "configs" / "decision.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    tau_info = json.loads((root / cfg["tau_path"]).read_text(encoding="utf-8"))
    art = load_model(root / cfg["model_path"])

    inputs = {r["input_key"]: r for r in load_inputs()}
    train_keys = {
        k for k, r in inputs.items()
        if "train" in r.get("sets", {}) and not any(s in HELDOUT_SETS for s in r.get("sets", {}))
    }

    # Sample 20 real non-test rows from harvest_out
    harvest_root = root / "ml" / "train_m2" / "harvest_out"
    rows: list[dict[str, Any]] = []
    cohort_cache: dict[tuple[str, str], list[dict[str, Any]]] = {}

    for gen in ("zeroshot", "sft", "rft", "rft_v2"):
        p = harvest_root / gen / "A" / "part-0000.jsonl"
        if not p.exists():
            continue
        for row in jsonl_iter(p):
            ik = row.get("input_key")
            if ik in train_keys and not row.get("error") and row.get("content"):
                rows.append(row)
                if len(rows) >= 20:
                    break
        if len(rows) >= 20:
            break

    assert len(rows) == 20, f"Expected 20 real non-test rows, got {len(rows)}"
    return {
        "cfg": cfg,
        "tau_info": tau_info,
        "art": art,
        "rows": rows,
        "inputs": inputs,
        "harvest_root": harvest_root,
    }


def test_confidence_schemas_20_rows(decision_env):
    """Validate ConfidenceInput and ConfidenceOutput against 20 real non-test rows."""
    cfg = decision_env["cfg"]
    art = decision_env["art"]
    rows = decision_env["rows"]
    inputs = decision_env["inputs"]

    for row in rows:
        ik = row["input_key"]
        meta = inputs[ik].get("record", {}).get("meta", {})
        ctx = {"rule_id": meta.get("rule_id", ""), "route": meta.get("route", "fix")}
        feats = compute_features(row, [row], ctx)

        # Validate ConfidenceInput
        c_in = ConfidenceInput(features=feats, spec_hash=art["spec_hash"])
        assert c_in.spec_hash == art["spec_hash"]
        assert isinstance(c_in.features, dict)

        # Compute confidence and validate ConfidenceOutput
        p = confidence(feats, art)
        c_out = ConfidenceOutput(p_hat=p)
        assert 0.0 <= c_out.p_hat <= 1.0

        # Validate JSON serialization round-trip
        data = json.loads(c_out.model_dump_json())
        assert data["p_hat"] == pytest.approx(p)


def test_decide_schemas_20_rows(decision_env):
    """Validate DecideInput, DecideOutput, and TrustRecord against 20 real non-test rows."""
    cfg = decision_env["cfg"]
    tau_info = decision_env["tau_info"]
    art = decision_env["art"]
    rows = decision_env["rows"]
    inputs = decision_env["inputs"]

    for idx, row in enumerate(rows):
        ik = row["input_key"]
        meta = inputs[ik].get("record", {}).get("meta", {})
        ctx = {"rule_id": meta.get("rule_id", ""), "route": meta.get("route", "fix")}
        feats = compute_features(row, [row], ctx)

        # Validate DecideInput
        d_in = DecideInput(
            features=feats,
            gate_passed=True,
            escalated_only=False,
            breaker="CLOSED",
            config=cfg,
            tau_info=tau_info,
        )
        assert d_in.gate_passed is True
        assert d_in.breaker == "CLOSED"

        # Compute Decision
        dec = decide(
            feats,
            gate_passed=True,
            escalated_only=False,
            breaker="CLOSED",
            config=cfg,
            tau_info=tau_info,
            art=art,
        )

        # Validate DecideOutput
        d_out = DecideOutput.from_decision(dec)
        assert d_out.action in {"auto_apply", "human_review", "reject"}
        assert d_out.feature_spec_hash == art["spec_hash"]
        assert d_out.model_version == cfg.get("model_version", "m2")
        assert len(d_out.top_contributors) > 0
        for c in d_out.top_contributors:
            assert isinstance(c, ContributionSchema)
            assert c.feature
            assert isinstance(c.text, str)

        # Validate TrustRecord
        record = TrustRecord.create(
            decision=d_out,
            context={"row_index": idx, "generator": row.get("generator")},
            record_id=f"rec-{idx:04d}",
        )
        assert record.record_id == f"rec-{idx:04d}"
        assert record.decision.action == dec.action
        assert "T" in record.timestamp  # ISO format

        # JSON round-trip
        dumped = record.model_dump_json()
        assert "confidence" in dumped or "action" in dumped
        reloaded = TrustRecord.model_validate_json(dumped)
        assert reloaded.decision.action == d_out.action
        assert reloaded.decision.cost_ratio == pytest.approx(d_out.cost_ratio)


def test_schema_rejection_on_bad_inputs():
    """Verify validation error when required fields are missing or wrong types."""
    with pytest.raises(ValidationError):
        ConfidenceInput(features="not_a_dict", spec_hash="hash")  # type: ignore

    with pytest.raises(ValidationError):
        ConfidenceOutput(p_hat="not_a_float")  # type: ignore

    with pytest.raises(ValidationError):
        DecideInput(
            features={},
            gate_passed="not_bool",  # type: ignore
            escalated_only=False,
            config={},
            tau_info={},
        )


def test_gate_failed_decision_schema(decision_env):
    """Verify DecideOutput and TrustRecord handle gate_passed=False cleanly."""
    cfg = decision_env["cfg"]
    art = decision_env["art"]
    dec = decide(
        {},
        gate_passed=False,
        escalated_only=False,
        breaker="CLOSED",
        config=cfg,
        tau_info={},
        art=art,
    )
    d_out = DecideOutput.from_decision(dec)
    assert d_out.action == "reject"
    assert d_out.p_hat is None
    assert d_out.reasons == ["gate failed"]

    rec = TrustRecord.create(decision=dec, record_id="gate-fail-01")
    assert rec.decision.action == "reject"
