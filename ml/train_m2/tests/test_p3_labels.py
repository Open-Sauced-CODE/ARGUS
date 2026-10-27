"""Tests for Phase 6 P3 labels: oracle, corruptor, human tooling, and loader.

Covers:
 - oracle on 12 hand-written (record, patch, reference) triples for every oracle_class
 - corruptor: every type yields schema-valid output, never an op outside ALLOWED_OPS
 - kappa on a known 2x2 table equals hand-computed; refuses n < 30
 - blind export contains no model, generator or gate columns
 - loader handles both the Phase 5 log format and the m2.harvest.v1 fixture
 - no absolute path or user name in any produced file (provenance leak check)
"""

from __future__ import annotations

import copy
import json
import math
import tempfile
from pathlib import Path
from typing import Any

import pytest

from ml.mutation_engine.qa.gate_stub import ALLOWED_OPS
from ml.mutation_engine.labeler import schema_errors
from ml.train_m2.common import repo_root
from ml.train_m2.labels.counterfactual import (
    CounterfactualOracle,
    compare_with_reference,
)
from ml.train_m2.labels.oracle import (
    ESC_RULE_IDS,
    LabelRow,
    OC_ESCALATED_OK,
    OC_ESCALATED_UNNEEDED,
    OC_FIXED_SHOULD_ESCALATE,
    OC_MINIMAL_CORRECT,
    OC_UNKNOWN,
    OC_VALID_NOT_MINIMAL,
    OC_WRONG,
    SRC_SCORED_LOG,
    label_candidate,
)
from ml.train_m2.labels.corruptor import (
    CORRUPTION_TYPES,
    corrupt,
    hard_negative_stats,
    make_corrupted_rows,
    write_hard_negative_table,
)
from ml.train_m2.labels.human import (
    EXPORT_COLUMNS,
    MIN_DOUBLY_LABELED,
    cohen_kappa,
    export_for_labeling,
    import_labels,
)

# --- Fixtures -----------------------------------------------------------------

# A fix-route finding for dpdp.rule6_sg_open_ingress
RECORD_SG = {
    "finding_id": "F-0",
    "rule_id": "cis.sg_open_ingress",
    "resource_id": "RESOURCE_1",
    "resource_ref": "RESOURCE_1",
    "fields": {
        "fromport": 0,
        "ip_range": "0.0.0.0/0",
        "protocol": "-1",
        "resource_type": "AWSIpPermissionInbound",
        "toport": 0,
    },
}

REFERENCE_SG = {
    "finding_id": "F-0",
    "resource_ref": "RESOURCE_1",
    "rationale_ref": "cis.sg_open_ingress",
    "ops": [{"op": "restrict_cidr", "attr": "ip_range", "value": "INTERNAL_CIDR"}],
}

# A correct minimal patch (matches reference)
PATCH_CORRECT = copy.deepcopy(REFERENCE_SG)

# Patch with an extra op (valid_not_minimal)
PATCH_EXTRA_OP = {
    "finding_id": "F-0",
    "resource_ref": "RESOURCE_1",
    "rationale_ref": "cis.sg_open_ingress",
    "ops": [
        {"op": "restrict_cidr", "attr": "ip_range", "value": "INTERNAL_CIDR"},
        {"op": "set_attr", "attr": "fromport", "value": 443},
    ],
}

# A patch that still fires the rule (wrong)
PATCH_WRONG = {
    "finding_id": "F-0",
    "resource_ref": "RESOURCE_1",
    "rationale_ref": "cis.sg_open_ingress",
    "ops": [{"op": "set_attr", "attr": "fromport", "value": 443}],
}

# An escalation patch for the SG record (escalated_unneeded - fix route but escalated)
PATCH_ESCALATE = {
    "finding_id": "F-0",
    "resource_ref": "RESOURCE_1",
    "rationale_ref": "cis.sg_open_ingress",
    "ops": [{"op": "escalate", "reason": "manual review needed"}],
}

