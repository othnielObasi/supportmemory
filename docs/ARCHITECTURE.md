# Architecture

TraceMemory's hackathon architecture is intentionally small:

```text
Console UI :3000
  ↓
FastAPI runtime :8000  ──→  Qwen Cloud (DashScope, Alibaba Cloud)
  ↓                          reflection / curation / drift reasoning
PostgreSQL durable store
  ↓
Recovery worker
  ↓
Alibaba Cloud OSS  ──  signed Execution Receipt archive (oss2 SDK)
```

Deployed on Alibaba Cloud ECS (see `infra/alibaba/`). The demo simulates MCP-style ticket, policy, and compliance tools so the project remains open-source and keyless for judges; Qwen Cloud and Alibaba OSS are live when API keys are supplied and fall back cleanly to deterministic local mode otherwise.

## Core records

- Runs
- Task contracts
- Run events
- Tool traces
- Checkpoints
- Context Health records
- Recovery records
- Execution receipt summaries

## Recovery flow

```text
Task contract → Context Health → Tool trace → Checkpoint → Failure → Restore → Task v2 → Receipt
```
