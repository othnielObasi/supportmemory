from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def stable_hash(value: Any) -> str:
    """Create a deterministic SHA-256 hash for trace inputs/outputs without storing secrets in indexes."""
    payload = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class Decision(str, Enum):
    allowed = "allowed"
    blocked = "blocked"
    needs_approval = "needs_approval"


class TraceStatus(str, Enum):
    success = "success"
    failed = "failed"
    blocked = "blocked"
    partial = "partial"
    recovered = "recovered"


class RecoveryStatus(str, Enum):
    none = "none"
    checkpoint_saved = "checkpoint_saved"
    interrupted = "interrupted"
    restored = "restored"
    unsafe_to_resume = "unsafe_to_resume"


class FailureType(str, Enum):
    pagination_missed = "pagination_missed"
    auth_missing = "auth_missing"
    schema_invalid = "schema_invalid"
    pii_blocked = "pii_blocked"
    unknown_tool = "unknown_tool"
    duplicate_action = "duplicate_action"
    interrupted = "interrupted"
    test_regression = "test_regression"
    none = "none"


class LessonStatus(str, Enum):
    candidate = "candidate"
    review_required = "review_required"
    pending_curation = "pending_curation"
    approved = "approved"
    rejected = "rejected"
    disabled = "disabled"
    superseded = "superseded"
    expired = "expired"


class RunEventStatus(str, Enum):
    pending = "pending"
    active = "active"
    complete = "complete"
    failed = "failed"


class ToolType(str, Enum):
    read = "read"
    write = "write"
    external_action = "external_action"
    unknown = "unknown"


class MultimodalAttachment(BaseModel):
    """Image/audio/document attachment for multimodal SupportMemory runs."""
    type: str = Field(default="image", pattern="^(image|audio|document)$")
    url: Optional[str] = None
    data_base64: Optional[str] = None
    mime_type: str = "image/png"
    caption: Optional[str] = None
    filename: Optional[str] = None


class RunTaskRequest(BaseModel):
    task_description: str = Field(..., min_length=3)
    organisation_id: str = "org_default"
    workspace_id: str = "wrk_default"
    project_id: str = "prj_default"
    environment_id: str = "dev"
    actor_id: str = "system"
    agent_id: str = "support_agent"
    dataset_type: str = "support_tickets"
    force_no_context: bool = False
    task_version: int = Field(default=1, ge=1)
    parent_checkpoint_id: Optional[str] = None
    simulate_restart: bool = False
    simulate_model_failure: bool = Field(default=False, description='Force the first gateway attempt to fail for resilience demos.')
    task_modification: Optional[str] = None
    idempotency_key: Optional[str] = Field(default=None, description="Client-supplied key to make retries safe.")
    request_id: str = Field(default_factory=lambda: new_id("req"))
    attachments: List[MultimodalAttachment] = Field(default_factory=list)
    ingest_vision_to_kb: bool = False
    # Per-user memory: profile + conversation history injected into context_prefix
    user_id: Optional[str] = Field(default=None, max_length=128)
    conversation_id: Optional[str] = Field(default=None, max_length=128)
    persist_conversation: bool = True


class RecoverTaskRequest(BaseModel):
    checkpoint_id: str
    task_description: Optional[str] = None
    agent_id: str = "support_agent"
    dataset_type: Optional[str] = None
    task_modification: Optional[str] = None
    idempotency_key: Optional[str] = None


class ModifyTaskRequest(BaseModel):
    modification: str = Field(..., min_length=3)
    new_task_description: str = Field(..., min_length=3)
    parent_checkpoint_id: Optional[str] = None
    dataset_type: str = "compliance_tickets"
    agent_id: str = "support_agent"
    actor_id: str = "user"


class GovernanceDecision(BaseModel):
    decision: Decision
    risk_score: int = Field(ge=0, le=100)
    reason: str
    policy_flags: List[str] = Field(default_factory=list)
    tool_type: ToolType = ToolType.unknown
    requires_human_review: bool = False
    timestamp: datetime = Field(default_factory=utc_now)
    redacted_args: Optional[Dict[str, Any]] = None
    pii_mode_applied: Optional[str] = None
    pii_types_detected: List[str] = Field(default_factory=list)


class ToolCall(BaseModel):
    tool_call_id: str = Field(default_factory=lambda: new_id("toolcall"))
    tool: str
    args: Dict[str, Any]
    governance_decision: GovernanceDecision
    output: Dict[str, Any] | None = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)