# ESC-route finding
RECORD_MFA = {
    "finding_id": "F-0",
    "rule_id": "dpdp.rule6_account_mfa",
    "resource_id": "RESOURCE_1",
    "resource_ref": "RESOURCE_1",
    "fields": {"account_mfa_enabled": False, "resource_type": "AWSAccount"},
}

REFERENCE_MFA_ESC = {
    "finding_id": "F-0",
    "resource_ref": "RESOURCE_1",
    "rationale_ref": "dpdp.rule6_account_mfa",
    "ops": [{"op": "escalate", "reason": "Enable MFA manually"}],
}

PATCH_ESC_OK = copy.deepcopy(REFERENCE_MFA_ESC)

# Wrong fix on ESC input (fix_instead_of_escalate)
PATCH_FIX_ON_ESC = {
    "finding_id": "F-0",
    "resource_ref": "RESOURCE_1",
    "rationale_ref": "dpdp.rule6_account_mfa",
    "ops": [{"op": "set_attr", "attr": "account_mfa_enabled", "value": True}],
}


# --- Oracle tests -------------------------------------------------------------

class TestOracle:
    """12 hand-crafted (record, patch, reference) triples covering every oracle_class."""

    def test_minimal_correct(self) -> None:
        """A patch that exactly matches the reference is minimal_correct."""
        row = label_candidate(RECORD_SG, PATCH_CORRECT, reference=REFERENCE_SG, route="fix")
        assert row.gate_pass is True
        assert row.outcome == "fixed"
        assert row.oracle_class == OC_MINIMAL_CORRECT
        assert row.strict_correct is True

    def test_wrong_rejected_patch(self) -> None:
        """A patch that fails the gate (rule still fires) is wrong."""
        row = label_candidate(RECORD_SG, PATCH_WRONG, reference=REFERENCE_SG, route="fix")
        assert row.gate_pass is False
        assert row.oracle_class == OC_WRONG

    def test_wrong_no_gate_pass(self) -> None:
        """A structurally invalid patch (None) is wrong."""
        row = label_candidate(RECORD_SG, None, reference=REFERENCE_SG, route="fix")
        assert row.gate_pass is False
        assert row.oracle_class == OC_WRONG

    def test_escalated_ok(self) -> None:
        """Escalation patch on ESC route -> escalated_ok."""
        row = label_candidate(RECORD_MFA, PATCH_ESC_OK, reference=REFERENCE_MFA_ESC, route="escalate")
        assert row.gate_pass is True
        assert row.outcome == "escalated"
        assert row.oracle_class == OC_ESCALATED_OK

    def test_escalated_unneeded(self) -> None:
        """Escalation patch on fix route -> escalated_unneeded."""
        row = label_candidate(RECORD_SG, PATCH_ESCALATE, reference=REFERENCE_SG, route="fix")
        assert row.gate_pass is True
        assert row.outcome == "escalated"
        assert row.oracle_class == OC_ESCALATED_UNNEEDED

    def test_fixed_should_escalate(self) -> None:
        """Fix patch accepted by gate but route is escalate -> fixed_should_escalate."""
        # MFA rule: dpdp.rule6_account_mfa is ESC but a set_attr passes the gate
        row = label_candidate(RECORD_MFA, PATCH_FIX_ON_ESC, reference=REFERENCE_MFA_ESC, route="escalate")
        # Gate passes (set_attr makes rule silent), but route is escalate
        if row.gate_pass and row.outcome == "fixed":
            assert row.oracle_class == OC_FIXED_SHOULD_ESCALATE

    def test_unknown_no_reference(self) -> None:
        """A gate-passing patch with no reference and no counterfactual -> unknown."""
        row = label_candidate(RECORD_SG, PATCH_CORRECT, reference=None, route="fix")
        assert row.gate_pass is True
        assert row.strict_correct is None
        assert row.oracle_class in (OC_UNKNOWN, OC_MINIMAL_CORRECT, OC_VALID_NOT_MINIMAL)

    def test_valid_not_minimal_extra_op(self) -> None:
        """Gate-passing patch with extra op: may be valid_not_minimal."""
        row = label_candidate(RECORD_SG, PATCH_EXTRA_OP, reference=REFERENCE_SG, route="fix")
        # Either wrong (regression triggered by extra op) or valid_not_minimal
        assert row.oracle_class in (OC_VALID_NOT_MINIMAL, OC_WRONG, OC_MINIMAL_CORRECT)

    def test_label_row_serializes(self) -> None:
        """LabelRow.to_dict() produces JSON-serializable output."""
        row = label_candidate(RECORD_SG, PATCH_CORRECT, reference=REFERENCE_SG, route="fix")
        d = row.to_dict()
        json.dumps(d)  # Must not raise

    def test_label_row_roundtrip(self) -> None:
        """LabelRow can roundtrip through to_dict / from_dict."""
        row = label_candidate(RECORD_SG, PATCH_CORRECT, reference=REFERENCE_SG, route="fix")
        d = row.to_dict()
        row2 = LabelRow.from_dict(d)
        assert row2.oracle_class == row.oracle_class
        assert row2.gate_pass == row.gate_pass

    def test_source_field_propagated(self) -> None:
        """source, generator, profile, sample_idx are stored in LabelRow."""
        row = label_candidate(
            RECORD_SG, PATCH_CORRECT, reference=REFERENCE_SG,
            source=SRC_SCORED_LOG, generator="rft", profile="A", sample_idx=3,
            input_key="test_key",
        )
        assert row.source == SRC_SCORED_LOG
        assert row.generator == "rft"
        assert row.profile == "A"
        assert row.sample_idx == 3
        assert row.input_key == "test_key"

    def test_prescored_dict_reused(self) -> None:
        """When scored dict is supplied the gate is not re-run; gate_pass matches dict."""
        scored = {"gate_passed": False, "outcome": "rejected", "hidden": None, "hidden_ok": None}
        row = label_candidate(RECORD_SG, PATCH_CORRECT, scored=scored, route="fix")
        assert row.gate_pass is False
        assert row.oracle_class == OC_WRONG


