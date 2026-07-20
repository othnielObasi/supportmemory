# SDK Integration

TraceMemory includes Python and TypeScript SDKs so developers can build their own agents on the infrastructure layer without calling HTTP endpoints manually.

---

## Python SDK

Location:

```text
packages/sdk-python/tracememory
```

Key methods:

```python
start_run(agent_id, task, dataset_type="support_tickets", **kwargs)
record_event(task_id, code, payload=None)
record_tool_trace(task_id, tool, input, output, validation=None)
save_checkpoint(task_id, checkpoint_name, state, metadata=None)
restore_checkpoint(checkpoint_id)
modify_task(task_id, new_task_description, modification, parent_checkpoint_id=None)
approve_memory(task_id, rule, applies_to, confidence=0.8, evidence=None)
list_events(task_id)
generate_plan(task, run_events=None, checkpoint_id=None, task_version=1)
synthesize_run_summary(text, voice_id=None, run_id=None, checkpoint_id=None)
partner_status()
```

Example:

```python
from tracememory import TraceMemoryClient

client = TraceMemoryClient(base_url="http://localhost:8000")
run = client.start_run("demo-agent", "Investigate unresolved tickets")
client.record_event(run["task_id"], "plan_prepared", {"plan": ["fetch", "checkpoint", "summarise"]})
```

---

## TypeScript SDK

Location:

```text
packages/sdk-typescript/src
```

Key methods mirror the Python SDK:

```ts
startRun(input)
recordEvent(taskId, code, payload)
recordToolTrace(taskId, trace)
saveCheckpoint(taskId, checkpoint)
restoreCheckpoint(checkpointId)
modifyTask(taskId, input)
approveMemory(taskId, input)
listEvents(taskId)
generatePlan(input)
synthesizeRunSummary(input)
partnerStatus()
```

Example:

```ts
import { TraceMemoryClient } from "@tracememory/sdk";

const client = new TraceMemoryClient({ baseUrl: "http://localhost:8000" });
const run = await client.startRun({
  agentId: "ticket-agent",
  task: "Investigate support tickets",
  datasetType: "support_tickets",
});
```

---

## Adapter Strategy

Framework adapters should translate framework lifecycle events into TraceMemory run events:

| Framework event | TraceMemory event |
|---|---|
| graph invoked | `request_received` |
| planner node output | `plan_prepared` |
| tool node start | `tool_execution_started` |
| tool node output | `trace_recorded` |
| durable boundary | `checkpoint_saved` |
| graph resumed | `checkpoint_restored` |
| human changes task | `task_modified` |


---

## Production SDK primitives

The SDKs now expose production-oriented primitives:

### Python

```python
run = tm.start_run(agent_id="claims-agent", task="Investigate claim docs")

tm.record_event(run["task_id"], code="plan_prepared")

tm.record_tool_trace(
    run["task_id"],
    tool="fetch_documents",
    input={"query": "claim evidence"},
    output={"records": 120},
    observed_signals={"complete": True},
    validation={"passed": True},
)

checkpoint = tm.save_checkpoint(
    run["task_id"],
    checkpoint_name="retrieval-complete",
    state={"records_seen": 120},
    resume_state={"current_step": "summarise", "validated_records": 120},
)

restored = tm.restore_checkpoint(checkpoint["checkpoint_id"])
```

### npm

```ts
const run = await tm.startRun({ agentId: "claims-agent", task: "Investigate claim docs" });

await tm.recordEvent(run.task_id, "plan_prepared");

await tm.recordToolTrace(run.task_id, {
  tool: "fetch_documents",
  input: { query: "claim evidence" },
  output: { records: 120 },
  observedSignals: { complete: true },
  validation: { passed: true },
});

const checkpoint = await tm.saveCheckpoint(run.task_id, {
  checkpointName: "retrieval-complete",
  state: { recordsSeen: 120 },
  resumeState: { currentStep: "summarise", validatedRecords: 120 },
});

const restored = await tm.restoreCheckpoint(checkpoint.checkpoint_id);
```


## Framework adapters

TraceMemory includes SDK-level adapters so developers do not need to manually record every primitive in common agent runtimes.

Implemented adapters:

- Python LangGraph adapter: `TraceMemoryLangGraphAdapter`
- Python CrewAI adapter: `TraceMemoryCrewAIAdapter`
- Python OpenAI Agents SDK-style middleware: `TraceMemoryOpenAIAgentsMiddleware`
- Python generic tool wrapper: `trace_tool`
- npm LangGraph adapter: `TraceMemoryLangGraphAdapter`
- npm CrewAI adapter: `TraceMemoryCrewAIAdapter`
- npm OpenAI Agents SDK-style middleware: `TraceMemoryOpenAIAgentsMiddleware`
- npm generic tool wrapper: `wrapTool`

See [`FRAMEWORK_ADAPTERS.md`](FRAMEWORK_ADAPTERS.md) for full examples.