class ExecutionTrace(BaseModel):
    id: str = Field(default_factory=lambda: new_id("trace"), alias="_id")
    task_id: str
    agent_id: str
    task_description: str
    context_prefix: str = ""
    status: TraceStatus
    failure_type: FailureType = FailureType.none
    tool_calls: List[ToolCall] = Field(default_factory=list)
    final_output: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    organisation_id: str = "org_default"
    workspace_id: str = "wrk_default"
    project_id: str = "prj_default"
    environment_id: str = "dev"

    class Config:
        populate_by_name = True


class TaskContract(BaseModel):
    """The original, durable definition of a task. Drift is measured against this."""
    id: str = Field(default_factory=lambda: new_id("contract"), alias="_id")
    task_id: str
    agent_id: str
    original_goal: str
    approved_scope: str = ""
    success_criteria: List[str] = Field(default_factory=list)
    forbidden_actions: List[str] = Field(default_factory=list)
    task_version: int = 1
    created_at: datetime = Field(default_factory=utc_now)

    class Config:
        populate_by_name = True


class ContractRequest(BaseModel):
    original_goal: str = Field(..., min_length=3)
    agent_id: str = "agent_demo"
    approved_scope: str = ""
    success_criteria: List[str] = Field(default_factory=list)
    forbidden_actions: List[str] = Field(default_factory=list)


class ContractResponse(BaseModel):
    contract_id: str
    task_id: str
    task_version: int
    original_goal: str


class DriftCheckRequest(BaseModel):
    current_action: str = Field(..., min_length=3)


class DriftCheckResponse(BaseModel):
    task_id: str
    aligned: bool
    severity: str            # none | minor | major
    reason: str
    contract_goal: str
    derivation: str = "llm"   # llm | deterministic_fallback


class ResumeState(BaseModel):
    current_step: str = "start"
    page_token: Optional[str] = None
    partial_results_ref: Optional[str] = None
    partial_results: List[Dict[str, Any]] = Field(default_factory=list)
    validated_records: int = 0
    pending_actions: List[Dict[str, Any]] = Field(default_factory=list)
    observed_signals: Dict[str, Any] = Field(default_factory=dict)


class TaskCheckpoint(BaseModel):
    id: str = Field(default_factory=lambda: new_id("chk"), alias="_id")
    organisation_id: str = "org_default"
    workspace_id: str = "wrk_default"
    project_id: str = "prj_default"
    environment_id: str = "dev"
    actor_id: str = "system"
    task_id: str
    trace_id: str
    agent_id: str
    task_version: int = 1
    recovery_status: RecoveryStatus = RecoveryStatus.checkpoint_saved
    dataset_type: str
    state: Dict[str, Any] = Field(default_factory=dict)
    resume_state: ResumeState = Field(default_factory=ResumeState)
    safe_to_resume: bool = True
    requires_human_review: bool = False
    memory_record_id: Optional[str] = None
    parent_checkpoint_id: Optional[str] = None
    checkpoint_name: str = "auto-checkpoint"
    created_at: datetime = Field(default_factory=utc_now)

    class Config:
        populate_by_name = True


class TaskVersion(BaseModel):
    id: str = Field(default_factory=lambda: new_id("taskver"), alias="_id")
    task_id: str
    version: int
    description: str
    modification: Optional[str] = None
    changed_fields: List[str] = Field(default_factory=list)
    actor_id: str = "system"
    parent_checkpoint_id: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)

    class Config:
        populate_by_name = True


class ToolTrace(BaseModel):
    id: str = Field(default_factory=lambda: new_id("tooltrace"), alias="_id")
    organisation_id: str = "org_default"
    workspace_id: str = "wrk_default"
    project_id: str = "prj_default"
    environment_id: str = "dev"
    actor_id: str = "system"
    task_id: str
    run_id: Optional[str] = None
    trace_id: Optional[str] = None
    checkpoint_id: Optional[str] = None
    tool_name: str
    tool_type: ToolType = ToolType.read
    input_summary: str = ""
    input_hash: str
    output_ref: Optional[str] = None
    output_hash: str
    observed_signals: Dict[str, Any] = Field(default_factory=dict)
    validation: Dict[str, Any] = Field(default_factory=dict)
    governor_decision: Optional[GovernanceDecision] = None
    idempotency_key: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)

    class Config:
        populate_by_name = True


