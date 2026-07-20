"""End-to-end SupportMemory check (works without Docker).

Exercises: hybrid governor, KB/PDF ingest+retrieve, language preference,
Qwen chat/TTS when keyed, agent runner + reflect/curate/retrieve loop,
helpdesk mock, multimodal vision fallback/live.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from app.config import Settings
from app.models.schemas import (
    HelpdeskMockTicketRequest,
    KbIngestRequest,
    MultimodalAnalyzeRequest,
    MultimodalAttachment,
    ToolType,
)
from app.services.agent_runner import AgentRunner
from app.services.curation_service import CurationService
from app.services.embedding_service import EmbeddingService
from app.services.governance import GovernanceService
from app.services.helpdesk_connector import fetch_helpdesk_mock
from app.services.kb_ingest_service import KbIngestService
from app.services.language_preference_service import LanguagePreferenceService
from app.services.model_gateway import ModelGatewayRegistry
from app.services.multimodal_service import MultimodalService
from app.services.reflection_service import ReflectionService
from app.services.retrieval_service import RetrievalService
from app.services.voice_service import VoiceService
from app.db.postgres import DESCENDING


class MemoryStore:
    def __init__(self):
        self.data = {}

    async def insert_one(self, collection, doc):
        self.data.setdefault(collection, []).append(doc)
        return doc.get("_id") or doc.get("id")

    async def find_many(self, collection, query=None, limit=50, sort=None):
        rows = list(self.data.get(collection, []))
        query = query or {}
        out = [r for r in rows if all(str(r.get(k)) == str(v) for k, v in query.items())]
        return out[:limit]

    async def find_one_by(self, collection, query=None, sort=None):
        rows = await self.find_many(collection, query=query, limit=1, sort=sort)
        return rows[0] if rows else None

    async def upsert_one(self, collection, query, update):
        existing = await self.find_one_by(collection, query)
        if existing:
            existing.update(update)
            return
        self.data.setdefault(collection, []).append(update)

    async def update_one(self, collection, query, update):
        existing = await self.find_one_by(collection, query)
        if not existing:
            return
        set_values = update.get("$set", {}) if any(str(k).startswith("$") for k in update) else update
        inc_values = update.get("$inc", {}) if isinstance(update.get("$inc"), dict) else {}
        existing.update(set_values)
        for key, amount in inc_values.items():
            existing[key] = (existing.get(key) or 0) + amount


def ok(label: str, cond: bool, detail: str = "") -> bool:
    mark = "PASS" if cond else "FAIL"
    line = f"[{mark}] {label}" + (f" - {detail}" if detail else "")
    print(line.encode("ascii", errors="replace").decode("ascii"))
    return cond


async def main() -> int:
    settings = Settings()
    store = MemoryStore()
    embeddings = EmbeddingService(settings)
    gov = GovernanceService(settings)
    kb = KbIngestService(store, embeddings, settings)
    prefs = LanguagePreferenceService(store)
    retrieval = RetrievalService(store, embeddings, settings, kb=kb)
    gateway = ModelGatewayRegistry(settings).get()
    reflection = ReflectionService(store, gateway)
    curation = CurationService(store, embeddings, settings)
    multimodal = MultimodalService(settings, gateway, kb=kb)
    voice = VoiceService(settings, language_prefs=prefs)
    agent = AgentRunner(gov)

    results = []

    # 1) Hybrid governor
    read_dec = gov.evaluate_tool_call(
        "fetch_tickets",
        {"query": "help customer@example.com"},
        {"tool_type": ToolType.read.value},
    )
    results.append(
        ok(
            "Governor redact on read",
            read_dec.decision.value == "allowed" and "pii_redacted" in read_dec.policy_flags,
            f"decision={read_dec.decision.value} flags={read_dec.policy_flags}",
        )
    )
    send_dec = gov.evaluate_tool_call(
        "send_email",
        {"to": "customer@example.com", "body": "refund"},
        {"tool_type": ToolType.external_action.value, "idempotency_key": "e2e-1"},
    )
    results.append(
        ok(
            "Governor require_approval on external+PII",
            send_dec.decision.value == "needs_approval",
            f"decision={send_dec.decision.value} mode={send_dec.pii_mode_applied}",
        )
    )

    # 2) Helpdesk mock
    ticket = fetch_helpdesk_mock(HelpdeskMockTicketRequest(source_system="zendesk_mock"))
    results.append(
        ok(
            "Helpdesk Zendesk-shaped mock",
            ticket.source_system == "zendesk_mock" and bool(ticket.ticket.get("id")),
            f"ticket={ticket.ticket.get('id')} subject={ticket.ticket.get('subject')}",
        )
    )

    # 3) KB ingest + retrieve (sample policy)
    ingested = await kb.ingest(
        KbIngestRequest(
            title="SupportMemory refund policy",
            text=(
                "Refunds may be approved within 30 days of purchase when the customer reports a payment failure "
                "or duplicate charge. Prefer issuing a refund over forcing a retry when the processor settled the charge. "
                "Always confirm the original ticket ID before approving."
            ),
            tags=["refunds", "supportmemory"],
            agent_id="ticket-investigation-agent",
        )
    )
    hits = await kb.search("When can we refund a payment failure?", top_k=3)
    results.append(
        ok(
            "KB ingest + search",
            ingested.chunk_count >= 1 and bool(hits) and hits[0].score > 0.05,
            f"chunks={ingested.chunk_count} top_score={hits[0].score if hits else None}",
        )
    )

    # 4) PDF ingest if present
    pdf = ROOT / "2509.11332v1.pdf"
    if pdf.exists():
        pdf_ingested = await kb.ingest_pdf(
            source=pdf,
            title="AI Governance PDF",
            tags=["pdf", "e2e"],
            agent_id="ticket-investigation-agent",
        )
        pdf_hits = await kb.search("five-layer framework for AI governance", top_k=2)
        results.append(
            ok(
                "PDF ingest + search",
                pdf_ingested.chunk_count >= 1 and bool(pdf_hits),
                f"chunks={pdf_ingested.chunk_count} top={pdf_hits[0].score if pdf_hits else None}",
            )
        )
    else:
        results.append(ok("PDF ingest + search", False, "PDF missing in root"))

    # 5) Language preference self-adjust
    resolved = await prefs.resolve_for_tts(
        user_id="cust_e2e",
        explicit_language=None,
        text="请帮我处理退款问题，谢谢",
        auto_learn=True,
    )
    pref = await prefs.get("cust_e2e")
    results.append(
        ok(
            "Language self-adjust (Chinese)",
            resolved["language_type"] == "Chinese" and pref["preferred_language"] == "Chinese",
            f"resolved={resolved} pref={pref['preferred_language']}",
        )
    )
    await prefs.set("cust_fr", "French", source="explicit")
    fr = await prefs.resolve_for_tts(
        user_id="cust_fr",
        explicit_language=None,
        text="Bonjour merci",
        auto_learn=True,
    )
    results.append(
        ok(
            "Language preference drives TTS lang",
            fr["language_type"] == "French" and fr["source"] == "user_preference",
            f"{fr}",
        )
    )

    # 6) Multimodal analyze
    mm = await multimodal.analyze(
        MultimodalAnalyzeRequest(
            prompt="Investigate this payment failure screenshot",
            attachment=MultimodalAttachment(type="image", caption="payment decline screenshot"),
            ingest_to_kb=True,
            title="Payment screenshot",
        )
    )
    results.append(
        ok(
            "Multimodal vision analyze",
            bool(mm.summary) and bool(mm.context_prefix),
            f"provider={mm.provider} fallback={mm.used_fallback} kb={mm.kb_document_id}",
        )
    )

    # 7) Agent run + retrieve lessons/KB into context
    rules, context_prefix, kb_hits = await retrieval.retrieve(
        "Analyse support tickets and apply refund policy for payment failures",
        "ticket-investigation-agent",
        top_k=3,
        include_kb=True,
        kb_top_k=3,
    )
    results.append(
        ok(
            "Retrieval merges KB into context",
            "Relevant knowledge" in context_prefix or bool(kb_hits),
            f"rules={len(rules)} kb_hits={len(kb_hits)}",
        )
    )

    # Force pagination lesson path: no special lesson yet — run agent
    trace = await agent.run(
        task_description="Analyse all support tickets and summarise recurring account issues.",
        agent_id="ticket-investigation-agent",
        dataset_type="support_tickets",
        context_prefix=context_prefix,
    )
    results.append(
        ok(
            "Ticket agent run",
            trace.status.value in {"success", "failed", "partial", "blocked"},
            f"status={trace.status.value} failure={trace.failure_type.value} tools={len(trace.tool_calls)}",
        )
    )

    # 8) Reflect → curate → retrieve (memory loop)
    insight = await reflection.reflect(trace)
    rule, reason, signature = await curation.curate(insight)
    rules2, prefix2, _ = await retrieval.retrieve(
        "Analyse paginated support tickets completely before answering",
        "ticket-investigation-agent",
        top_k=3,
        include_kb=True,
    )
    results.append(
        ok(
            "Reflect -> curate -> retrieve loop",
            insight is not None and (rule is not None or "PII" in reason or "unsafe" in reason.lower() or "short" in reason.lower() or "Merged" in reason),
            f"insight={insight.id} rule={getattr(rule, 'id', None)} reason={reason[:80]} retrieved={len(rules2)}",
        )
    )

    # 9) Qwen chat live
    chat = await gateway.chat(
        system="Reply in one short sentence.",
        user="Confirm SupportMemory E2E path is reachable on Qwen.",
        max_tokens=60,
        temperature=0,
    )
    results.append(
        ok(
            "Qwen chat live",
            bool(settings.qwen_api_key) and bool(chat.content) and getattr(gateway, "provider", "") == "qwen",
            f"provider={getattr(gateway, 'provider', type(gateway).__name__)} model={chat.model} content={(chat.content or '')[:100]}",
        )
    )

    # 10) Qwen TTS with learned language preference
    if settings.qwen_api_key:
        audio, msg, meta = await voice.synthesize(
            "SupportMemory can recover tickets and remember lessons.",
            user_id="cust_e2e_en",
            language_type="English",
            auto_learn=True,
        )
        results.append(
            ok(
                "Qwen TTS + language preference",
                bool(audio) and meta.get("provider") == "qwen",
                f"lang={meta.get('resolved_language')} source={meta.get('language_source')} bytes={len(audio or '')}",
            )
        )
    else:
        results.append(ok("Qwen TTS + language preference", False, "QWEN_API_KEY missing"))

    # Policy summary
    policy = gov.policy_summary()
    results.append(
        ok(
            "Governor hybrid default",
            policy.get("pii_mode") == "hybrid",
            f"pii_mode={policy.get('pii_mode')} external={policy.get('external_pii_mode')}",
        )
    )

    print("\n==== SupportMemory E2E summary ====")
    passed = sum(1 for r in results if r)
    total = len(results)
    print(f"{passed}/{total} checks passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
