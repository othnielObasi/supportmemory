# API Reference

The hackathon build exposes the recovery path needed for judging.

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/demo/failure-recovery` | Run the complete one-click recovery demo. |
| `POST` | `/api/demo/recovery-run` | Friendly alias for the same recovery demo. |
| `GET` | `/api/demo/recovery-run/{run_id}` | Lightweight read/probe endpoint for demo runs. |
| `POST` | `/api/tasks/run` | Start a durable task run. |
| `POST` | `/api/tasks/recover` | Recover from a checkpoint. |
| `POST` | `/api/tasks/{task_id}/modify` | Create a new task version after scope changes. |
| `POST` | `/api/runs/{task_id}/events` | Record a run event. |
| `POST` | `/api/runs/{task_id}/tool-traces` | Record a tool trace. |
| `POST` | `/api/runs/{task_id}/checkpoints` | Save a checkpoint. |
| `POST` | `/api/context-health/build` | Build a clean context bundle and receipt. |
| `GET` | `/api/context-health/receipts` | List context receipts. |
| `POST` | `/api/mcp/gateway/test` | Test the MCP-style gateway path. |

OpenAPI docs are available locally at:

```text
http://localhost:8000/docs
```