class IdempotencyRecord(BaseModel):
    id: str = Field(default_factory=lambda: new_id("idem"), alias="_id")
    key: str
    operation: str
    status: str = "completed"
    run_id: Optional[str] = None
    trace_id: Optional[str] = None
    task_id: Optional[str] = None
    result_ref: Optional[str] = None
    result_hash: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    organisation_id: str = "org_default"
    workspace_id: str = "wrk_default"

    class Config:
        populate_by_name = True


class ReflectionInsight(BaseModel):
    id: str = Field(default_factory=lambda: new_id("reflection"), alias="_id")
    source_trace_id: str
    task_id: str
    agent_id: str
    insight: str
    candidate_rule: str
    failure_type: FailureType
    confidence: float = Field(ge=0, le=1)
    status: LessonStatus = LessonStatus.pending_curation
    derivation: str = "llm"
    organisation_id: str = "org_default"
    workspace_id: str = "wrk_default"
    project_id: str = "prj_default"
    environment_id: str = "dev"
    created_at: datetime = Field(default_factory=utc_now)

    class Config:
        populate_by_name = True


class PlaybookRule(BaseModel):
    id: str = Field(default_factory=lambda: new_id("rule"), alias="_id")
    rule_text: str
    category: str = "tool_use"
    status: LessonStatus
    source_trace_id: str = "developer"
    source_reflection_id: str = "developer"
    source_tool_trace_ids: List[str] = Field(default_factory=list)
    scope: List[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    risk_level: str = "low"
    approved_by: Optional[str] = None
    applied_runs: List[str] = Field(default_factory=list)
    superseded_by: Optional[str] = None
    success_count: int = 0
    failure_count: int = 0
    version: int = 1
    signature: str
    policy_flags: List[str] = Field(default_factory=list)
    embedding: List[float] = Field(default_factory=list)
    organisation_id: str = "org_default"
    workspace_id: str = "wrk_default"
    project_id: str = "prj_default"
    environment_id: str = "dev"
    agent_id: Optional[str] = None
    expires_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    class Config:
        populate_by_name = True


class RetrievedRule(BaseModel):
    rule_id: str
    score: float
    rule_text: str
    category: str = "tool_use"
    evidence_ids: List[str] = Field(default_factory=list)


class RetrievalEvent(BaseModel):
    id: str = Field(default_factory=lambda: new_id("retrieval"), alias="_id")
    task_id: str
    agent_id: str
    query: str
    retrieved_rules: List[RetrievedRule]
    context_prefix: str
    organisation_id: str = "org_default"
    workspace_id: str = "wrk_default"
    project_id: str = "prj_default"
    environment_id: str = "dev"
    trace_id: Optional[str] = None
    kb_hits: List[Dict[str, Any]] = Field(default_factory=list)
    graph_paths: List[Dict[str, Any]] = Field(default_factory=list)
    embedding_provider: str = "hash"
    created_at: datetime = Field(default_factory=utc_now)

    class Config:
        populate_by_name = True


class RunEvent(BaseModel):
    code: str
    label: str
    status: RunEventStatus
    description: str
    timestamp: datetime = Field(default_factory=utc_now)


class StorageContextRecord(BaseModel):
    provider: str = "PostgreSQL JSONB"
    run_collection: str = "agent_runs"
    events_collection: str = "run_events"
    checkpoints_collection: str = "task_checkpoints"
    task_versions_collection: str = "task_versions"
    traces_collection: str = "execution_traces"
    tool_traces_collection: str = "tool_traces"
    memory_collection: str = "playbook_rules"
    retrieval_collection: str = "retrieval_events"
    idempotency_collection: str = "idempotency_keys"
    governor_collection: str = "governor_decisions"


class TaskRunResponse(BaseModel):
    organisation_id: str = "org_default"
    workspace_id: str = "wrk_default"
    project_id: str = "prj_default"
    environment_id: str = "dev"
    task_id: str
    trace_id: str
    status: TraceStatus
    final_output: str
    failure_type: FailureType
    retrieved_rules: List[RetrievedRule]
    context_prefix: str
    run_events: List[RunEvent] = Field(default_factory=list)
    task_version: int = 1
    checkpoint_id: Optional[str] = None
    recovery_status: RecoveryStatus = RecoveryStatus.none
    memory_record_id: Optional[str] = None
    parent_checkpoint_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    storage_context_record: StorageContextRecord = Field(default_factory=StorageContextRecord)
    model_trace: Dict[str, Any] = Field(default_factory=dict)
    investigation_report: Optional[str] = None
    tool_investigation_summary: Optional[str] = None
    reflection_id: Optional[str] = None
    learned_rule_id: Optional[str] = None
    context_receipt_id: Optional[str] = None


class CheckpointRestoreResponse(BaseModel):
    checkpoint_id: str
    task_id: str
    trace_id: str = ""
    agent_id: str = ""
    task_version: int
    recovery_status: RecoveryStatus
    resume_from: str = "start"
    state: Dict[str, Any]
    agent_state: ResumeState = Field(default_factory=ResumeState)
    safe_to_resume: bool = True
    requires_human_review: bool = False
    memory_record_id: Optional[str] = None
    parent_checkpoint_id: Optional[str] = None
    storage_context_record: StorageContextRecord = Field(default_factory=StorageContextRecord)


class TaskModificationResponse(BaseModel):
    task_id: str
    task_version: int
    version_id: str
    parent_checkpoint_id: Optional[str]
    modification: str
    new_task_description: str


class SystemStatus(BaseModel):
    status: str
    app: str
    environment: str
    database: str
    connected: bool
    aws_ready: bool
    mcp_ready: bool = False
    collections: List[str]
    indexes_ready: bool
    production_features: List[str]
    model_routing: Dict[str, str] = Field(default_factory=dict)


class ReflectResponse(BaseModel):
    reflection_id: str
    candidate_rule: str
    confidence: float
    status: LessonStatus
    insight: str
    derivation: str = "llm"


class CurateResponse(BaseModel):
    rule_id: Optional[str] = None
    status: LessonStatus | str
    reason: str
    signature: Optional[str] = None


class RetrieveLessonsRequest(BaseModel):
    task_description: str
    agent_id: str = "support_agent"
    top_k: int = Field(default=3, ge=1, le=10)
    include_kb: bool = True
    kb_top_k: int = Field(default=3, ge=0, le=10)
    organisation_id: str = "org_default"
    workspace_id: str = "wrk_default"
    project_id: str = "prj_default"
    environment_id: str = "dev"
    include_graph: bool = True


class KbHit(BaseModel):
    chunk_id: str
    document_id: str
    title: str
    score: float
    text: str
    source_type: str = "policy"
    source_system: str = "kb"
    evidence_ids: List[str] = Field(default_factory=list)


class RetrieveLessonsResponse(BaseModel):
    retrieved_rules: List[RetrievedRule]
    context_prefix: str
    kb_hits: List[KbHit] = Field(default_factory=list)


class GraphNode(BaseModel):
    id: str = Field(default_factory=lambda: new_id("node"), alias="_id")
    organisation_id: str = "org_default"
    workspace_id: str = "wrk_default"
    project_id: str = "prj_default"
    environment_id: str = "dev"
    node_type: str
    canonical_key: str
    properties: Dict[str, Any] = Field(default_factory=dict)
    source_type: str = "manual"
    source_id: str = "manual"
    confidence: float = Field(default=1.0, ge=0, le=1)
    valid_from: datetime = Field(default_factory=utc_now)
    valid_until: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utc_now)

    class Config:
        populate_by_name = True