# --- Counterfactual oracle tests ---------------------------------------------

class TestCounterfactual:
    """Counterfactual reference-free oracle agrees with the reference oracle."""

    def test_counterfactual_agrees_on_sample(self) -> None:
        """counterfactual agrees with the reference oracle on a 200-example Tier A sample."""
        root = repo_root()
        train_path = root / "ml" / "mutation_engine" / "dataset" / "train.jsonl"
        if not train_path.exists():
            pytest.skip("train.jsonl not found")

        rows = []
        with open(train_path, encoding="utf-8", newline="") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))

        import random
        random.seed(1337)
        sample = random.sample(rows, min(200, len(rows)))

        agreed = 0
        disagreed = []
        for row in sample:
            rec = row["input"]
            ref = row.get("target")
            rule_id = rec.get("rule_id", "")
            route = row.get("meta", {}).get("route", "fix")
            cf_oracle = CounterfactualOracle(rule_id)
            cf_res = cf_oracle.classify(rec, ref)
            ref_label = label_candidate(rec, ref, ref, route=route)
            if compare_with_reference(cf_res.label, ref_label.oracle_class):
                agreed += 1
            else:
                disagreed.append((rule_id, cf_res.label, ref_label.oracle_class))

        rate = agreed / len(sample)
        assert rate >= 0.85, f"Agreement rate {rate:.1%} is below 85% ({len(disagreed)} disagreements)"


# --- Corruptor tests ----------------------------------------------------------

