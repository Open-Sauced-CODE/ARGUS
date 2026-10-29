"""Phase 6 corruptor: applies typed corruptions to reference patches and natural candidates.

Corruption types
----------------
C1  extra_rule_field_write   -- write an extra rule-read field that the reference does NOT write
C2  wrong_value_same_type    -- replace a value with a wrong value of the same Python type
C3  partial_fix              -- keep only a strict prefix of the reference ops (hard-negatives)
C4  duplicate_attr_write     -- duplicate one op (write the same attr twice)
C5  value_drift              -- lifecycle days x2 or /2; or swap a CIDR for INTERNAL_CIDR
C6  escalate_instead_of_fix  -- replace all fix ops with a single plausible escalate
C7  fix_instead_of_escalate  -- for ESC inputs, produce a plausible but wrong fix
C8  control_switched_off     -- flip a boolean field from True to False

All corrupted rows
  - carry source='corruptor'
  - are TRAIN-ONLY (never in calibration, risk control or evaluation)
  - may only use ops from ALLOWED_OPS (set_attr, restrict_cidr, set_lifecycle_rule, enable_feature)
  - must pass the Patch-IR JSON schema

Public interface
----------------
corrupt(record, reference, corruption_type, seed) -> Patch-IR dict | None
    Returns the corrupted patch or None if the corruption cannot be applied to this input.

make_corrupted_rows(record, reference, route, input_key, seed) -> list[dict]
    Returns one corrupted LabelRow-dict per applicable corruption type.
    Each row has all LabelRow fields plus "corruption_type".

hard_negative_stats(rows, gate_fn) -> dict
    Compute per-type gate_pass_rate, oracle_wrong_rate, hard_negative_rate.
    hard_negative_rate = P(gate_pass AND oracle wrong).

write_hard_negative_table(stats, out_path) -> None
    Writes the Markdown table to out_path.
"""

from __future__ import annotations

import copy
import json
import logging
import random as _random
from typing import Any, Mapping, Sequence

from ml.mutation_engine.labeler import schema_errors
from ml.mutation_engine.qa.gate_stub import ALLOWED_OPS
from ml.mutation_engine.qa.hidden_checks import APPROVED_ALGORITHMS, all_rule_fields
from ml.train_m2.labels.oracle import (
    ESC_RULE_IDS,
    LabelRow,
    SRC_SCORED_LOG,
    label_candidate,
)

LOG = logging.getLogger(__name__)

CORRUPTION_TYPES = ("C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8")

# DPDP retention constant (same as in counterfactual.py)
RETENTION_DAYS = 90
INTERNAL_CIDR = "INTERNAL_CIDR"

# Plausible wrong CIDR values for value-drift
WRONG_CIDRS = ("10.0.0.0/8", "192.168.0.0/16", "172.16.0.0/12")


def _all_rule_fields_list() -> list[str]:
    return sorted(all_rule_fields())


def _edit_ops(patch: dict) -> list[dict]:
    """Extract non-escalate ops from the patch."""
    return [op for op in patch.get("ops", []) if op.get("op") != "escalate"]


def _safe_patch(record: Mapping[str, Any], ops: list[dict]) -> dict:
    """Assemble a Patch-IR dict from ops; keep bookkeeping fields from record."""
    return {
        "finding_id": record.get("finding_id", "F-0"),
        "resource_ref": record.get("resource_ref", "RESOURCE_1"),
        "rationale_ref": record.get("rule_id", ""),
        "ops": ops,
    }


def _wrong_value(attr: str, current: Any, rng: _random.Random) -> Any:
    """Return a wrong value of the same Python type as current."""
    if isinstance(current, bool):
        return not current
    if isinstance(current, (int, float)):
        if current == 0:
            return 1
        return current * 2
    if isinstance(current, str):
        if current in APPROVED_ALGORITHMS:
            others = [a for a in APPROVED_ALGORITHMS if a != current]
            return rng.choice(others) if others else current + "_WRONG"
        if current == INTERNAL_CIDR:
            return "0.0.0.0/0"
        return current + "_WRONG"
    if isinstance(current, list):
        if current and isinstance(current[0], str):
            return [current[0] + "_WRONG"]
        return []
    return current  # Cannot produce a different value -> caller skips