class GraphEdge(BaseModel):
    id: str = Field(default_factory=lambda: new_id("edge"), alias="_id")
    organisation_id: str = "org_default"
    workspace_id: str = "wrk_default"
    project_id: str = "prj_default"
    environment_id: str = "dev"
    source_node_id: str
    target_node_id: str
    relation: str
    properties: Dict[str, Any] = Field(default_factory=dict)
    evidence_ids: List[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0, le=1)
    valid_from: datetime = Field(default_factory=utc_now)
    valid_until: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utc_now)

    class Config:
        populate_by_name = True


class GraphPath(BaseModel):
    node_ids: List[str]
    relations: List[str]
    evidence_ids: List[str] = Field(default_factory=list)
    score: float = 0.0
    explanation: str = ""


class GraphNodeRequest(BaseModel):
    organisation_id: str = "org_default"
    workspace_id: str = "wrk_default"
    project_id: str = "prj_default"
    environment_id: str = "dev"
    node_type: str
    canonical_key: str
    properties: Dict[str, Any] = Field(default_factory=dict)
    source_type: str = "manual"
    source_id: str = "manual"
    confidence: float = Field(default=1.0, ge=0, le=1)
    valid_until: Optional[datetime] = None


class GraphEdgeRequest(BaseModel):
    organisation_id: str = "org_default"
    workspace_id: str = "wrk_default"
    project_id: str = "prj_default"
    environment_id: str = "dev"
    source_node_id: str
    target_node_id: str
    relation: str
    evidence_ids: List[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0, le=1)
    valid_until: Optional[datetime] = None