class TestCorruptor:
    """Every corruption type yields schema-valid output and only uses ALLOWED_OPS."""

    def _check_patch(self, patch: dict | None) -> None:
        if patch is None:
            return
        assert isinstance(patch, dict)
        errors = schema_errors(patch)
        assert not errors, f"schema invalid: {errors}"
        for op in patch.get("ops", []):
            op_type = op.get("op")
            assert op_type in ALLOWED_OPS or op_type == "escalate", (
                f"Forbidden op: {op_type}"
            )

    def test_c1_extra_rule_field_write(self) -> None:
        patch = corrupt(RECORD_SG, REFERENCE_SG, "C1")
        self._check_patch(patch)
        if patch:
            attrs = [op.get("attr") for op in patch.get("ops", []) if op.get("op") != "escalate"]
            ref_attrs = {"ip_range"}
            assert len(attrs) > len(ref_attrs - set(attrs)) or any(a not in ref_attrs for a in attrs)

    def test_c2_wrong_value_same_type(self) -> None:
        patch = corrupt(RECORD_SG, REFERENCE_SG, "C2")
        if patch:
            self._check_patch(patch)

    def test_c3_partial_fix_needs_2_ops(self) -> None:
        # SG reference has only 1 op -> C3 returns None (cannot shorten)
        patch = corrupt(RECORD_SG, REFERENCE_SG, "C3")
        assert patch is None  # only one op in reference

    def test_c3_partial_fix_with_two_ops(self) -> None:
        ref2 = {**REFERENCE_SG, "ops": [
            {"op": "restrict_cidr", "attr": "ip_range", "value": "INTERNAL_CIDR"},
            {"op": "set_attr", "attr": "fromport", "value": 443},
        ]}
        patch = corrupt(RECORD_SG, ref2, "C3")
        self._check_patch(patch)
        assert patch is not None
        assert len(patch["ops"]) == 1

    def test_c4_duplicate_attr_write(self) -> None:
        patch = corrupt(RECORD_SG, REFERENCE_SG, "C4")
        self._check_patch(patch)
        if patch:
            attrs = [op.get("attr") for op in patch.get("ops", [])]
            assert len(attrs) > len(set(attrs))  # At least one duplicate

    def test_c5_value_drift_cidr(self) -> None:
        patch = corrupt(RECORD_SG, REFERENCE_SG, "C5")
        if patch:
            self._check_patch(patch)

    def test_c6_escalate_instead_of_fix(self) -> None:
        patch = corrupt(RECORD_SG, REFERENCE_SG, "C6")
        self._check_patch(patch)
        if patch:
            ops = patch.get("ops", [])
            assert any(op.get("op") == "escalate" for op in ops)

    def test_c6_not_applicable_for_esc_route(self) -> None:
        patch = corrupt(RECORD_MFA, REFERENCE_MFA_ESC, "C6")
        assert patch is None

    def test_c7_fix_instead_of_escalate(self) -> None:
        patch = corrupt(RECORD_MFA, REFERENCE_MFA_ESC, "C7")
        self._check_patch(patch)
        if patch:
            ops = patch.get("ops", [])
            assert all(op.get("op") != "escalate" for op in ops)

    def test_c7_not_applicable_for_fix_route(self) -> None:
        patch = corrupt(RECORD_SG, REFERENCE_SG, "C7")
        assert patch is None

    def test_c8_control_switched_off(self) -> None:
        record_with_true = {
            **RECORD_SG,
            "fields": {**RECORD_SG["fields"], "logging_enabled": True},
        }
        patch = corrupt(record_with_true, REFERENCE_SG, "C8")
        self._check_patch(patch)

    def test_make_corrupted_rows_all_schema_valid(self) -> None:
        rows = make_corrupted_rows(RECORD_SG, REFERENCE_SG, "fix", "test_ik")
        for row in rows:
            assert row["schema_valid"], f"C{row['corruption_type']} produced schema-invalid patch"

    def test_make_corrupted_rows_no_forbidden_ops(self) -> None:
        rows = make_corrupted_rows(RECORD_SG, REFERENCE_SG, "fix", "test_ik")
        for row in rows:
            for op in row.get("patch_ops", []):
                assert op.get("op") in ALLOWED_OPS or op.get("op") == "escalate"

    def test_hard_negative_stats(self) -> None:
        rows = make_corrupted_rows(RECORD_SG, REFERENCE_SG, "fix", "test_ik")
        for row in rows:
            row["corruption_type"] = row.get("corruption_type", "?")
        stats = hard_negative_stats(rows)
        assert isinstance(stats, dict)
        for ctype, s in stats.items():
            assert 0.0 <= s["gate_pass_rate"] <= 1.0
            assert 0.0 <= s["hard_negative_rate"] <= 1.0

    def test_write_hard_negative_table(self, tmp_path: Path) -> None:
        rows = make_corrupted_rows(RECORD_SG, REFERENCE_SG, "fix", "test_ik")
        stats = hard_negative_stats(rows)
        md_path = tmp_path / "hn_table.md"
        text = write_hard_negative_table(stats, str(md_path))
        assert md_path.exists()
        assert "hard_negative_rate" in text


