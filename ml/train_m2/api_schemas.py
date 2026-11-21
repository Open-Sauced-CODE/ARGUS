"""API schemas for M2 confidence, decision, and audit trust endpoints (Shaurya-owned).

Pydantic schemas matching ml/train_m2/decide.py interfaces.
All outputs are ASCII-only.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence
from pydantic import BaseModel, ConfigDict, Field

from ml.train_m2.decide import Contribution, Decision

LOG = logging.getLogger(__name__)


class ContributionSchema(BaseModel):
    """Schema for a single feature contribution to an M2 decision."""
    model_config = ConfigDict(extra="ignore", from_attributes=True)

    feature: str
    value: float | None = None
    contribution: float
    text: str


class ConfidenceInput(BaseModel):
    """Input payload for confidence scoring endpoint."""
    model_config = ConfigDict(extra="ignore")

    features: dict[str, Any]
    spec_hash: str


class ConfidenceOutput(BaseModel):
    """Output payload from confidence scoring endpoint."""
    model_config = ConfigDict(extra="ignore")

    p_hat: float


class DecideInput(BaseModel):
    """Input payload for decision endpoint."""
    model_config = ConfigDict(extra="ignore")

    features: dict[str, Any]
    gate_passed: bool
    escalated_only: bool
    breaker: str = "CLOSED"
    config: dict[str, Any]
    tau_info: dict[str, Any]


class DecideOutput(BaseModel):
    """Output payload matching Decision dataclass from decide.py."""
    model_config = ConfigDict(extra="ignore", from_attributes=True)

    action: str
    p_hat: float | None = None
    tau: float | None = None
    bayes_cutoff: float
    threshold_used: float | None = None
    reasons: list[str] = Field(default_factory=list)
    top_contributors: list[ContributionSchema] = Field(default_factory=list)
    breaker_state: str
    model_version: str
    feature_spec_hash: str
    alpha: float
    delta: float
    cost_ratio: float

    @classmethod
    def from_decision(cls, d: Decision) -> DecideOutput:
        """Construct DecideOutput from a decide.Decision instance."""
        return cls(
            action=d.action,
            p_hat=d.p_hat,
            tau=d.tau,
            bayes_cutoff=d.bayes_cutoff,
            threshold_used=d.threshold_used,
            reasons=list(d.reasons),
            top_contributors=[
                ContributionSchema(
                    feature=c.feature,
                    value=c.value,
                    contribution=c.contribution,
                    text=c.text,
                )
                for c in d.top_contributors
            ],
            breaker_state=d.breaker_state,
            model_version=d.model_version,
            feature_spec_hash=d.feature_spec_hash,
            alpha=d.alpha,
            delta=d.delta,
            cost_ratio=d.cost_ratio,
        )


class TrustRecord(BaseModel):
    """Audit and trust record wrapping an M2 decision with execution context and timestamp."""
    model_config = ConfigDict(extra="ignore")

    record_id: str | None = None
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    decision: DecideOutput
    context: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def create(
        cls,
        decision: Decision | DecideOutput,
        context: Mapping[str, Any] | None = None,
        record_id: str | None = None,
    ) -> TrustRecord:
        """Factory method to construct a TrustRecord."""
        if isinstance(decision, Decision):
            dec_out = DecideOutput.from_decision(decision)
        else:
            dec_out = decision
        return cls(
            record_id=record_id,
            decision=dec_out,
            context=dict(context or {}),
        )
