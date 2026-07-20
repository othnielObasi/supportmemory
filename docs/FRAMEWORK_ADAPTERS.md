# TraceMemory Framework Adapters

TraceMemory is designed to be framework-agnostic infrastructure. Developers can call the REST API directly, use the Python/npm SDKs, or use adapters that wrap common agent runtimes.

The adapters do not replace LangGraph, CrewAI, OpenAI Agents SDK, or custom orchestration. They add durable runtime state around those runtimes:

- run events
- tool traces
- checkpoints
- restore state
- task versions
- idempotent action records
- approved execution memory

## Adapter status

| Adapter | Package | Status | Purpose |
|---|---|---|---|
| LangGraph adapter | Python + npm | Implemented | Wrap graph nodes and save checkpoints after transitions |
| CrewAI adapter | Python + npm | Implemented | Wrap CrewAI-like task/tool functions and record handoffs |
| OpenAI Agents middleware | Python + npm | Implemented | Record lifecycle hooks and wrap tool calls |
| Generic tool wrapper | Python + npm | Implemented | Framework-neutral tool tracing and checkpointing |

These are production-oriented MVP adapters. They avoid hard dependencies on each framework so the SDK remains lightweight and import-safe. Projects can use them directly or adapt them to framework-specific extension points.

---

## LangGraph

### Python

```python
from tracememory import TraceMemoryClient, TraceMemoryLangGraphAdapter

client = TraceMemoryClient(base_url="https://api.tracememory.dev", api_key="tm_live_...")
run = client.start_run(agent_id="claims-graph", task="Investigate claim documents")
task_id = run["task_id"]

adapter = TraceMemoryLangGraphAdapter(client, task_id, graph_name="claims-graph")

def retrieve_node(state: dict) -> dict:
    return {**state, "documents": fetch_documents(state["query"])}

retrieve_node = adapter.wrap_node("retrieve", retrieve_node)
```

What is recorded:

- `tool_execution_started` for the node transition
- checkpoint with input and output state
- `checkpoint_saved` event linked to the node

### npm

```ts
import { TraceMemoryClient, TraceMemoryLangGraphAdapter } from "@tracememory/sdk";

const tm = new TraceMemoryClient("https://api.tracememory.dev", process.env.TRACEMEMORY_API_KEY);
const run = await tm.startRun({ agentId: "claims-graph", task: "Investigate claim documents" }) as any;
const adapter = new TraceMemoryLangGraphAdapter(tm, run.task_id, "claims-graph");

const retrieveNode = adapter.wrapNode("retrieve", async (state) => ({
  ...state,
  documents: await fetchDocuments(state.query),
}));
```

---

## CrewAI

### Python

```python
from tracememory import TraceMemoryClient, TraceMemoryCrewAIAdapter

client = TraceMemoryClient(base_url="https://api.tracememory.dev", api_key="tm_live_...")
run = client.start_run(agent_id="vendor-review-crew", task="Coordinate vendor review")
adapter = TraceMemoryCrewAIAdapter(client, run["task_id"], crew_name="vendor-review")

review_task = adapter.wrap_task("collect_vendor_evidence", collect_vendor_evidence)
review_task()
adapter.record_handoff("research-agent", "review-agent", {"reason": "evidence collected"})
```

What is recorded:

- task start/plan event
- checkpoint after task completion
- handoff as a task modification event

---

## OpenAI Agents SDK

### Python

```python
from tracememory import TraceMemoryClient, TraceMemoryOpenAIAgentsMiddleware

client = TraceMemoryClient(base_url="https://api.tracememory.dev", api_key="tm_live_...")
run = client.start_run(agent_id="compliance-agent", task="Review compliance tickets")
middleware = TraceMemoryOpenAIAgentsMiddleware(client, run["task_id"], agent_id="compliance-agent")

middleware.on_agent_start("Review compliance tickets and preserve runtime evidence.")
middleware.on_plan({"steps": ["retrieve", "validate", "summarize"]})
fetch_tool = middleware.wrap_tool("fetch_compliance_tickets", fetch_compliance_tickets)
fetch_tool()
middleware.on_final_answer("Review complete.")
```

What is recorded:

- agent start event
- plan event
- tool trace for wrapped tools
- optional checkpoint after read tools
- final answer event

---

## Generic tool wrapper

Use the generic wrapper when your agent framework does not have a dedicated adapter.

```python
from tracememory import TraceMemoryClient, ToolWrapperConfig, trace_tool

client = TraceMemoryClient(base_url="https://api.tracememory.dev", api_key="tm_live_...")
run = client.start_run(agent_id="custom-agent", task="Fetch all tickets")

@trace_tool(
    client,
    run["task_id"],
    ToolWrapperConfig(
        tool_name="fetch_support_tickets",
        tool_type="read",
        checkpoint_after=True,
        observed_signals=lambda args, kwargs, result: {"next_page_token": result.get("next_page_token")},
    ),
)
def fetch_support_tickets(page_token=None):
    return {"items": [], "next_page_token": None}
```

---

## Production notes

For production usage:

1. Use stable `agent_id`, `project_id`, and environment metadata.
2. Add idempotency keys around write/action-taking tools.
3. Record validation conditions for tools that can return partial results.
4. Save checkpoints after safe boundaries, not after every tiny step.
5. Treat execution memory as governed: candidate → approved → applied.
6. Use the signed-in console to inspect runs, checkpoints, memory, and trace lineage.