def corrupt(
    record: Mapping[str, Any],
    reference: dict | None,
    corruption_type: str,
    seed: int = 1337,
) -> dict | None:
    """Apply one corruption type; return the corrupted patch or None if inapplicable."""
    rng = _random.Random(seed)
    rule_id = record.get("rule_id", "")
    is_esc_rule = rule_id in ESC_RULE_IDS

    if reference is None:
        # Cannot corrupt without a reference for most types
        if corruption_type not in ("C6", "C7"):
            return None

    ref_ops = _edit_ops(reference) if reference else []

    if corruption_type == "C1":
        # Extra rule-field write: add an op for a field the reference does NOT write
        if not ref_ops:
            return None
        ref_attrs = {op.get("attr") for op in ref_ops}
        rule_fields = _all_rule_fields_list()
        extras = [f for f in rule_fields if f not in ref_attrs and f != "resource_type"]
        if not extras:
            return None
        extra_field = rng.choice(extras)
        # Write True (a plausible enabling value)
        extra_op = {"op": "set_attr", "attr": extra_field, "value": True}
        new_ops = copy.deepcopy(ref_ops) + [extra_op]
        return _safe_patch(record, new_ops)

    if corruption_type == "C2":
        # Wrong value of the same type
        if not ref_ops:
            return None
        # Pick the first op with a replaceable value
        for idx, op in enumerate(ref_ops):
            new_val = _wrong_value(op.get("attr", ""), op.get("value"), rng)
            if new_val != op.get("value"):
                new_ops = copy.deepcopy(ref_ops)
                new_ops[idx] = dict(new_ops[idx], value=new_val)
                return _safe_patch(record, new_ops)
        return None

    if corruption_type == "C3":
        # Partial fix: drop the last op (only valid if there are >=2 ops)
        if len(ref_ops) < 2:
            return None
        # Keep only first n-1 ops (the shortest partial fix)
        n = rng.randint(1, len(ref_ops) - 1)
        new_ops = copy.deepcopy(ref_ops[:n])
        return _safe_patch(record, new_ops)

    if corruption_type == "C4":
        # Duplicate one attr write
        if not ref_ops:
            return None
        dup_op = rng.choice(ref_ops)
        new_ops = copy.deepcopy(ref_ops) + [copy.deepcopy(dup_op)]
        return _safe_patch(record, new_ops)

    if corruption_type == "C5":
        # Value drift
        if not ref_ops:
            return None
        new_ops = copy.deepcopy(ref_ops)
        for idx, op in enumerate(new_ops):
            val = op.get("value")
            attr = op.get("attr", "")
            if isinstance(val, (int, float)) and "day" in attr:
                new_ops[idx] = dict(op, value=val * 2)
                return _safe_patch(record, new_ops)
            if val == INTERNAL_CIDR or op.get("op") == "restrict_cidr":
                new_ops[idx] = dict(op, value=rng.choice(WRONG_CIDRS))
                return _safe_patch(record, new_ops)
        return None

    if corruption_type == "C6":
        # Escalate instead of fix (valid for fix-route inputs)
        if is_esc_rule:
            return None  # Not a corruption for ESC inputs
        esc_ops = [{"op": "escalate", "reason": "Cannot apply fix automatically (corrupted)"}]
        return _safe_patch(record, esc_ops)

    if corruption_type == "C7":
        # Fix instead of escalate (only for ESC inputs)
        if not is_esc_rule:
            return None
        # Plausible but wrong: set any rule-read boolean field to True
        rule_fields = _all_rule_fields_list()
        bool_fields = [
            f for f in rule_fields
            if f not in ("resource_type",)
            and isinstance(record.get("fields", {}).get(f, True), bool)
        ]
        if not bool_fields:
            # Fallback: set a generic field
            fix_ops = [{"op": "set_attr", "attr": "account_mfa_enabled", "value": True}]
        else:
            attr = rng.choice(bool_fields)
            fix_ops = [{"op": "set_attr", "attr": attr, "value": True}]
        return _safe_patch(record, fix_ops)

    if corruption_type == "C8":
        # Flip a boolean True field to False (turns off a control)
        fields = record.get("fields", {})
        on_fields = [k for k, v in fields.items() if v is True and k != "resource_type"]
        if not on_fields:
            return None
        chosen = rng.choice(on_fields)
        off_op = {"op": "set_attr", "attr": chosen, "value": False}
        base_ops = copy.deepcopy(ref_ops) if ref_ops else []
        new_ops = base_ops + [off_op]
        return _safe_patch(record, new_ops)

    raise ValueError(f"Unknown corruption type {corruption_type!r}")