class GraphTraverseRequest(BaseModel):
    organisation_id: str = "org_default"
    workspace_id: str = "wrk_default"
    seed_node_ids: List[str] = Field(default_factory=list)
    query: str = ""
    relations: List[str] = Field(default_factory=list)
    max_depth: int = Field(default=2, ge=1, le=4)
    max_paths: int = Field(default=12, ge=1, le=50)


class KbIngestRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    text: str = Field(..., min_length=20, max_length=200_000)
    source_type: str = Field(default="policy", max_length=64)
    source_system: str = Field(default="kb", max_length=64)
    tags: List[str] = Field(default_factory=list)
    agent_id: str = "ticket-investigation-agent"
    chunk_chars: int = Field(default=1000, ge=200, le=4000)
    chunk_overlap: int = Field(default=150, ge=0, le=800)
    organisation_id: str = "org_default"
    workspace_id: str = "wrk_default"
    project_id: str = "prj_default"
    environment_id: str = "dev"
    expires_at: Optional[datetime] = None


class KbChunkSummary(BaseModel):
    chunk_id: str
    index: int
    char_count: int


class KbIngestResponse(BaseModel):
    document_id: str
    title: str
    chunk_count: int
    embedding_provider: str
    chunks: List[KbChunkSummary]
    source_type: str
    source_system: str
    organisation_id: str = "org_default"
    workspace_id: str = "wrk_default"


class KbDocumentSummary(BaseModel):
    document_id: str
    title: str
    source_type: str
    source_system: str
    chunk_count: int
    tags: List[str] = Field(default_factory=list)
    created_at: datetime
    agent_id: str = "ticket-investigation-agent"


class KbSearchRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=4000)
    agent_id: str = "ticket-investigation-agent"
    top_k: int = Field(default=5, ge=1, le=20)
    organisation_id: str = "org_default"
    workspace_id: str = "wrk_default"


class KbSearchResponse(BaseModel):
    hits: List[KbHit]
    context_prefix: str


class HelpdeskMockTicketRequest(BaseModel):
    """Zendesk/Freshdesk-shaped mock connector request (demo sources)."""
    ticket_id: Optional[str] = None
    dataset_type: str = "support_tickets"
    page_token: Optional[str] = None
    source_system: str = Field(default="zendesk_mock", pattern="^(zendesk_mock|freshdesk_mock)$")


class HelpdeskMockTicketResponse(BaseModel):
    source_system: str
    connector: str = "helpdesk_webhook_api"
    ticket: Dict[str, Any]
    comments: List[Dict[str, Any]] = Field(default_factory=list)
    next_page_token: Optional[str] = None
    note: str = "Mock connector — same shape as a live Zendesk/Freshdesk webhook/API ingest."


class MultimodalAnalyzeRequest(BaseModel):
    prompt: str = Field(
        default="Describe this support evidence for a customer-support agent. Extract errors, UI text, and likely root cause.",
        min_length=3,
        max_length=4000,
    )
    attachment: MultimodalAttachment
    agent_id: str = "ticket-investigation-agent"
    ingest_to_kb: bool = False
    title: Optional[str] = None
    organisation_id: str = "org_default"
    workspace_id: str = "wrk_default"
    project_id: str = "prj_default"
    environment_id: str = "dev"


class MultimodalAnalyzeResponse(BaseModel):
    analysis_id: str
    modality: str
    provider: str
    model: str
    used_fallback: bool
    summary: str
    extracted_signals: List[str] = Field(default_factory=list)
    context_prefix: str
    kb_document_id: Optional[str] = None
    note: str = ""


class FireworksPlanRequest(BaseModel):
    task_description: str = Field(..., min_length=3)
    run_events: List[str] = Field(default_factory=list)
    checkpoint_id: Optional[str] = None
    task_version: int = 1


class GatewayAttemptRecord(BaseModel):
    model: str
    role: str
    status: str
    latency_ms: int
    error: Optional[str] = None


class FireworksPlanResponse(BaseModel):
    provider: str
    model: str
    plan: str
    used_fallback: bool = False
    attempts: List[GatewayAttemptRecord] = Field(default_factory=list)


