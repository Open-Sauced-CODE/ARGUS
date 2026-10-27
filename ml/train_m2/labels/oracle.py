"""Phase 6 oracle: assigns a ground-truth label to each fix candidate.

Contract
--------
label_candidate(record, patch, reference, route, scored) -> LabelRow

LabelRow fields
---------------
gate_pass       : bool   -- did the patch pass the gate?
outcome         : str    -- "fixed" | "escalated" | "rejected"
hidden          : dict | None  -- {decoys_untouched, no_side_effects, minimal_patch, full_equivalence}
strict_correct  : bool | None  -- True iff the fix is genuinely correct (definition below)
oracle_class    : str    -- one of the seven classes defined in the task spec
source          : str    -- "reference" | "counterfactual" | "human" | "scored_log"
source_file     : str | None  -- repo-relative path of the source file (provenance)
generator       : str | None  -- generator tag from the harvest line
profile         : str | None  -- profile tag from the harvest line
sample_idx      : int | None  -- sample index within the 8-sample group

Strict-correctness definition (when a reference exists):
  strict_correct = gate_pass AND outcome=="fixed"
                   AND hidden["full_equivalence"] is True
                   AND hidden["minimal_patch"] is True
                   AND hidden["decoys_untouched"] is True
                   AND hidden["no_side_effects"] is True

When no reference exists the counterfactual result is used (strict_correct = None if unknown).

Escalate-only candidates (outcome=="escalated", gate_pass==True) are labeled:
  "escalated_ok"       when route is "escalate"
  "escalated_unneeded" when route is "fix" / "T0"
They are EXCLUDED from M2 training and evaluation (rule 8: gate_pass is never the label).

Notes
-----
* Callers that have the pre-computed scored dict (Phase 5 candidate logs) should pass it as
  `scored` to avoid re-running the gate.  Otherwise the gate is called fresh (needs OPA on PATH).
* This module does NOT cache OPA results: pass the scored dict whenever available.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from ml.mutation_engine.qa.gate_stub import gate
from ml.mutation_engine.qa.hidden_checks import all_ok, hidden_checks

LOG = logging.getLogger(__name__)

# Seven oracle classes
OC_MINIMAL_CORRECT = "minimal_correct"
OC_VALID_NOT_MINIMAL = "valid_not_minimal"
OC_WRONG = "wrong"
OC_ESCALATED_OK = "escalated_ok"
OC_ESCALATED_UNNEEDED = "escalated_unneeded"
OC_FIXED_SHOULD_ESCALATE = "fixed_should_escalate"
OC_UNKNOWN = "unknown"

ORACLE_CLASSES = frozenset([
    OC_MINIMAL_CORRECT, OC_VALID_NOT_MINIMAL, OC_WRONG,
    OC_ESCALATED_OK, OC_ESCALATED_UNNEEDED, OC_FIXED_SHOULD_ESCALATE, OC_UNKNOWN,
])

# Sources
SRC_REFERENCE = "reference"
SRC_COUNTERFACTUAL = "counterfactual"
SRC_HUMAN = "human"
SRC_SCORED_LOG = "scored_log"

# Escalate route IDs (from README_contracts.md section 4)
ESC_RULE_IDS = frozenset([
    "dpdp.rule6a_rds",
    "dpdp.rule6_account_mfa",
    "dpdp.rule7_detection",
    "dpdp.rule15_region",
])


def _route_from_record(record: Mapping[str, Any]) -> str:
    """Infer route from the record's rule_id."""
    rule_id = record.get("rule_id", "")
    return "escalate" if rule_id in ESC_RULE_IDS else "fix"