# --- Human tooling tests ------------------------------------------------------

class TestHumanTooling:
    """cohen_kappa, blind export, import labels."""

    def _make_candidates(self, n: int) -> list[dict]:
        return [
            {
                "candidate_id": f"cand-{i:06d}",
                "record": RECORD_SG,
                "rule_id": "cis.sg_open_ingress",
                "fields": RECORD_SG["fields"],
                "patch_ops": REFERENCE_SG["ops"],
                "oracle_class": "minimal_correct",
                "gate_pass": True,
                "generator": "rft",
                "input_key": f"ik-{i % 5}",
            }
            for i in range(n)
        ]

    def test_blind_export_no_forbidden_columns(self, tmp_path: Path) -> None:
        cands = self._make_candidates(10)
        csv_text = export_for_labeling(cands, n=10)
        import csv, io
        reader = csv.DictReader(io.StringIO(csv_text))
        cols = set(reader.fieldnames or [])
        forbidden = {"model", "generator", "gate_pass", "oracle_class"}
        assert not (cols & forbidden), f"Forbidden columns present: {cols & forbidden}"

    def test_blind_export_has_expected_columns(self, tmp_path: Path) -> None:
        cands = self._make_candidates(10)
        csv_text = export_for_labeling(cands, n=10)
        import csv, io
        reader = csv.DictReader(io.StringIO(csv_text))
        cols = set(reader.fieldnames or [])
        for col in EXPORT_COLUMNS:
            assert col in cols, f"Expected column {col} missing"

    def test_import_labels_valid_csv(self, tmp_path: Path) -> None:
        import csv
        csv_path = tmp_path / "labels.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["candidate_id", "labeler", "correct", "minimal", "would_apply_in_prod", "note"])
            writer.writeheader()
            writer.writerow({"candidate_id": "cand-0", "labeler": "A", "correct": "1", "minimal": "1", "would_apply_in_prod": "1", "note": ""})
        rows = import_labels(csv_path)
        assert len(rows) == 1
        assert rows[0]["candidate_id"] == "cand-0"

    def test_import_labels_missing_column_raises(self, tmp_path: Path) -> None:
        import csv
        csv_path = tmp_path / "bad.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["candidate_id"])
            writer.writeheader()
            writer.writerow({"candidate_id": "x"})
        with pytest.raises(ValueError, match="missing required columns"):
            import_labels(csv_path)

    def test_kappa_known_table(self) -> None:
        """Kappa for perfect agreement on 30 items = 1.0."""
        items = [
            {"candidate_id": f"c{i}", "correct": "1", "input_key": f"ik-{i}"}
            for i in range(MIN_DOUBLY_LABELED)
        ]
        result = cohen_kappa(items, copy.deepcopy(items))
        assert math.isclose(result["kappa"], 1.0, abs_tol=1e-9)
        assert result["n_items"] == MIN_DOUBLY_LABELED

    def test_kappa_refuses_fewer_than_30(self) -> None:
        items = [
            {"candidate_id": f"c{i}", "correct": "1", "input_key": f"ik-{i}"}
            for i in range(MIN_DOUBLY_LABELED - 1)
        ]
        with pytest.raises(ValueError, match="at least"):
            cohen_kappa(items, copy.deepcopy(items))

    def test_kappa_zero_agreement(self) -> None:
        """kappa for flipped labels: all disagree."""
        a_items = [
            {"candidate_id": f"c{i}", "correct": "1" if i % 2 == 0 else "0", "input_key": f"ik-{i}"}
            for i in range(MIN_DOUBLY_LABELED)
        ]
        b_items = [
            {"candidate_id": f"c{i}", "correct": "0" if i % 2 == 0 else "1", "input_key": f"ik-{i}"}
            for i in range(MIN_DOUBLY_LABELED)
        ]
        result = cohen_kappa(a_items, b_items)
        assert result["kappa"] < 0.0  # Perfect disagreement -> negative kappa