class VoiceSummaryRequest(BaseModel):
    text: str = Field(..., min_length=3, max_length=1200)
    voice_id: Optional[str] = None
    language_type: Optional[str] = None
    user_id: Optional[str] = None
    auto_learn_language: bool = True
    run_id: Optional[str] = None
    checkpoint_id: Optional[str] = None


class VoiceSummaryResponse(BaseModel):
    provider: str = "qwen"
    enabled: bool
    voice_id: Optional[str] = None
    audio_base64: Optional[str] = None
    mime_type: str = "audio/wav"
    message: str
    model: Optional[str] = None
    resolved_language: Optional[str] = None
    language_source: Optional[str] = None


class VoiceTranscribeRequest(BaseModel):
    audio_url: Optional[str] = None
    audio_base64: Optional[str] = None
    mime_type: str = "audio/wav"
    language: Optional[str] = None
    user_id: Optional[str] = None
    auto_learn_language: bool = True
    ingest_to_kb: bool = False
    title: Optional[str] = None
    agent_id: str = "ticket-investigation-agent"


class VoiceTranscribeResponse(BaseModel):
    provider: str = "qwen"
    enabled: bool
    model: Optional[str] = None
    transcript: Optional[str] = None
    message: str
    kb_document_id: Optional[str] = None
    context_prefix: str = ""
    resolved_language: Optional[str] = None
    language_source: Optional[str] = None
    learned_preference: Optional[Dict[str, Any]] = None


class LanguagePreferenceRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128)
    language: str = Field(..., min_length=2, max_length=32)


class LanguagePreferenceResponse(BaseModel):
    user_id: str
    preferred_language: str
    preferred_code: str
    source: str
    updated_at: Optional[str] = None
    detection_history: List[Dict[str, Any]] = Field(default_factory=list)


class UserPreferenceRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128)
    display_name: Optional[str] = Field(default=None, max_length=200)
    email: Optional[str] = Field(default=None, max_length=320)
    phone: Optional[str] = Field(default=None, max_length=64)
    company: Optional[str] = Field(default=None, max_length=200)
    contact_channel: Optional[str] = Field(default=None, max_length=64)
    plan_tier: Optional[str] = Field(default=None, max_length=64)
    preferred_language: Optional[str] = Field(default=None, max_length=32)
    timezone: Optional[str] = Field(default=None, max_length=64)
    extras: Dict[str, Any] = Field(default_factory=dict)
    merge_extras: bool = True
    organisation_id: str = "org_default"
    workspace_id: str = "wrk_default"


class UserPreferenceResponse(BaseModel):
    user_id: str
    display_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    contact_channel: str = "unknown"
    plan_tier: str = "unknown"
    preferred_language: Optional[str] = None
    timezone: Optional[str] = None
    extras: Dict[str, Any] = Field(default_factory=dict)
    source: str = "default"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    organisation_id: str = "org_default"
    workspace_id: str = "wrk_default"


class ConversationCreateRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128)
    title: Optional[str] = Field(default=None, max_length=200)
    channel: Optional[str] = Field(default="chat", max_length=64)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    organisation_id: str = "org_default"
    workspace_id: str = "wrk_default"


class ConversationMessageRequest(BaseModel):
    role: str = Field(default="user", max_length=32)
    content: str = Field(..., min_length=1, max_length=20_000)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ConversationMessage(BaseModel):
    message_id: str
    role: str
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None


class ConversationResponse(BaseModel):
    conversation_id: str
    user_id: str
    title: str
    channel: str = "chat"
    is_default: bool = False
    message_count: int = 0
    messages: List[ConversationMessage] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    organisation_id: str = "org_default"
    workspace_id: str = "wrk_default"


class ConversationSummary(BaseModel):
    conversation_id: str
    user_id: str
    title: str
    channel: str = "chat"
    is_default: bool = False
    message_count: int = 0
    updated_at: Optional[str] = None
    organisation_id: str = "org_default"
    workspace_id: str = "wrk_default"


class PartnerStatus(BaseModel):
    fireworks_enabled: bool
    fireworks_model: str
    gateway_enabled: bool = False
    gateway_models: Dict[str, str] = Field(default_factory=dict)
    mcp_ready: bool = False
    qwen_voice_enabled: bool = False
    qwen_tts_model: str = "qwen3-tts-flash"
    qwen_asr_model: str = "qwen3-asr-flash"
    multilingual_voice: bool = True
    livekit_planned: bool = False
    notes: List[str] = Field(default_factory=list)


