"""Offline test: ingest root PDF into KB memory and search it."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))

from app.config import Settings
from app.services.embedding_service import EmbeddingService
from app.services.kb_ingest_service import KbIngestService


class MemoryStore:
    def __init__(self):
        self.data = {}

    async def insert_one(self, collection, doc):
        self.data.setdefault(collection, []).append(doc)
        return doc

    async def find_many(self, collection, query=None, limit=50, sort=None):
        rows = list(self.data.get(collection, []))
        query = query or {}
        return [row for row in rows if all(str(row.get(k)) == str(v) for k, v in query.items())][:limit]


async def main() -> None:
    pdf = ROOT / "2509.11332v1.pdf"
    if not pdf.exists():
        raise SystemExit(f"PDF not found: {pdf}")

    settings = Settings(embedding_provider="hash", embedding_dimensions=384)
    store = MemoryStore()
    kb = KbIngestService(store, EmbeddingService(settings), settings)

    print("PDF:", pdf, "size=", pdf.stat().st_size)
    text, pages = KbIngestService.extract_pdf_text(pdf)
    print(f"Extracted pages={pages} chars={len(text)}")
    print("Title sniff:", text[:160])

    ingested = await kb.ingest_pdf(
        source=pdf,
        title="Five-Layer Framework for AI Governance (PDF)",
        tags=["governance", "regulation", "hackathon-pdf"],
        agent_id="ticket-investigation-agent",
    )
    print(
        "INGEST:",
        {
            "document_id": ingested.document_id,
            "chunk_count": ingested.chunk_count,
            "embedding_provider": ingested.embedding_provider,
            "source_type": ingested.source_type,
        },
    )

    queries = [
        "What is the five-layer framework for AI governance?",
        "How do regulation standards and certification integrate?",
        "refund payment failure ticket",
    ]
    for query in queries:
        hits = await kb.search(query, top_k=3)
        print("\nQUERY:", query)
        if not hits:
            print("  (no hits)")
            continue
        for hit in hits:
            print(f"  score={hit.score} title={hit.title}")
            print(f"  snippet={hit.text[:220]}...")

    assert ingested.chunk_count >= 1
    gov_hits = await kb.search(
        "five-layer AI governance regulation standards certification",
        top_k=3,
    )
    assert gov_hits and gov_hits[0].score > 0.05
    print("\nPASS: PDF ingest + retrieval succeeded")


if __name__ == "__main__":
    asyncio.run(main())
