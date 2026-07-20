# Hackathon Scope

TraceMemory for the **Global AI Hackathon Series with Qwen Cloud — Track 1:
MemoryAgent** focuses on one proof:

> An agent with persistent memory can accumulate experience across
> multi-turn, cross-session interactions — storing and retrieving memory
> efficiently, forgetting stale information on time, and recalling the
> critical facts within a limited context window — and can prove, via a
> signed receipt, that a recovered run used real prior memory rather than
> starting cold.

Concretely, TraceMemory's Context Health, curation, retrieval, and reflection
services *are* the MemoryAgent primitives the track asks for:

| Track 1 ask | TraceMemory component |
|---|---|
| Efficient memory storage & retrieval | `retrieval_service.py`, `curation_service.py` |
| Timely forgetting of outdated information | Context Health staleness checks (`context_health/service.py`) |
| Recall within limited context windows | `reflection_service.py` + checkpoint/recovery path |
| Cross-session accuracy improvement | Execution Receipts feeding forward into future task contracts |

## In scope

- One main UI at `http://localhost:3000`
- One-click `Run Agent Recovery Demo`
- FastAPI runtime on `http://localhost:8000`
- PostgreSQL durable records
- Recovery worker service
- Context Health checks (forgetting / staleness detection)
- MCP-style mock tools
- Qwen Cloud as the primary model gateway (`DEFAULT_MODEL_GATEWAY=qwen`)
- Alibaba Cloud OSS execution-receipt archival (durable, tamper-evident proof)
- Alibaba Cloud ECS deployment path
- Execution receipt/proof panel
- Open-source-ready package

## Out of scope for this hackathon branch

- Billing
- Heavy RBAC
- Broad enterprise admin controls
- MongoDB
- Complex graph memory
- Startup competition pitch material
- Domain-specific chatbots

## Judge memory line

TraceMemory is a governed memory agent: it stores, curates, forgets, and
recalls execution memory across sessions — and proves it with a signed
receipt.