class RecordEventRequest(BaseModel):
    code: str = Field(..., min_length=2)
    payload: Dict[str, Any] = Field(default_factory=dict)


class RecordEventResponse(BaseModel):
    event_id: str
    task_id: str
    code: str
    status: RunEventStatus = RunEventStatus.complete


class RecordToolTraceRequest(BaseModel):
    tool: str = Field(..., min_length=2)
    tool_type: ToolType = ToolType.read
    input: Dict[str, Any] = Field(default_factory=dict)
    output: Dict[str, Any] = Field(default_factory=dict)
    validation: Dict[str, Any] = Field(default_factory=dict)
    observed_signals: Dict[str, Any] = Field(default_factory=dict)
    checkpoint_id: Optional[str] = None
    trace_id: Optional[str] = None
    idempotency_key: Optional[str] = None


class RecordToolTraceResponse(BaseModel):
    tool_trace_id: str
    task_id: str
    tool: str
    input_hash: str
    output_hash: str


class SaveCheckpointRequest(BaseModel):
    checkpoint_name: str = Field(default="manual-checkpoint")
    state: Dict[str, Any] = Field(default_factory=dict)
    resume_state: ResumeState = Field(default_factory=ResumeState)
    safe_to_resume: bool = True
    requires_human_review: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SaveCheckpointResponse(BaseModel):
    checkpoint_id: str
    task_id: str
    checkpoint_name: str
    recovery_status: RecoveryStatus = RecoveryStatus.checkpoint_saved
    safe_to_resume: bool = True


class ApproveMemoryRequest(BaseModel):
    rule: str = Field(..., min_length=3)
    applies_to: List[str] = Field(default_factory=list)
    source_trace_ids: List[str] = Field(default_factory=list)
    source_tool_trace_ids: List[str] = Field(default_factory=list)
    confidence: float = Field(default=0.8, ge=0, le=1)
    risk_level: str = "low"
    approved_by: str = "developer"
    evidence: Dict[str, Any] = Field(default_factory=dict)
    organisation_id: str = "org_default"
    workspace_id: str = "wrk_default"
    project_id: str = "prj_default"
    environment_id: str = "dev"
    agent_id: Optional[str] = None
    expires_at: Optional[datetime] = None


class ApproveMemoryResponse(BaseModel):
    memory_record_id: str
    task_id: str
    status: LessonStatus = LessonStatus.approved


class ActionExecutionRequest(BaseModel):
    tool_name: str
    tool_type: ToolType = ToolType.external_action
    idempotency_key: str = Field(..., min_length=6)
    input: Dict[str, Any] = Field(default_factory=dict)


class ActionExecutionResponse(BaseModel):
    action_id: str
    replayed: bool = False
    decision: Decision
    result: Dict[str, Any]
    idempotency_key: str


class DemoState(BaseModel):
    traces: List[ExecutionTrace]
    reflections: List[ReflectionInsight]
    playbook_rules: List[PlaybookRule]
    retrieval_events: List[RetrievalEvent]
    task_checkpoints: List[TaskCheckpoint] = Field(default_factory=list)
    task_versions: List[TaskVersion] = Field(default_factory=list)


class GatewayHealthResponse(BaseModel):
    enabled: bool
    provider: str
    model: str
    message: str
    used_fallback: bool = False
    attempts: List[GatewayAttemptRecord] = Field(default_factory=list)


class RecoveryDemoResponse(BaseModel):
    task_response: TaskRunResponse
    final_report: str
    gateway_attempts: List[GatewayAttemptRecord] = Field(default_factory=list)
    demo_steps: List[str] = Field(default_factory=list)


class MCPToolAttemptRecord(BaseModel):
    tool_name: str
    status: str
    latency_ms: int
    endpoint: str
    error: Optional[str] = None


class MCPGatewayToolResponse(BaseModel):
    enabled: bool
    provider: str
    tool_name: str
    output: Dict[str, Any]
    validation: Dict[str, Any]
    observed_signals: Dict[str, Any]
    attempts: List[MCPToolAttemptRecord] = Field(default_factory=list)


class HackathonReadinessResponse(BaseModel):
    readiness_score: str
    verdict: str
    requirements: List[Dict[str, Any]]
    demo: RecoveryDemoResponse
    mcp_tool: MCPGatewayToolResponse
    next_actions: List[str] = Field(default_factory=list)

