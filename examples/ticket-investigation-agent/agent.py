"""Reference agent built on TraceMemory.

This example demonstrates how a domain-specific agent uses TraceMemory as
infrastructure instead of owning checkpointing, trace storage, recovery, and
execution memory internally.
"""

from __future__ import annotations

from tracememory import TraceMemoryClient


def run_ticket_investigation(base_url: str, task: str) -> dict:
    """Run a support-ticket investigation through the TraceMemory SDK."""
    tm = TraceMemoryClient(base_url=base_url)

    run = tm.start_run(
        agent_id="ticket-investigation-agent",
        task=task,
        dataset_type="support_tickets",
        idempotency_key="ticket-demo-001",
    )
    task_id = run["task_id"]

    tm.record_event(
        task_id,
        code="plan_prepared",
        payload={"plan": ["fetch support tickets", "follow continuation signals", "save checkpoint", "summarise recurring issues"]},
    )

    tm.record_tool_trace(
        task_id,
        tool="fetch_support_tickets",
        input={"status": "open"},
        output={"items_count": 50, "next_page_token": "page_2"},
        observed_signals={"next_page_token": "page_2"},
        validation={"condition": "continue until next_page_token is null", "passed": False},
    )

    checkpoint = tm.save_checkpoint(
        task_id,
        checkpoint_name="support-page-1",
        state={"page": 1, "next_page_token": "page_2", "partial_findings": ["billing delay"]},
        resume_state={"current_step": "fetch_remaining_records", "page_token": "page_2", "validated_records": 50},
    )

    restored = tm.restore_checkpoint(checkpoint["checkpoint_id"])
    recovered = tm.recover_task(
        checkpoint["checkpoint_id"],
        task_description="Resume support-ticket investigation from saved cursor",
        agent_id="ticket-investigation-agent",
        dataset_type="support_tickets",
        idempotency_key="ticket-demo-recover-001",
    )

    return {"run": run, "checkpoint": checkpoint, "restored": restored, "recovered": recovered}
