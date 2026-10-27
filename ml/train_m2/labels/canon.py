"""Canonical forms of Patch-IR answers.

Two answers are the SAME answer when they have the same ops and the same rationale_ref; finding_id and
resource_ref never matter. Used by the intake report (diversity of samples) and later by the feature store.
"""

from __future__ import annotations

import json
from typing import Any, Iterable, Mapping

EMPTY = "EMPTY"
INVALID = "INVALID"

__all__ = ["EMPTY", "INVALID", "canonical_answer", "is_escalate_only", "distinct_answers"]


def canonical_answer(content: str | None) -> str:
    """Stable string key for the meaning of one model answer.

    Empty text gives EMPTY; text that is not a JSON object gives INVALID.
    """
    if not content or not str(content).strip():
        return EMPTY
    try:
        obj = json.loads(content)
    except (TypeError, ValueError):
        return INVALID
    if not isinstance(obj, dict):
        return INVALID
    return json.dumps(
        {"ops": obj.get("ops"), "rationale_ref": obj.get("rationale_ref")},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def is_escalate_only(ops: Iterable[Mapping[str, Any]] | None) -> bool:
    """True when the patch is nothing but escalate operations (and there is at least one)."""
    ops = list(ops or [])
    return bool(ops) and all(isinstance(o, Mapping) and o.get("op") == "escalate" for o in ops)


def distinct_answers(contents: Iterable[str | None]) -> int:
    """Number of different non-empty answers among raw model outputs (INVALID counts as one kind)."""
    return len({canonical_answer(c) for c in contents if c and str(c).strip()})