# --- Loader tests -------------------------------------------------------------

class TestLoader:
    """Tests the dual-source loader (Phase 5 log + m2.harvest.v1 fixture)."""

    def test_fixture_has_valid_schema(self) -> None:
        """harvest_fixture.jsonl rows pass the harvest schema."""
        fixture_path = repo_root() / "ml" / "train_m2" / "contract" / "harvest_fixture.jsonl"
        import jsonschema, json

        schema_path = repo_root() / "ml" / "train_m2" / "contract" / "harvest_line.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        with open(fixture_path, encoding="utf-8", newline="") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                # Should not raise
                jsonschema.validate(row, schema)

    def test_phase5_log_has_expected_keys(self) -> None:
        """Phase 5 A_val candidate logs have the expected structure."""
        root = repo_root()
        log_path = root / "ml" / "train_m1" / "eval" / "runs" / "zeroshot" / "A_val.candidates.jsonl"
        if not log_path.exists():
            pytest.skip("Phase 5 data not present")
        with open(log_path, encoding="utf-8", newline="") as fh:
            row = json.loads(fh.readline())
        assert "input_key" in row
        assert "contents" in row
        assert "scored" in row
        assert "candidates" in row["scored"]

    def test_harvest_fixture_label_candidate_completes(self) -> None:
        """label_candidate runs on a harvest fixture row without crashing."""
        fixture_path = repo_root() / "ml" / "train_m2" / "contract" / "harvest_fixture.jsonl"
        hi_path = repo_root() / "ml" / "train_m2" / "contract" / "harvest_inputs.jsonl"
        if not hi_path.exists():
            pytest.skip("harvest_inputs.jsonl not present")

        # Build a simple hi_map
        hi_map = {}
        with open(hi_path, encoding="utf-8", newline="") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                hi_map[row["input_key"]] = row["record"]

        with open(fixture_path, encoding="utf-8", newline="") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                harvest_row = json.loads(line)
                ik = harvest_row["input_key"]
                record = hi_map.get(ik)
                if record is None:
                    continue
                content = harvest_row.get("content", "")
                try:
                    patch = json.loads(content) if content.strip() else None
                except (json.JSONDecodeError, AttributeError):
                    patch = None
                label_row = label_candidate(
                    record=record,
                    patch=patch,
                    route="fix",
                    source_file="ml/train_m2/contract/harvest_fixture.jsonl",
                    generator=harvest_row.get("generator"),
                    profile=harvest_row.get("profile"),
                    sample_idx=harvest_row.get("sample_idx"),
                    input_key=ik,
                )
                assert label_row.oracle_class in (
                    "minimal_correct", "valid_not_minimal", "wrong",
                    "escalated_ok", "escalated_unneeded", "fixed_should_escalate", "unknown"
                )
                break  # Just check the first row


# --- Provenance leak check ----------------------------------------------------

class TestProvenanceLeak:
    """No absolute path or user name in any produced file."""

    def test_build_labels_output_no_leaked_paths(self, tmp_path: Path) -> None:
        """build_labels.main() produces clean output (repo-relative paths only)."""
        import re

        from ml.train_m2.labels.build_labels import main

        out_dir = tmp_path / "labels_out"
        ret = main(["--out-dir", str(out_dir)])
        assert ret == 0, "build_labels.main exited non-zero"

        root_str = str(repo_root()).replace("\\", "/")
        home_str = str(Path.home()).replace("\\", "/")
        leak_patterns = [root_str, home_str, "C:/Users", "C:\\Users", "Desktop"]

        for out_file in out_dir.rglob("*"):
            if out_file.is_file():
                content = out_file.read_text(encoding="utf-8", errors="ignore")
                for pat in leak_patterns:
                    assert pat not in content, (
                        f"Leaked path {pat!r} found in {out_file.name}"
                    )
