"""Unit tests for ml/train_m2/eval/oof_truncate.py (P6k)."""
from __future__ import annotations

import json

from ml.train_m2.eval.oof_truncate import (
    first_json_prefix,
    has_trailing_text,
    matches_reference_canonical,
    trailing_text_inside_json,
)

VALID_OBJ = {
    "finding_id": "F-0",
    "resource_ref": "BUCKET_1",
    "ops": [{"op": "set_attr", "attr": "logging_enabled", "value": True}],
    "rationale_ref": "dpdp.rule6_logging",
}


def test_first_json_prefix_trailing_junk_accepted() -> None:
    """Valid Patch-IR JSON followed by assistant/trailing junk is accepted."""
    content = json.dumps(VALID_OBJ) + "\nassistant\n<think>\nreasoning\n</think>\n{}"
    obj, ok = first_json_prefix(content)
    assert ok is True
    assert obj == VALID_OBJ
    assert has_trailing_text(content) is True
    assert trailing_text_inside_json(obj) is False


def test_first_json_prefix_leading_junk_rejected() -> None:
    """Leading junk before a valid JSON object must be rejected (no searching forward)."""
    content = "assistant\n<think>\n</think>\n" + json.dumps(VALID_OBJ)
    obj, ok = first_json_prefix(content)
    assert ok is False
    assert obj is None


def test_first_json_prefix_schema_invalid_rejected() -> None:
    """JSON object at index 0 that fails remediate/patch_ir/schema.json is rejected."""
    bad_obj = {"finding_id": "F-0", "resource_ref": "bad_ref_lowercase", "ops": []}
    obj, ok = first_json_prefix(json.dumps(bad_obj) + "\nextra")
    assert ok is False
    assert obj is None


def test_first_json_prefix_unterminated_think_tail_accepted() -> None:
    """Complete first JSON object followed by unterminated <think> tail is accepted."""
    content = (
        json.dumps(VALID_OBJ)
        + "\nassistant\n<think>\n1. Analyze input\n2. Cut off mid-sentence without closing tag"
    )
    obj, ok = first_json_prefix(content)
    assert ok is True
    assert obj == VALID_OBJ
    assert has_trailing_text(content) is True
    assert trailing_text_inside_json(obj) is False


def test_first_json_prefix_empty_or_non_dict_rejected() -> None:
    """Empty strings and non-dict JSON values at index 0 are rejected."""
    for bad in ("", "   ", "[1, 2, 3]", '"hello"', "not json"):
        obj, ok = first_json_prefix(bad)
        assert ok is False
        assert obj is None


def test_matches_reference_canonical_ignores_finding_id_and_resource_ref() -> None:
    """Canonical comparison uses only ops and rationale_ref."""
    cand = {
        "finding_id": "F-9",
        "resource_ref": "RESOURCE_2",
        "ops": [{"op": "set_attr", "attr": "logging_enabled", "value": True}],
        "rationale_ref": "dpdp.rule6_logging",
    }
    assert matches_reference_canonical(cand, VALID_OBJ) is True
    assert trailing_text_inside_json({"ops": [{"op": "escalate", "reason": "bad <think>"}]}) is True
