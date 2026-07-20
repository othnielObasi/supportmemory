import pytest

from app.services.agent_runner import AgentRunner
from app.services.governance import GovernanceService


@pytest.mark.asyncio
async def test_coding_agent_uses_refactor_tool_not_ticket_tool():
    runner = AgentRunner(GovernanceService())
    trace = await runner.run(
        task_description="Refactor the auth module to async and make the full test suite pass.",
        agent_id="coding-agent",
        dataset_type="code_refactor_evidence",
        context_prefix="",
    )
    assert trace.tool_calls[0].tool == "run_refactor_step"
    assert "passed" in trace.final_output
    assert "failed" in trace.final_output


def test_coding_agent_failure_sets_test_regression_type():
    import asyncio
    from app.models.schemas import FailureType

    runner = AgentRunner(GovernanceService())
    trace = asyncio.run(runner.run(
        task_description="Refactor the auth module to async and make the full test suite pass.",
        agent_id="coding-agent",
        dataset_type="code_refactor_evidence",
        context_prefix="",
    ))
    assert trace.failure_type == FailureType.test_regression


def test_reflection_fallback_produces_async_pool_lesson_for_test_regression():
    from app.services.reflection_service import ReflectionService
    from app.models.schemas import ExecutionTrace, FailureType, TraceStatus, new_id

    service = ReflectionService(store=None, gateway=None)
    trace = ExecutionTrace(
        _id=new_id("trace"), task_id=new_id("task"), agent_id="coding-agent",
        task_description="Refactor the auth module to async.",
        context_prefix="", status=TraceStatus.success, failure_type=FailureType.test_regression,
        tool_calls=[], final_output="2 passed, 2 failed",
    )
    insight, rule, confidence = service._derive_fallback(trace)
    assert "async database connection pool" in rule
    assert confidence >= 0.85


@pytest.mark.asyncio
async def test_coding_agent_unknown_dataset_type_raises_cleanly():
    runner = AgentRunner(GovernanceService())
    with pytest.raises(ValueError, match="Unknown dataset_type"):
        await runner.run(
            task_description="Refactor something.",
            agent_id="coding-agent",
            dataset_type="not_a_real_dataset",
            context_prefix="",
        )


@pytest.mark.asyncio
async def test_ticket_agent_still_uses_ticket_tool():
    runner = AgentRunner(GovernanceService())
    trace = await runner.run(
        task_description="Analyse all support tickets.",
        agent_id="ticket-investigation-agent",
        dataset_type="support_tickets",
        context_prefix="",
    )
    assert trace.tool_calls[0].tool == "fetch_tickets"
