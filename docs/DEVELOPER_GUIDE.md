# Developer Guide

This guide explains how developers build agents on top of TraceMemory.

TraceMemory is designed as infrastructure. Your agent remains responsible for domain logic, tool choice, and final responses. TraceMemory provides durable execution context, checkpoints, recovery, task versions, trace evidence, and approved execution memory.

---

## Integration Pattern

```text
Your agent / LangGraph / CrewAI / custom runtime
        ↓
TraceMemory SDK or HTTP API
        ↓
TraceMemory API service
        ↓
PostgreSQL context engine
```

---

## Core Concepts

### Run

A run represents one long-running agent workflow.

### Run Event

A run event is a durable lifecycle event such as:

```text
request_received
understanding_generated
plan_prepared
runtime_decision
tool_execution_started
trace_recorded
checkpoint_saved
interruption_detected
checkpoint_restored
task_modified
memory_created_or_retrieved
final_answer
```

### Tool Trace

A tool trace records what an agent called, what the tool returned, and which validation condition was checked.

### Checkpoint

A checkpoint stores resumable state. It should be saved after important safe execution boundaries.

### Task Version

A task version records user changes to the task, preserving consistency across modifications.

### Execution Memory

Execution memory is an approved reusable lesson derived from a run or trace. It is not raw chat history.

---

## Recommended Agent Lifecycle

```text
1. start_run()
2. record_event("understanding_generated")
3. record_event("plan_prepared")
4. record_event("runtime_decision")
5. record_tool_trace()
6. save_checkpoint()
7. approve_memory() when useful
8. restore_checkpoint() on interruption
9. modify_task() when scope changes
10. list_events() for evidence/UI
```

---

## Python Example

```python
from tracememory import TraceMemoryClient

client = TraceMemoryClient(base_url="https://api.example.com")

run = client.start_run(
    agent_id="claims-agent",
    task="Investigate open claims and compliance blockers",
    dataset_type="support_tickets",
    idempotency_key="claims-run-001",
)

task_id = run["task_id"]

client.record_event(task_id, "understanding_generated", {
    "goal": "Investigate open claims",
    "sources": ["support_tickets", "compliance_tickets"],
})

client.record_event(task_id, "plan_prepared", {
    "plan": [
        "retrieve support tickets",
        "follow continuation signals",
        "save checkpoint",
        "extend task if compliance blockers are requested",
    ]
})

client.record_tool_trace(
    task_id=task_id,
    tool="fetch_support_tickets",
    input={"status": "open"},
    output={"records": 100, "next_page_token": "page_2"},
    validation={"condition": "continue until next_page_token is null", "passed": False},
)

checkpoint = client.save_checkpoint(
    task_id=task_id,
    checkpoint_name="support-page-1",
    state={"page": 1, "next_page_token": "page_2"},
)
```

---

## Framework Adapters

The repo includes a lightweight LangGraph adapter placeholder in:

```text
packages/sdk-python/tracememory/langgraph_adapter.py
```

The intended adapter responsibilities are:

- record node start/end events
- save checkpoints after node boundaries
- record tool traces
- restore graph state from checkpoints
- expose run events to the console

---

## Production Integration Notes

For production workloads:

- provide idempotency keys for retried requests
- checkpoint only at safe resumable boundaries
- keep secrets out of checkpoint state
- redact or hash sensitive tool inputs
- use tenant/user/workspace metadata in run records
- enforce auth before exposing run evidence
- use PostgreSQL TTL/index policies where appropriate

