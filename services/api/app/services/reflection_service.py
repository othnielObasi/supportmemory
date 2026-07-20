from __future__ import annotations

import json
from typing import Any, Optional

from app.db.postgres import DESCENDING
from app.db.postgres import PostgresStore
from app.models.schemas import ExecutionTrace, FailureType, LessonStatus, ReflectionInsight, new_id


REFLECTION_SYSTEM_PROMPT = (
    "You are the reflection component of an AI agent's execution-memory system. "
    "You are given the trace of a single agent run: the task, the tools it called with their "
    "inputs/outputs and observed signals, the final output, and whether and how it failed. "
    "Derive ONE generalisable lesson that, if applied on future runs, would make the agent more "
    "reliable. The lesson must be grounded in evidence visible in THIS trace, must generalise "
    "beyond this exact task (no task-specific identifiers), and must be safe (no secrets/PII). "
    "Return STRICT JSON only, no prose, no code fences, with exactly these keys: "
    '{"insight": "<one sentence: what happened and why>", '
    '"candidate_rule": "<one imperative sentence the agent can follow next time>", '
    '"confidence": <float 0..1 reflecting how strongly the trace supports this rule>}'
)


class ReflectionService:
    """Derives a reusable lesson from an execution trace.

    The lesson is produced by reasoning over the *actual* trace via the model gateway
    (real, non-hardcoded learning). A deterministic table is retained ONLY as an explicit
    offline fallback for when no live gateway is configured or the model returns unparseable
    output; when that path is used it is recorded transparently in the insight metadata so a
    reviewer can always tell which path produced a given lesson.
    """

    def __init__(self, store: PostgresStore, gateway: Any | None = None):
        self.store = store
        self.gateway = gateway

    async def reflect(self, trace: ExecutionTrace) -> ReflectionInsight:
        derivation = "llm"
        result = await self._derive_with_model(trace)
        if result is None:
            derivation = "deterministic_fallback"
            result = self._derive_fallback(trace)
        insight, rule, confidence = result

        reflection = ReflectionInsight(
            _id=new_id('reflection'),
            source_trace_id=trace.id,
            task_id=trace.task_id,
            agent_id=trace.agent_id,
            insight=insight,
            candidate_rule=rule,
            failure_type=trace.failure_type,
            confidence=confidence,
            status=LessonStatus.pending_curation,
            derivation=derivation,
        )
        await self.store.insert_one('reflection_insights', reflection.model_dump(by_alias=True))
        return reflection

    async def _derive_with_model(self, trace: ExecutionTrace) -> Optional[tuple[str, str, float]]:
        """Ask the model to reason over the real trace. Returns None if unavailable/unparseable."""
        if self.gateway is None:
            return None
        if 'local-deterministic' in str(getattr(self.gateway, 'configured_models', {})):
            return None

        user_prompt = self._render_trace(trace)
        try:
            result = await self.gateway.chat(
                system=REFLECTION_SYSTEM_PROMPT,
                user=user_prompt,
                temperature=0.2,
                max_tokens=400,
            )
        except Exception:
            return None

        content = getattr(result, 'content', '') or ''
        parsed = self._parse_json(content)
        if not parsed:
            return None
        insight = str(parsed.get('insight', '')).strip()
        rule = str(parsed.get('candidate_rule', '')).strip()
        try:
            confidence = float(parsed.get('confidence', 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        if not insight or not rule:
            return None
        confidence = max(0.0, min(1.0, confidence))
        return (insight, rule, confidence)

    @staticmethod
    def _render_trace(trace: ExecutionTrace) -> str:
        tool_lines = []
        for tc in trace.tool_calls:
            name = getattr(tc, 'tool', getattr(tc, 'name', 'tool'))
            inp = getattr(tc, 'input', getattr(tc, 'arguments', ''))
            out = getattr(tc, 'output', getattr(tc, 'result', ''))
            status = getattr(tc, 'status', '')
            tool_lines.append(f"- {name} [{status}] in={str(inp)[:200]} out={str(out)[:200]}")
        tools = "\n".join(tool_lines) if tool_lines else "(no tool calls recorded)"
        return (
            f"TASK: {trace.task_description}\n"
            f"STATUS: {trace.status}\n"
            f"FAILURE_TYPE: {trace.failure_type}\n"
            f"TOOL CALLS:\n{tools}\n"
            f"FINAL OUTPUT: {str(trace.final_output)[:600]}\n"
        )

    @staticmethod
    def _parse_json(content: str) -> Optional[dict]:
        content = content.strip()
        if content.startswith("```"):
            content = content.strip('`')
            if content.lower().startswith('json'):
                content = content[4:]
        start = content.find('{')
        end = content.rfind('}')
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            return json.loads(content[start:end + 1])
        except json.JSONDecodeError:
            return None

    def _derive_fallback(self, trace: ExecutionTrace) -> tuple[str, str, float]:
        """Deterministic, offline-safe lesson table. Used only when no live model is available."""
        if trace.failure_type == FailureType.pagination_missed:
            return ('The agent produced an incomplete result because it did not continue fetching pages when next_page_token was present.', 'For paginated APIs, continue fetching until next_page_token is null before producing a final answer.', 0.92)
        if trace.failure_type == FailureType.auth_missing:
            return ('The agent attempted a write operation before authentication was confirmed.', 'Authenticate before performing write operations.', 0.88)
        if trace.failure_type == FailureType.schema_invalid:
            return ('The agent passed malformed data to a downstream tool.', 'Validate schema before passing output to downstream tools.', 0.87)
        if trace.failure_type == FailureType.pii_blocked:
            return ('The agent attempted an external action containing sensitive personal data.', 'Scan and redact PII before using external communication tools.', 0.9)
        if trace.failure_type == FailureType.test_regression:
            return ('The async refactor failed because the database connection pool was not initialised before a module ran migrations on import.', 'Initialise the async database connection pool before any module that runs migrations on import.', 0.9)
        return ('The trace completed successfully and produced a reusable best-practice pattern.', 'Check task requirements, tool outputs, and validation status before producing a final answer.', 0.74)

    async def get(self, reflection_id: str) -> ReflectionInsight | None:
        doc = await self.store.find_one('reflection_insights', reflection_id)
        return ReflectionInsight.model_validate(doc) if doc else None

    async def list(self, limit: int = 25) -> list[ReflectionInsight]:
        docs = await self.store.find_many('reflection_insights', limit=limit, sort=[('created_at', DESCENDING)])
        return [ReflectionInsight.model_validate(doc) for doc in docs]
