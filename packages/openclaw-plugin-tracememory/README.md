# TraceMemory for OpenClaw

TraceMemory for OpenClaw is an execution-memory plugin that sends OpenClaw agent lifecycle events to TraceMemory.

It adds:

- durable task-event recording
- context health receipts
- tool-call trace capture
- checkpoint/recovery event capture
- task modification history
- audit-ready execution trail

OpenClaw remains the agent runtime. TraceMemory becomes the reliability, recovery and audit layer.

## Minimal usage

```ts
import { createTraceMemoryOpenClawPlugin } from "@tracememory/openclaw-plugin";

export default createTraceMemoryOpenClawPlugin({
  apiUrl: process.env.TRACEMEMORY_API_URL ?? "http://localhost:8000/api",
  apiKey: process.env.TRACEMEMORY_API_KEY,
  workspaceId: process.env.TRACEMEMORY_WORKSPACE_ID ?? "wrk_default",
  projectId: process.env.TRACEMEMORY_PROJECT_ID ?? "prj_default",
  agentId: "openclaw_agent",
});
```


## TraceMemory API prefix

Configure `apiUrl` as the TraceMemory server base URL and leave `apiPrefix` as `/api` unless your deployment changes it. The plugin sends lifecycle events, context-health build requests, tool traces, and checkpoint-related events to TraceMemory.

```ts
createTraceMemoryOpenClawPlugin({
  apiUrl: "http://localhost:8000",
  apiPrefix: "/api",
  apiKey: process.env.TRACEMEMORY_API_KEY,
  agentId: "openclaw-agent"
});
```

OpenClaw remains the agent runtime. TraceMemory is the execution-memory, checkpoint, context-health, and receipt plugin.
