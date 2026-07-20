from app.config import Settings
from app.models.schemas import Decision, ToolType
from app.services.governance import GovernanceService


def test_hybrid_redacts_pii_on_read_tools():
    gov = GovernanceService(Settings(RUNTIME_GOVERNOR_PII_MODE="hybrid"))
    decision = gov.evaluate_tool_call(
        "fetch_tickets",
        {"query": "customer@example.com billing delay", "dataset_type": "support_tickets"},
        {"tool_type": ToolType.read.value},
    )
    assert decision.decision == Decision.allowed
    assert "pii_redacted" in decision.policy_flags
    assert decision.redacted_args["query"] == "[REDACTED_EMAIL] billing delay"
    assert decision.pii_mode_applied == "hybrid_redact_internal"


def test_hybrid_redacts_pii_on_internal_write_tools():
    gov = GovernanceService(Settings(RUNTIME_GOVERNOR_PII_MODE="hybrid"))
    decision = gov.evaluate_tool_call(
        "update_ticket_note",
        {"note": "Call back 555-123-4567 about refund"},
        {"tool_type": ToolType.write.value, "idempotency_key": "k1"},
    )
    # update_ticket_note is internal write (not send_/refund_) → redact + allow
    assert decision.decision == Decision.allowed
    assert "pii_redacted" in decision.policy_flags
    assert "[REDACTED_PHONE]" in decision.redacted_args["note"]


def test_hybrid_requires_approval_on_external_send_with_pii():
    gov = GovernanceService(
        Settings(
            RUNTIME_GOVERNOR_PII_MODE="hybrid",
            RUNTIME_GOVERNOR_EXTERNAL_PII_MODE="require_approval",
        )
    )
    decision = gov.evaluate_tool_call(
        "send_email",
        {"to": "customer@example.com", "body": "refund approved"},
        {"tool_type": ToolType.external_action.value, "idempotency_key": "k1"},
    )
    assert decision.decision == Decision.needs_approval
    assert decision.requires_human_review is True
    assert "external_action" in decision.policy_flags
    assert "email" in decision.pii_types_detected


def test_hybrid_blocks_external_refund_when_configured():
    gov = GovernanceService(
        Settings(
            RUNTIME_GOVERNOR_PII_MODE="hybrid",
            RUNTIME_GOVERNOR_EXTERNAL_PII_MODE="block",
        )
    )
    decision = gov.evaluate_tool_call(
        "refund_payment",
        {"email": "payer@example.com", "card": "4111-1111-1111-1111"},
        {"tool_type": ToolType.external_action.value, "idempotency_key": "k1"},
    )
    assert decision.decision == Decision.blocked
    assert "action_blocked" in decision.policy_flags
    assert "external_action" in decision.policy_flags


def test_global_redact_mode_still_allows_external_after_masking():
    gov = GovernanceService(Settings(RUNTIME_GOVERNOR_PII_MODE="redact"))
    decision = gov.evaluate_tool_call(
        "send_email",
        {"to": "customer@example.com", "ssn": "123-45-6789"},
        {"tool_type": ToolType.external_action.value, "idempotency_key": "k1"},
    )
    assert decision.decision == Decision.allowed
    assert decision.redacted_args["to"] == "[REDACTED_EMAIL]"
    assert decision.redacted_args["ssn"] == "[REDACTED_SSN]"


def test_global_block_mode_blocks_non_read_pii():
    gov = GovernanceService(Settings(RUNTIME_GOVERNOR_PII_MODE="block"))
    decision = gov.evaluate_tool_call(
        "send_email",
        {"to": "customer@example.com"},
        {"tool_type": ToolType.external_action.value, "idempotency_key": "k1"},
    )
    assert decision.decision == Decision.blocked


def test_governor_allowlist_blocks_unknown_tool_name():
    gov = GovernanceService(
        Settings(
            RUNTIME_GOVERNOR_PII_MODE="hybrid",
            RUNTIME_GOVERNOR_TOOL_ALLOWLIST="fetch_tickets,run_refactor_step",
        )
    )
    decision = gov.evaluate_tool_call(
        "send_email",
        {"to": "ops@example.com"},
        {"tool_type": ToolType.external_action.value, "idempotency_key": "k1"},
    )
    assert decision.decision == Decision.blocked
    assert "tool_not_allowlisted" in decision.policy_flags


def test_governor_policy_summary_includes_hybrid():
    gov = GovernanceService(Settings(RUNTIME_GOVERNOR_PII_MODE="hybrid"))
    summary = gov.policy_summary()
    assert summary["pii_mode"] == "hybrid"
    assert summary["external_pii_mode"] == "require_approval"
    assert "hybrid" in summary["behaviors"]
