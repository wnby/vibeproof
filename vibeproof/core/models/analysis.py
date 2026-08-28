"""Analyst Agent 的动作、追踪和架构报告模型。"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import Field, model_validator

from vibeproof.core.models.common import (
    AgentActionType,
    AgentRunStatus,
    ClaimStatus,
    ClaimType,
    StrictModel,
    VerificationStatus,
)
from vibeproof.core.models.repository import EvidenceReference


class ClaimDraft(StrictModel):
    claim: str = Field(min_length=1, max_length=1_000)
    claim_type: ClaimType = ClaimType.OTHER
    evidence_ids: list[str] = Field(default_factory=list, max_length=8)
    confidence: float = Field(default=0.5, ge=0, le=1)


class AnalysisClaim(ClaimDraft):
    status: ClaimStatus
    rejection_reason: str | None = None


class AgentAction(StrictModel):
    action: AgentActionType
    query: str | None = Field(default=None, max_length=200)
    summary: str | None = Field(default=None, max_length=4_000)
    claims: list[ClaimDraft] = Field(default_factory=list, max_length=30)
    unresolved_questions: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_action_payload(self) -> AgentAction:
        if self.action == AgentActionType.SEARCH_SOURCE:
            if not self.query or not self.query.strip():
                raise ValueError("SEARCH_SOURCE requires a non-empty query")
            if self.claims or self.summary or self.unresolved_questions:
                raise ValueError("SEARCH_SOURCE may only contain action and query")
        if self.action == AgentActionType.FINAL_ANSWER:
            if self.query is not None:
                raise ValueError("FINAL_ANSWER cannot contain a query")
            if not self.summary or not self.summary.strip():
                raise ValueError("FINAL_ANSWER requires a summary")
        return self


class AgentTraceStep(StrictModel):
    step: int = Field(ge=1)
    action: str
    query: str | None = None
    returned_evidence_ids: list[str] = Field(default_factory=list)
    message: str | None = None
    error: str | None = None


class ArchitectureReport(StrictModel):
    report_id: str = Field(default_factory=lambda: f"architecture:{uuid4().hex}")
    repository_name: str
    snapshot_id: str
    run_status: AgentRunStatus
    verification_status: VerificationStatus
    provider: str
    model: str
    summary: str
    claims: list[AnalysisClaim] = Field(default_factory=list)
    rejected_claims: list[AnalysisClaim] = Field(default_factory=list)
    evidence: list[EvidenceReference] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    trace: list[AgentTraceStep] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