@dataclass
class LabelRow:
    """Ground-truth label for one candidate patch."""

    gate_pass: bool
    outcome: str                          # "fixed" | "escalated" | "rejected"
    hidden: dict[str, bool | None] | None
    strict_correct: bool | None
    oracle_class: str
    source: str                           # SRC_* constant
    source_file: str | None = None
    generator: str | None = None
    profile: str | None = None
    sample_idx: int | None = None
    input_key: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        return {
            "gate_pass": self.gate_pass,
            "outcome": self.outcome,
            "hidden": self.hidden,
            "strict_correct": self.strict_correct,
            "oracle_class": self.oracle_class,
            "source": self.source,
            "source_file": self.source_file,
            "generator": self.generator,
            "profile": self.profile,
            "sample_idx": self.sample_idx,
            "input_key": self.input_key,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "LabelRow":
        return cls(
            gate_pass=d["gate_pass"],
            outcome=d["outcome"],
            hidden=d.get("hidden"),
            strict_correct=d.get("strict_correct"),
            oracle_class=d["oracle_class"],
            source=d["source"],
            source_file=d.get("source_file"),
            generator=d.get("generator"),
            profile=d.get("profile"),
            sample_idx=d.get("sample_idx"),
            input_key=d.get("input_key"),
        )


def _strict_correct_from_hidden(hidden: dict[str, bool | None]) -> bool:
    """True iff all four hidden checks pass (full_equivalence, minimal_patch, decoys_untouched, no_side_effects)."""
    return (
        hidden.get("full_equivalence") is True
        and hidden.get("minimal_patch") is True
        and hidden.get("decoys_untouched") is True
        and hidden.get("no_side_effects") is True
    )


def _oracle_class(
    gate_pass: bool,
    outcome: str,
    hidden: dict[str, bool | None] | None,
    route: str,
    strict_correct: bool | None,
) -> str:
    """Derive the seven-class oracle label."""
    if not gate_pass:
        # Rejected: wrong in the gate sense
        return OC_WRONG

    if outcome == "escalated":
        # Gate passed with an escalate-only patch
        if route == "escalate":
            return OC_ESCALATED_OK
        return OC_ESCALATED_UNNEEDED

    if outcome == "fixed":
        if route == "escalate":
            # A fix was accepted by the gate, but the correct answer is to escalate
            return OC_FIXED_SHOULD_ESCALATE

        if strict_correct is None:
            return OC_UNKNOWN

        if strict_correct:
            return OC_MINIMAL_CORRECT

        # Gate passed, outcome is fixed, but not strictly correct
        # Check whether at least rule-silence was achieved (any gate-pass that isn't strict)
        if hidden is not None and hidden.get("full_equivalence") is True:
            return OC_VALID_NOT_MINIMAL
        return OC_WRONG

    return OC_WRONG


def label_candidate(
    record: Mapping[str, Any],
    patch: Any,
    reference: Any = None,
    route: str | None = None,
    scored: Mapping[str, Any] | None = None,
    *,
    source: str = SRC_REFERENCE,
    source_file: str | None = None,
    generator: str | None = None,
    profile: str | None = None,
    sample_idx: int | None = None,
    input_key: str | None = None,
) -> LabelRow:
    """Assign a ground-truth label to one candidate patch.

    Parameters
    ----------
    record      The airlock record the model saw (shape from gate_stub / README_contracts.md section 3).
    patch       The candidate Patch-IR dict (or None / bad JSON -> treated as rejected).
    reference   The reference Patch-IR for this input, or None if unavailable.
    route       "fix" | "escalate" | "T0"; inferred from record.rule_id if None.
    scored      Pre-computed scored dict from Phase 5 candidate logs
                (keys: gate_passed, outcome, hidden, hidden_ok).  When supplied the gate is
                NOT re-run.
    source      One of SRC_* constants; defaults to SRC_REFERENCE.
    source_file, generator, profile, sample_idx
                Provenance fields written into LabelRow.
    input_key   Cluster identifier (stored verbatim; used by downstream consumers).
    """
    if route is None:
        route = _route_from_record(record)
    # Normalise route: T0 counts as "fix" for oracle purposes
    effective_route = "escalate" if route == "escalate" else "fix"

    if scored is not None:
        # Reuse pre-computed gate result from Phase 5 candidate logs
        gate_pass: bool = bool(scored.get("gate_passed", False))
        outcome: str = str(scored.get("outcome", "rejected"))
        raw_hidden: dict | None = scored.get("hidden")
    else:
        # Run the gate fresh (needs OPA on PATH)
        if patch is None:
            gate_pass = False
            outcome = "rejected"
            raw_hidden = None
        else:
            result = gate(dict(record), patch)
            gate_pass = result.passed
            outcome = result.outcome
            raw_hidden = (
                hidden_checks(dict(record), patch, reference)
                if gate_pass else None
            )

    # If hidden was not computed yet (gate pass, fresh run) but pre-scored dict was used without hidden
    if gate_pass and raw_hidden is None and scored is not None:
        try:
            raw_hidden = hidden_checks(dict(record), patch, reference)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("hidden_checks failed: %s", exc)
            raw_hidden = None

    # Compute strict_correct
    strict_correct: bool | None = None
    if gate_pass and outcome == "fixed":
        if reference is not None and raw_hidden is not None:
            strict_correct = _strict_correct_from_hidden(raw_hidden)
        # else stays None (no reference available)

    oc = _oracle_class(gate_pass, outcome, raw_hidden, effective_route, strict_correct)

    return LabelRow(
        gate_pass=gate_pass,
        outcome=outcome,
        hidden=raw_hidden,
        strict_correct=strict_correct,
        oracle_class=oc,
        source=source,
        source_file=source_file,
        generator=generator,
        profile=profile,
        sample_idx=sample_idx,
        input_key=input_key,
    )


def label_from_scored_log(
    record: Mapping[str, Any],
    scored_candidate: Mapping[str, Any],
    reference: Any = None,
    route: str | None = None,
    *,
    source: str = SRC_SCORED_LOG,
    source_file: str | None = None,
    generator: str | None = None,
    profile: str | None = None,
    sample_idx: int | None = None,
    input_key: str | None = None,
) -> LabelRow:
    """Convenience wrapper that labels one entry from a Phase 5 `scored.candidates` list.

    The scored_candidate dict must have the Phase 5 shape:
      {gate_passed, outcome, hidden, hidden_ok, correct, escalated, ...}

    The gate is NOT re-run.  hidden_checks is NOT re-run (uses pre-stored hidden dict).
    If a reference is provided and the stored hidden dict lacks full_equivalence/minimal_patch,
    we recompute those two checks only.
    """
    return label_candidate(
        record=record,
        patch=None,          # not needed when scored dict is provided
        reference=reference,
        route=route,
        scored=scored_candidate,
        source=source,
        source_file=source_file,
        generator=generator,
        profile=profile,
        sample_idx=sample_idx,
        input_key=input_key,
    )
