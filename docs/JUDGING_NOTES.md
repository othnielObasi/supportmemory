# Judging Notes

## Impact

Agents are moving from chat into long-running real work. TraceMemory addresses a core blocker: agents lose state, repeat actions, use stale context, and cannot recover cleanly after interruption.

## Demo

The main demo is one click in the UI:

```text
http://localhost:3000 → Run Agent Recovery Demo
```

The UI calls:

```text
POST /api/demo/failure-recovery
```

and shows:

```text
Task saved → Context checked → Tool called → Checkpoint saved → Failure detected → Agent restored → Task updated → Receipt generated
```

## Creativity

Most tools observe agent failure. TraceMemory makes the agent run recoverable and receipt-backed.

## Pitch

TraceMemory is crash recovery for AI agents.

## Top-1 judge message

TraceMemory should be judged on one live proof:

> The agent crashes halfway. TraceMemory restores the checkpoint, keeps the task contract and tool evidence attached, continues the task, and produces an execution receipt.

Do not pitch this as a dashboard. Pitch it as **crash recovery for AI agents**.

## Track 1: MemoryAgent fit

- **Efficient storage/retrieval** — curation and retrieval services persist
  only approved, deduplicated execution memory, retrieved by relevance not
  full replay.
- **Timely forgetting** — Context Health actively flags and expires stale
  context rather than letting it silently accumulate.
- **Recall within limited context windows** — reflection service selects the
  minimal memory slice needed to resume a task, not the full history.
- **Qwen Cloud** — primary model gateway for reasoning (reflection, drift
  checks), OpenAI-compatible via DashScope.
- **Alibaba Cloud deployment** — ECS-hosted backend; signed receipts
  additionally archived to Alibaba OSS as durable, third-party-verifiable
  proof.

## 3-minute video spine

0–20s: Agents lose memory across sessions and repeat work.  
20–45s: TraceMemory's memory pipeline — contract, Context Health staleness
check, curated retrieval — running on Qwen Cloud, deployed on Alibaba Cloud.  
45s–1:45: Live run — tool trace, checkpoint, simulated interruption.  
1:45–2:30: Recovery restores the checkpoint; task continues with prior
memory intact, not from scratch.  
2:30–3:00: Signed execution receipt generated and archived to Alibaba OSS —
proof the memory used was real.
