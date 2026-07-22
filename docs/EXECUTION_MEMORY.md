# Execution Memory: Cross-Run Learning Loop

TraceMemory does not just recover a single run — it carries lessons forward across runs.
This is implemented today (not aspirational) by four services that form a closed loop.
Every claim below maps to real code under `services/api/app/services/`.

## The loop

```
   run fails / completes
          │
          ▼
   ReflectionService.reflect(trace)      reflection_service.py
          │   derives a candidate lesson + confidence from the trace
          ▼
   CurationService.curate(reflection)    curation_service.py
          │   validates safety/PII, dedupes via embedding similarity,
          │   HMAC-signs, promotes to the durable playbook
          ▼
   playbook_rules  (Postgres)            db/postgres.py
          │   approved, signed, reusable rules
          ▼
   RetrievalService.retrieve(task)       retrieval_service.py
          │   embeds the next task, returns top-K rules as a context prefix
          ▼
   applied on the NEXT run
```

The normal `POST /api/tasks/run` path now closes this loop automatically. It reflects on
the completed trace and curates the candidate when its confidence meets
`MEMORY_MIN_AUTO_CONFIDENCE`. Set `MEMORY_AUTO_LEARN=false` when an installation requires
fully manual approval through the reflection and curation endpoints.

## Relationship memory

SupportMemory also maintains a tenant-scoped property graph in PostgreSQL JSONB. Graph
nodes cover customers, accounts, tickets, incidents, policies, KB chunks, execution traces,
tool actions, and lessons. Edges retain evidence IDs, confidence, validity windows, and
tenant identity. Retrieval resolves seed entities from the new task, performs a bounded
one/two-hop traversal, and injects only compact evidence paths into the existing context
prefix. Vector/lexical search remains responsible for semantic discovery; the graph adds
explicit relationships and provenance.

Graph endpoints:

- `POST /api/graph/nodes`
- `POST /api/graph/edges`
- `POST /api/graph/traverse`

## Memory governance

- All new KB, lesson, profile, conversation, retrieval, checkpoint, and graph records carry
  organisation/workspace scope.
- Rule retrieval enforces tenant, agent/scope, status, and expiry constraints.
- Context Health redacts common email, phone, government-ID, payment-card, and credential
  patterns before recalled context reaches a model.
- `DELETE /api/memory/users/{user_id}` removes user-owned memory.
- `POST /api/memory/expired/prune?dry_run=true` previews expired records; use
  `dry_run=false` to delete them.
- Retrieval audit records contain rules, KB chunks, graph paths, trace ID, tenant identity,
  context prefix, and embedding provider. Execution receipts hash the graph paths used.

## What each stage actually does

**Reflection** (`reflection_service.py`)
Inspects a completed `ExecutionTrace` and derives a candidate rule with a confidence
score. Failure types map to concrete lessons — e.g. a missed-pagination failure yields
"for paginated APIs, continue fetching until next_page_token is null before producing a
final answer" (confidence 0.92). Successful runs yield a reusable best-practice pattern.
The insight is persisted as a `ReflectionInsight` with status `pending_curation`.

**Curation** (`curation_service.py`)
Gatekeeps what becomes long-term memory. It validates the candidate for safety and PII,
embeds it, and checks for near-duplicates by cosine similarity against existing approved
rules. Duplicates are merged (incrementing `failure_count`) rather than re-added. New,
safe rules are HMAC-signed and written to `playbook_rules` with status `approved`.

**Retrieval** (`retrieval_service.py` + `embedding_service.py`)
On a new task, embeds the task description and ranks approved rules using a blend of
vector similarity, keyword overlap, and a category boost. The top-K rules are assembled
into a context prefix and recorded as a `RetrievalEvent` so the application of memory is
itself auditable.

## How it is exposed

- `POST /traces/{trace_id}/reflect` — derive a lesson from a trace
- `POST /reflections/{reflection_id}/curate` — validate and promote into the playbook
- Retrieval runs automatically at task start (see `api.py`), and the
  `memory_created_or_retrieved` run event marks when execution memory was applied.

## Why this is the differentiator

Durable-execution tooling (Temporal, Restate, DBOS, LangGraph checkpointing) can resume a
crashed run. None of them turn the failure into a signed, reusable rule that improves the
*next* run. TraceMemory's loop is the self-improvement story — and unlike a generic
"memory" claim, every step here is backed by code and exercised by the test suite.

## Honest scope

- Lesson derivation is LLM-driven: when a model gateway (OpenAI-compatible, OpenRouter, or
  Google) is configured, `ReflectionService` sends the actual execution trace to the model
  and parses a generated lesson + confidence. Lessons are generated from the trace, not
  selected from a fixed list. Each insight is stamped with `derivation: "llm"`.
- A deterministic lesson table is retained ONLY as an offline fallback for when no gateway
  is configured or the model returns unparseable output. Those insights are stamped
  `derivation: "deterministic_fallback"`, so it is always auditable which path produced a
  given rule. This keeps the demo runnable offline without misrepresenting it as learning.
- The playbook is per-deployment. Cross-tenant sharing of rules is out of scope for the
  hackathon build.

## Live demo mode (UI)

The Agent demo in the UI runs scripted by default (offline-safe for recording). A "Scripted/Live"
toggle in the agent header probes the backend `/health`; when reachable, advancing each stage calls
the real API — `/api/tasks/run`, `/api/traces/{id}/reflect`, `/api/reflections/{id}/curate`,
`/api/lessons/retrieve` — and overlays the real trace id, the model-derived lesson, its
`derivation` ("llm" or "deterministic_fallback"), the signed playbook rule id, and the retrieved
rule with its score. If the backend is unreachable or a call fails, the stage falls back to scripted
content and says so. Point the UI at a backend with `?api=<base-url>` (defaults to http://localhost:8000).

## Swappable demo scenarios

The Agent demo ships two scenarios, selected with `?scenario=`:
- `ticket` (default) — enterprise ticket-investigation agent.
- `coding` — an autonomous coding agent that crashes mid-refactor, recovers without
  re-running an already-applied migration (idempotency), and gets the migration order
  right on a second module because it retrieved the lesson it learned the first time.

Both run identically in scripted and live modes; only the scenario content differs. The
coding scenario exists to show the recover/prove/learn loop is horizontal — coding agents
have the same crash/duplicate/forgetting failure modes — while the submission stays on the
Vultr (infrastructure) track.
