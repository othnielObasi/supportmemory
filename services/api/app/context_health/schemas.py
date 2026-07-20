from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


ContextAction = Literal["include", "compress", "redact", "exclude", "delegate", "require_approval"]
PolicyStatus = Literal["allow", "allow_compressed", "redacted", "excluded", "allow_scoped", "requires_approval"]


class ContextCandidate(BaseModel):
    source_ref: str = Field(..., min_length=1)
    source_type: str = Field(default="document")
    title: str | None = None
    summary: str = ""
    content: str = ""
    token_estimate: int = Field(default=0, ge=0)
    relevance_score: int = Field(default=50, ge=0, le=100)
    freshness_score: int = Field(default=70, ge=0, le=100)
    trust_score: int = Field(default=60, ge=0, le=100)
    sensitivity_level: Literal["low", "medium", "high", "secret"] = "low"
    verification_status: str = "source_verified"
    action: ContextAction = "include"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContextBuildRequest(BaseModel):
    task: str = Field(..., min_length=3)
    agent_type: str = "general_agent"
    organisation_id: str = "org_default"
    workspace_id: str = "wrk_default"
    project_id: str = "prj_default"
    environment_id: str = "dev"
    token_budget: int = Field(default=12000, ge=1000)
    candidate_context: list[ContextCandidate] = Field(default_factory=list)
    persist_receipt: bool = True


class ContextDecision(BaseModel):
    source_ref: str
    source_type: str
    title: str | None = None
    action: ContextAction
    policy_status: PolicyStatus
    policy_id: str
    reason: str
    relevance_score: int
    freshness_score: int
    trust_score: int
    token_estimate: int
    included_tokens: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContextDiagnostics(BaseModel):
    total_candidates: int
    included: int
    compressed: int
    redacted: int
    excluded: int
    requires_approval: int
    total_candidate_tokens: int
    total_included_tokens: int
    warnings: list[str] = Field(default_factory=list)


class ContextReceipt(BaseModel):
    receipt_id: str = Field(default_factory=lambda: new_id("ctxrcpt"))
    task: str
    agent_type: str
    organisation_id: str = "org_default"
    workspace_id: str = "wrk_default"
    project_id: str = "prj_default"
    environment_id: str = "dev"
    decisions: list[ContextDecision]
    diagnostics: ContextDiagnostics
    created_at: datetime = Field(default_factory=utc_now)


class ContextBuildResponse(BaseModel):
    receipt_id: str
    clean_context: str
    decisions: list[ContextDecision]
    diagnostics: ContextDiagnostics
    created_at: datetime


class DemoScenario(BaseModel):
    scenario_id: str
    name: str
    description: str
    task: str
    agent_type: str
    token_budget: int
    candidate_context: list[ContextCandidate]