# -------------------------
# Enterprise adoption models
# -------------------------

class EnterpriseRole(str, Enum):
    owner = "owner"
    admin = "admin"
    developer = "developer"
    operator = "operator"
    auditor = "auditor"
    viewer = "viewer"


class EnterpriseScope(str, Enum):
    runs_read = "runs:read"
    runs_write = "runs:write"
    checkpoints_read = "checkpoints:read"
    checkpoints_write = "checkpoints:write"
    memory_read = "memory:read"
    memory_approve = "memory:approve"
    tools_read = "tools:read"
    tools_execute = "tools:execute"
    gateways_read = "gateways:read"
    gateways_write = "gateways:write"
    audit_read = "audit:read"
    admin_manage = "admin:manage"


class TenantContext(BaseModel):
    organisation_id: str = "org_default"
    workspace_id: str = "wrk_default"
    project_id: str = "prj_default"
    environment_id: str = "dev"
    actor_id: str = "system"


class OrganisationCreateRequest(BaseModel):
    name: str = Field(..., min_length=2)
    slug: str = Field(..., min_length=2)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class OrganisationResponse(BaseModel):
    organisation_id: str
    name: str
    slug: str
    created_at: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)


class WorkspaceCreateRequest(BaseModel):
    organisation_id: Optional[str] = None
    name: str = Field(..., min_length=2)
    slug: str = Field(..., min_length=2)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class WorkspaceResponse(BaseModel):
    workspace_id: str
    organisation_id: str
    name: str
    slug: str
    created_at: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ProjectCreateRequest(BaseModel):
    workspace_id: Optional[str] = None
    name: str = Field(..., min_length=2)
    slug: str = Field(..., min_length=2)
    environment_id: str = "dev"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ProjectResponse(BaseModel):
    project_id: str
    workspace_id: str
    organisation_id: str
    name: str
    slug: str
    environment_id: str
    created_at: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(..., min_length=2)
    role: EnterpriseRole = EnterpriseRole.developer
    scopes: List[str] = Field(default_factory=list)
    project_id: Optional[str] = None
    environment_id: str = "dev"
    expires_at: Optional[datetime] = None


class ApiKeyCreateResponse(BaseModel):
    api_key_id: str
    name: str
    role: EnterpriseRole
    scopes: List[str]
    key_preview: str
    api_key: str = Field(..., description="Shown once. Store it securely.")
    created_at: datetime


class ApiKeyResponse(BaseModel):
    api_key_id: str
    name: str
    role: str
    scopes: List[str]
    status: str
    key_preview: str
    created_at: datetime
    last_used_at: Optional[datetime] = None


class EnterpriseContextResponse(BaseModel):
    principal: TenantContext
    role: str
    scopes: List[str]
    auth_required: bool


class ModelGatewayConfigRequest(BaseModel):
    name: str = Field(..., min_length=2)
    provider: str = Field(default="openai")
    base_url: Optional[str] = None
    model_map: Dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ModelGatewayConfigResponse(BaseModel):
    gateway_id: str
    name: str
    provider: str
    enabled: bool
    model_map: Dict[str, str]
    health: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ToolRegistryCreateRequest(BaseModel):
    name: str = Field(..., min_length=2)
    description: str = ""
    tool_type: ToolType = ToolType.read
    schema: Dict[str, Any] = Field(default_factory=dict)
    auth_profile_id: Optional[str] = None
    permission_scope: str = "tools:execute"
    gateway: str = "mcp"
    policy: Dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class ToolRegistryResponse(BaseModel):
    tool_id: str
    name: str
    description: str
    tool_type: str
    permission_scope: str
    gateway: str
    enabled: bool
    policy: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class BackgroundJobRequest(BaseModel):
    job_type: str = Field(..., min_length=2)
    payload: Dict[str, Any] = Field(default_factory=dict)


class BackgroundJobResponse(BaseModel):
    job_id: str
    job_type: str
    status: str
    attempts: int
    payload: Dict[str, Any]
    created_at: datetime


class AuditLogResponse(BaseModel):
    audit_id: str
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    outcome: str
    actor_id: Optional[str] = None
    workspace_id: Optional[str] = None
    created_at: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)


class EnterpriseReadinessResponse(BaseModel):
    readiness_score: str
    verdict: str
    implemented_capabilities: List[Dict[str, Any]]
    remaining_hardening: List[str] = Field(default_factory=list)
    enterprise_architecture: Dict[str, Any]
