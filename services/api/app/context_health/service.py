from __future__ import annotations

from app.context_health.schemas import (
    ContextBuildRequest,
    ContextBuildResponse,
    ContextCandidate,
    ContextDecision,
    ContextDiagnostics,
    ContextReceipt,
    DemoScenario,
    utc_now,
)


class ContextHealthService:
    """Portable ContextOps-derived context-health engine for TraceMemory.

    This is intentionally deterministic and provider-agnostic. It can run without
    an LLM and can be called before an OpenClaw/LangChain/CrewAI agent step.
    """

    def build_context(self, payload: ContextBuildRequest) -> tuple[ContextBuildResponse, ContextReceipt]:
        decisions = [self._decide(item, payload) for item in payload.candidate_context]
        clean_parts: list[str] = []
        for decision, item in zip(decisions, payload.candidate_context, strict=False):
            if decision.policy_status in {"excluded", "requires_approval"}:
                continue
            text = item.content or item.summary or ""
            if decision.action == "compress":
                text = self._compress(text or item.summary, max_chars=900)
            if decision.action == "redact":
                text = self._redact(text)
            if text:
                clean_parts.append(f"SOURCE: {item.source_ref}\nTITLE: {item.title or item.source_type}\n{text.strip()}")
        clean_context = "\n\n---\n\n".join(clean_parts)
        diagnostics = self._diagnostics(decisions, payload.candidate_context)
        receipt = ContextReceipt(
            task=payload.task,
            agent_type=payload.agent_type,
            organisation_id=payload.organisation_id,
            workspace_id=payload.workspace_id,
            project_id=payload.project_id,
            environment_id=payload.environment_id,
            decisions=decisions,
            diagnostics=diagnostics,
        )
        response = ContextBuildResponse(
            receipt_id=receipt.receipt_id,
            clean_context=clean_context,
            decisions=decisions,
            diagnostics=diagnostics,
            created_at=receipt.created_at,
        )
        return response, receipt

    def scenarios(self) -> list[DemoScenario]:
        return [
            DemoScenario(
                scenario_id="stale_policy",
                name="Stale policy blocked before agent run",
                description="Shows stale/archived context being excluded before the agent acts.",
                task="Investigate a refund dispute and recommend whether the customer should be reimbursed.",
                agent_type="support_investigation_agent",
                token_budget=6000,
                candidate_context=[
                    ContextCandidate(source_ref="policy/refunds-2023", source_type="policy", title="Old refund policy", summary="Archived 2023 refund rule", content="Refunds are not allowed after 7 days.", token_estimate=80, relevance_score=85, freshness_score=20, trust_score=75, metadata={"archived": True}),
                    ContextCandidate(source_ref="policy/refunds-2026", source_type="policy", title="Current refund policy", summary="Current refund policy", content="Refunds may be approved within 30 days where fulfilment evidence is incomplete.", token_estimate=95, relevance_score=92, freshness_score=92, trust_score=82),
                ],
            ),
            DemoScenario(
                scenario_id="bloated_tool_schema",
                name="Large tool schema compressed",
                description="Shows token bloat control for tool/context exposure.",
                task="Plan a supplier-risk investigation using available tools without exposing unnecessary schema details.",
                agent_type="web_intelligence_agent",
                token_budget=4000,
                candidate_context=[
                    ContextCandidate(source_ref="tool/web-search-schema", source_type="tool_schema", title="Web search tool schema", summary="Very large schema", content="field: value\n" * 800, token_estimate=9000, relevance_score=75, freshness_score=80, trust_score=70, action="compress"),
                    ContextCandidate(source_ref="memory/supplier-risk-playbook", source_type="memory", title="Supplier risk playbook", summary="Approved investigation playbook", content="Check sanctions, recent negative news, ownership links, and logistics dependency risks.", token_estimate=110, relevance_score=90, freshness_score=75, trust_score=90),
                ],
            ),
        ]

    def _decide(self, item: ContextCandidate, payload: ContextBuildRequest) -> ContextDecision:
        if item.sensitivity_level == "secret":
            return self._decision(item, "exclude", "excluded", "ctx-secret-block-v2", "Secrets or credentials must not enter agent context", 0)
        if item.sensitivity_level == "high":
            return self._decision(item, "require_approval", "requires_approval", "ctx-high-sensitivity-approval-v1", "High-sensitivity context requires human approval", 0)
        if item.verification_status not in {"source_verified", "verified", "trusted"}:
            return self._decision(item, "exclude", "excluded", "ctx-unverifiable-exclude-v1", "Context source could not be verified", 0)
        if item.freshness_score < 35:
            return self._decision(item, "exclude", "excluded", "ctx-stale-block-v1", "Context is stale or archived", 0)
        if item.relevance_score < 35:
            return self._decision(item, "exclude", "excluded", "ctx-low-relevance-exclude-v2", "Context is not relevant enough to the current task", 0)
        if item.trust_score < 35:
            return self._decision(item, "exclude", "excluded", "ctx-low-trust-exclude-v1", "Context source trust is too low", 0)
        if item.sensitivity_level == "medium":
            return self._decision(item, "redact", "redacted", "ctx-redaction-v2", "Medium sensitivity context is allowed after redaction", max(1, item.token_estimate // 2))
        if item.token_estimate > max(payload.token_budget // 2, 2500) or item.action == "compress":
            return self._decision(item, "compress", "allow_compressed", "ctx-large-context-compress-v2", "Large context must be compressed before use", min(item.token_estimate, max(300, payload.token_budget // 4)))
        if item.action == "delegate":
            return self._decision(item, "delegate", "allow_scoped", "ctx-scoped-delegation-v2", "Context allowed only inside scoped subagent review", item.token_estimate)
        return self._decision(item, "include", "allow", "ctx-default-allow-v2", "Context passed relevance, freshness, safety, trust and verification checks", item.token_estimate)

    def _decision(self, item: ContextCandidate, action, status, policy_id, reason, included_tokens: int) -> ContextDecision:
        return ContextDecision(
            source_ref=item.source_ref,
            source_type=item.source_type,
            title=item.title,
            action=action,
            policy_status=status,
            policy_id=policy_id,
            reason=reason,
            relevance_score=item.relevance_score,
            freshness_score=item.freshness_score,
            trust_score=item.trust_score,
            token_estimate=item.token_estimate,
            included_tokens=included_tokens,
            metadata=item.metadata,
        )

    def _diagnostics(self, decisions: list[ContextDecision], candidates: list[ContextCandidate]) -> ContextDiagnostics:
        warnings: list[str] = []
        if any(d.policy_id == "ctx-stale-block-v1" for d in decisions):
            warnings.append("Stale context excluded before agent execution.")
        if any(d.policy_id == "ctx-large-context-compress-v2" for d in decisions):
            warnings.append("Large context compressed to reduce token bloat and attention dilution.")
        if any(d.policy_status == "requires_approval" for d in decisions):
            warnings.append("Human approval required before high-risk context can be used.")
        return ContextDiagnostics(
            total_candidates=len(decisions),
            included=sum(d.policy_status == "allow" for d in decisions),
            compressed=sum(d.policy_status == "allow_compressed" for d in decisions),
            redacted=sum(d.policy_status == "redacted" for d in decisions),
            excluded=sum(d.policy_status == "excluded" for d in decisions),
            requires_approval=sum(d.policy_status == "requires_approval" for d in decisions),
            total_candidate_tokens=sum(c.token_estimate for c in candidates),
            total_included_tokens=sum(d.included_tokens for d in decisions),
            warnings=warnings,
        )

    def _compress(self, text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        return text[:max_chars].rstrip() + "\n[compressed by TraceMemory Context Health]"

    def _redact(self, text: str) -> str:
        redacted = text.replace("api_key", "[redacted_key]").replace("password", "[redacted_password]")
        return redacted
