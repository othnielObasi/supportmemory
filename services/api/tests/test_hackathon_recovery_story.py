from app.api import RUN_EVENT_DEFINITIONS
from app.context_health.schemas import ContextBuildRequest, ContextCandidate
from app.context_health.service import ContextHealthService
from app.models.schemas import RecordToolTraceRequest, SaveCheckpointRequest


def test_hackathon_story_has_required_runtime_events():
    codes = {code for code, _, _ in RUN_EVENT_DEFINITIONS}
    required = {
        "request_received",
        "plan_prepared",
        "trace_recorded",
        "checkpoint_saved",
        "interruption_detected",
        "checkpoint_restored",
        "task_modified",
        "final_answer",
    }
    assert required.issubset(codes)


def test_hackathon_context_health_flags_stale_source():
    service = ContextHealthService()
    response, receipt = service.build_context(
        ContextBuildRequest(
            task="Investigate support and compliance blockers",
            candidate_context=[
                ContextCandidate(source_ref="stale-policy", content="Old policy", relevance_score=85, freshness_score=5, trust_score=80, token_estimate=20),
                ContextCandidate(source_ref="current-ticket", content="Current support ticket evidence", relevance_score=95, freshness_score=92, trust_score=90, token_estimate=40),
            ],
        )
    )
    assert response.diagnostics.excluded >= 1
    assert response.receipt_id == receipt.receipt_id
    assert "Old policy" not in response.clean_context
    assert "Current support ticket evidence" in response.clean_context


def test_hackathon_tool_trace_and_checkpoint_contracts():
    trace = RecordToolTraceRequest(
        tool="fetch_support_tickets",
        tool_type="read",
        input={"account_id": "acct_123", "page_token": None},
        output={"items_count": 25, "next_page_token": "page_2"},
        observed_signals={"next_page_token": "page_2"},
        validation={"status": "requires_continuation"},
    )
    checkpoint = SaveCheckpointRequest(
        state={"current_step": "fetch_remaining_records", "page_token": "page_2"}
    )
    assert trace.observed_signals["next_page_token"] == "page_2"
    assert checkpoint.state["page_token"] == "page_2"