def _deterministic_corrupt_seed(global_seed: int, input_key: str, ctype: str) -> int:
    """Derive a deterministic int seed for one (input_key, ctype) pair.

    Uses hashlib.sha256 so the result is PYTHONHASHSEED-independent (F3 fix).
    """
    import hashlib

    raw = f"{global_seed}:{input_key}:{ctype}".encode("utf-8")
    digest = hashlib.sha256(raw).digest()
    # Take the first 8 bytes as a big-endian unsigned int; mask to fit in Python int
    return int.from_bytes(digest[:8], "big") & 0x7FFF_FFFF_FFFF_FFFF


def make_corrupted_rows(
    record: Mapping[str, Any],
    reference: dict | None,
    route: str,
    input_key: str,
    seed: int = 1337,
    source_file: str | None = None,
) -> list[dict]:
    """Generate one corrupted LabelRow-dict per applicable type (TRAIN-ONLY).

    The returned dicts extend LabelRow.to_dict() with:
      "corruption_type": str
      "schema_valid": bool

    F3 fix: each (input_key, ctype) gets a deterministic seed derived from
    hashlib.sha256(f"{seed}:{input_key}:{ctype}") -- not python hash().
    """
    valid_candidates: list[tuple[str, dict, bool]] = []
    for ctype in CORRUPTION_TYPES:
        # F3 fix: use deterministic per-(input_key, ctype) seed, not python hash()
        ctype_seed = _deterministic_corrupt_seed(seed, input_key, ctype)
        patch = corrupt(record, reference, ctype, seed=ctype_seed)
        if patch is None:
            continue
        # Validate: must not introduce ops outside ALLOWED_OPS and must pass schema
        ops = patch.get("ops", [])
        invalid_ops = [op.get("op") for op in ops if op.get("op") not in ALLOWED_OPS and op.get("op") != "escalate"]
        if invalid_ops:
            LOG.warning("C%s produced invalid op %s; skipping", ctype, invalid_ops)
            continue
        errors = schema_errors(patch)
        valid_candidates.append((ctype, patch, not errors))

    if not valid_candidates:
        return []

    from ml.mutation_engine.qa.gate_stub import gate_many
    from ml.mutation_engine.qa.hidden_checks import hidden_checks

    cases = [(dict(record), patch) for _, patch, _ in valid_candidates]
    gate_results = gate_many(cases)

    rows = []
    for (ctype, patch, schema_valid), g_res in zip(valid_candidates, gate_results):
        raw_hidden = (
            hidden_checks(dict(record), patch, reference)
            if g_res.passed else None
        )
        scored = {
            "gate_passed": g_res.passed,
            "outcome": g_res.outcome,
            "hidden": raw_hidden,
        }
        label_row = label_candidate(
            record=record,
            patch=patch,
            reference=reference,
            route=route,
            scored=scored,
            source="corruptor",
            source_file=source_file,
            input_key=input_key,
        )
        row_dict = label_row.to_dict()
        row_dict["corruption_type"] = ctype
        row_dict["schema_valid"] = schema_valid
        rows.append(row_dict)
    return rows


