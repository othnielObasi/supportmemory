# SupportMemory — Project Story

Hackathon submission narrative for **Track 1: MemoryAgent** (Qwen Cloud).

**Repository:** https://github.com/othnielObasi/supportmemory

---

## Inspiration

Customer support is one of the hardest places to “just add an LLM.” Agents re-ask questions customers already answered, re-investigate issues that were already diagnosed, and lose everything if a long tool-using run crashes mid-flight. That is not only a model problem — it is a **memory** problem.

In short:

$$
\text{good support} \approx \text{recall} + \text{safe action} + \text{recoverability} + \text{proof}
$$

We built **SupportMemory** for **Track 1: MemoryAgent** on **Qwen Cloud**: a support agent that remembers what matters, forgets what is stale, resumes after failure, and proves what it did. The goal is \(\text{memory that recovers}\) — not another chat wrapper.

## What it does

SupportMemory investigates tickets with durable execution memory:

- **Persistent user memory** — name, contact channel, plan tier, extras, plus conversation history across sessions
- **KB memory** — real text/PDF ingest, chunking, embeddings (Qwen `text-embedding-v3` when keyed), hybrid search
- **Context Health** — filter stale/noisy context before planning
- **Runtime Governor** — hybrid PII: redact on reads; require approval on external `send_*` / `refund_*` actions
- **Checkpoints + recovery** — PostgreSQL-backed checkpoints; simulate failure → restore trusted state without replaying completed tools
- **Cross-session improvement** — reflect → curate → retrieve lessons on the next related run
- **Multimodal / voice on Qwen** — vision (`qwen-vl-max`), TTS, ASR with language preference
- **Signed execution receipts** — SHA-256 + Ed25519 proof; optional Alibaba OSS archive

Judges can run the one-click path:

```bash
cp .env.example .env
docker compose up --build
# open http://localhost:3000 → Run recovery demo
# or POST /api/demo/failure-recovery
```

Keyless/mock mode works without external keys; set `QWEN_API_KEY` for live Qwen Cloud reasoning.

## How we built it

We shipped a Docker Compose stack:

1. **SupportMemory console UI** wired to the live API (investigations, inspector, KB panel)
2. **FastAPI runtime** for tasks, tools, KB, preferences, conversations, voice, multimodal
3. **PostgreSQL** as the durable store for checkpoints, traces, KB chunks, user prefs, and conversation history
4. **Recovery worker** to resume incomplete runs
5. **Qwen / DashScope** as the model gateway (chat, embeddings, VL, TTS, ASR)
6. **Helpdesk mocks** (Zendesk/Freshdesk-shaped) so demos run without CRM credentials

The demo story is intentionally concrete:

```text
Task contract → Context Health → Tool traces → Checkpoint
→ Failure → Restore → Reflect/Curate → Retrieve → Receipt
```

## Challenges we ran into

1. **Search quality** — naive hash/Jaccard ranking underperformed; we improved coverage/phrase ranking and Qwen embeddings.
2. **UI vs product story** — we replaced the old infra-style demo with a SupportMemory dashboard and wired KB/tasks/recovery live.
3. **Per-user memory gap** — language prefs existed, but general profile + conversation history did not; we added both and inject them into `POST /api/tasks/run` via `user_id`.
4. **Hackathon packaging** — public repo, full Apache-2.0 `LICENSE`, runnable Compose instructions, and Alibaba/Qwen deployment notes for judges.

## Accomplishments that we're proud of

- A **one-click failure → recovery demo** that proves checkpoints, non-replayed tools, and signed receipts
- A **real KB path** (text + PDF ingest → embed → search), not just mocked “memory” text
- A **hybrid Runtime Governor** that treats support side-effects (send/refund) differently from internal reads
- **Per-user preferences + conversation history** wired into task context for true cross-session recall
- A **judge-friendly open-source package**: public GitHub repo, Apache-2.0 license, Docker Compose, keyless mode

## What we learned

- “Memory” for agents is not one vector DB call — it is **profile + conversation + KB + lessons + checkpoints**.
- Forgetting is as important as remembering: Context Health and bounded conversation windows keep context usable.
- Support actions need a **governor**, not just a chat model — especially around PII and refunds/emails.
- Judges need a **keyless path** and a **one-click recovery demo**; live Qwen can be an optional upgrade.
- Proof matters: a signed receipt turns “trust me” into auditable evidence.

## What's next for SupportMemory

- Live Zendesk/Freshdesk connectors behind the same mock contracts
- Richer UI for preferences + conversation threads in the dashboard
- Production auth, tenancy, and receipt verification for enterprise support teams
- Deeper Qwen Cloud multimodal workflows (screenshot → root cause → spoken summary) in the default demo path

---

## Built with

Python, FastAPI, PostgreSQL, Docker, Docker Compose, React, TypeScript, JavaScript, Qwen, DashScope, Alibaba Cloud, OSS, Ed25519, MCP, REST API, LLM Agents, RAG, TTS, ASR, Computer Vision, Hackathon, Open Source, Apache-2.0

## Try it out

| Link | URL |
|---|---|
| GitHub | https://github.com/othnielObasi/supportmemory |
| Local UI | http://localhost:3000 |
| API docs | http://localhost:8000/docs |