def hard_negative_stats(rows: list[dict]) -> dict[str, dict]:
    """Per-type gate_pass_rate, oracle_wrong_rate, hard_negative_rate.

    hard_negative_rate = P(gate_pass AND oracle wrong).
    A row is oracle-wrong if oracle_class == 'wrong' ONLY.
    oracle_class == 'unknown' is EXCLUDED from wrong and counted separately (F7 fix).
    """
    from collections import defaultdict

    buckets: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        ctype = row.get("corruption_type", "?")
        buckets[ctype].append(row)

    result: dict[str, dict] = {}
    for ctype, bucket in buckets.items():
        n = len(bucket)
        gate_pass = sum(1 for r in bucket if r.get("gate_pass"))
        # F7: exclude 'unknown' from wrong count
        oracle_wrong = sum(1 for r in bucket if r.get("oracle_class") == "wrong")
        oracle_unknown = sum(1 for r in bucket if r.get("oracle_class") == "unknown")
        hard_neg = sum(
            1 for r in bucket
            if r.get("gate_pass") and r.get("oracle_class") == "wrong"
        )
        result[ctype] = {
            "n": n,
            "gate_pass_rate": gate_pass / n if n else 0.0,
            "oracle_wrong_rate": oracle_wrong / n if n else 0.0,
            "oracle_unknown_count": oracle_unknown,
            "hard_negative_rate": hard_neg / n if n else 0.0,
        }
    return result


def filter_hard_negative_types(
    stats: dict[str, dict],
) -> tuple[dict[str, dict], list[str]]:
    """Keep only corruption types with hard_negative_rate > 0.

    Returns (kept_stats, dropped_types).
    F2 fix: types with hard_negative_rate == 0 are dropped from output.
    """
    kept: dict[str, dict] = {}
    dropped: list[str] = []
    for ctype, s in stats.items():
        if s["hard_negative_rate"] > 0.0:
            kept[ctype] = s
        else:
            dropped.append(ctype)
    return kept, sorted(dropped)


def write_hard_negative_table(
    stats: dict[str, dict],
    out_path: str | None = None,
    pre_filter_stats: dict[str, dict] | None = None,
    dropped_types: list[str] | None = None,
) -> str:
    """Render hard-negative stats as a Markdown table; returns the Markdown text.

    When pre_filter_stats and dropped_types are supplied, the table includes a
    pre-filter section and a dropped-types list (F2 fix: shows what was removed).
    oracle_unknown_count column added (F7 fix).
    """
    from pathlib import Path as _Path

    def _render_table(tbl_stats: dict[str, dict], label: str) -> str:
        hdr = (
            f"## {label}\n\n"
            "| Type | n | gate_pass_rate | oracle_wrong_rate"
            " | unknown_count | hard_negative_rate |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
        )
        lines_md = []
        for ctype in sorted(tbl_stats):
            s = tbl_stats[ctype]
            lines_md.append(
                "| {} | {} | {:.3f} | {:.3f} | {} | {:.3f} |".format(
                    ctype,
                    s["n"],
                    s["gate_pass_rate"],
                    s["oracle_wrong_rate"],
                    s.get("oracle_unknown_count", 0),
                    s["hard_negative_rate"],
                )
            )
        return hdr + "\n".join(lines_md) + "\n"

    parts: list[str] = ["# Hard-negative table (corruptor, TRAIN partition)\n"]

    if pre_filter_stats is not None:
        parts.append(_render_table(pre_filter_stats, "Pre-filter (all types)"))
        dropped = sorted(dropped_types or [])
        parts.append(f"\n**Dropped types (hard_negative_rate == 0):** {', '.join(dropped) or 'none'}\n")

    parts.append(_render_table(stats, "Post-filter (kept types)"))

    text = "\n".join(parts)
    if out_path is not None:
        _Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        _Path(out_path).write_text(text, encoding="utf-8")
    return text
