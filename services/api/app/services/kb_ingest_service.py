from __future__ import annotations

import io
from pathlib import Path
from typing import List, Optional, Union

from app.config import Settings
from app.db.postgres import DESCENDING, PostgresStore
from app.models.schemas import (
    KbChunkSummary,
    KbDocumentSummary,
    KbHit,
    KbIngestRequest,
    KbIngestResponse,
    new_id,
    utc_now,
)
from app.services.embedding_service import EmbeddingService
from app.services.search_ranking import rank_score


DEMO_KB_DOCS = [
    {
        "title": "Refund policy — SupportMemory KB",
        "source_type": "policy",
        "tags": ["refunds", "billing"],
        "text": (
            "Refunds may be approved within 30 days of purchase when the customer reports a payment failure "
            "or duplicate charge. Prefer issuing a refund over forcing a retry when the payment processor "
            "already marked the charge as settled. Always confirm the original ticket ID and processor "
            "reference before approving. Do not ask the customer to re-enter card details if a prior "
            "investigation already confirmed a processor-side decline."
        ),
    },
    {
        "title": "Ticket pagination SOP",
        "source_type": "sop",
        "tags": ["tickets", "pagination"],
        "text": (
            "When fetching support tickets from a paginated helpdesk API, continue fetching until "
            "next_page_token is null before producing a final answer. Partial page summaries are incomplete "
            "and must not be treated as a closed investigation. Preserve page_token in the checkpoint so a "
            "crashed run can resume without re-fetching completed pages."
        ),
    },
    {
        "title": "Escalation preferences",
        "source_type": "preference",
        "tags": ["escalation", "preferences"],
        "text": (
            "Enterprise customers prefer chat escalation over email when a billing dispute exceeds $500. "
            "Remember prior customer preference: do not re-ask channel preference if it was recorded on an "
            "earlier ticket in the same account. Compliance holds block refunds until a human reviewer clears "
            "the case — the agent must surface the hold instead of inventing a workaround."
        ),
    },
]


class KbIngestService:
    """Real document/KB ingestion: paste text → chunk → embed → Postgres → retrieve."""

    def __init__(self, store: PostgresStore, embeddings: EmbeddingService, settings: Settings):
        self.store = store
        self.embeddings = embeddings
        self.settings = settings

    @staticmethod
    def extract_pdf_text(source: Union[str, Path, bytes]) -> tuple[str, int]:
        """Extract plain text from a PDF path or raw bytes. Returns (text, page_count)."""
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("pypdf is required for PDF ingest. Install services/api/requirements.txt") from exc

        if isinstance(source, (bytes, bytearray)):
            reader = PdfReader(io.BytesIO(source))
        else:
            reader = PdfReader(str(source))
        pages = [(page.extract_text() or "") for page in reader.pages]
        text = " ".join(" ".join(pages).split())
        if len(text) < 20:
            raise ValueError("PDF produced too little extractable text (scanned/image-only PDFs need OCR)")
        return text, len(reader.pages)

    async def ingest_pdf(
        self,
        *,
        source: Union[str, Path, bytes],
        title: str,
        source_system: str = "pdf_upload",
        tags: Optional[List[str]] = None,
        agent_id: str = "ticket-investigation-agent",
    ) -> KbIngestResponse:
        text, page_count = self.extract_pdf_text(source)
        result = await self.ingest(
            KbIngestRequest(
                title=title,
                text=text[:200_000],
                source_type="pdf",
                source_system=source_system,
                tags=(tags or []) + ["pdf", f"pages:{page_count}"],
                agent_id=agent_id,
            )
        )
        return result

    async def ingest(self, payload: KbIngestRequest) -> KbIngestResponse:
        chunks = self._chunk_text(payload.text, payload.chunk_chars, payload.chunk_overlap)
        if not chunks:
            raise ValueError("No chunks produced from document text")

        document_id = new_id("doc")
        created_at = utc_now()
        chunk_summaries: List[KbChunkSummary] = []

        for index, chunk_text in enumerate(chunks):
            chunk_id = new_id("chk")
            embedding = await self.embeddings.embed(chunk_text)
            await self.store.insert_one(
                "kb_chunks",
                {
                    "_id": chunk_id,
                    "id": chunk_id,
                    "document_id": document_id,
                    "title": payload.title,
                    "text": chunk_text,
                    "source_type": payload.source_type,
                    "source_system": payload.source_system,
                    "status": "approved",
                    "embedding": embedding,
                    "agent_id": payload.agent_id,
                    "tags": payload.tags,
                    "index": index,
                    "created_at": created_at.isoformat(),
                },
            )
            chunk_summaries.append(KbChunkSummary(chunk_id=chunk_id, index=index, char_count=len(chunk_text)))

        await self.store.insert_one(
            "kb_documents",
            {
                "_id": document_id,
                "id": document_id,
                "title": payload.title,
                "source_type": payload.source_type,
                "source_system": payload.source_system,
                "tags": payload.tags,
                "agent_id": payload.agent_id,
                "chunk_count": len(chunk_summaries),
                "char_count": len(payload.text),
                "created_at": created_at.isoformat(),
            },
        )

        return KbIngestResponse(
            document_id=document_id,
            title=payload.title,
            chunk_count=len(chunk_summaries),
            embedding_provider=self.settings.embedding_provider,
            chunks=chunk_summaries,
            source_type=payload.source_type,
            source_system=payload.source_system,
        )

    async def list_documents(self, limit: int = 50) -> List[KbDocumentSummary]:
        docs = await self.store.find_many("kb_documents", limit=limit, sort=[("created_at", DESCENDING)])
        results: List[KbDocumentSummary] = []
        for doc in docs:
            results.append(
                KbDocumentSummary(
                    document_id=doc.get("_id") or doc.get("id"),
                    title=doc.get("title", "Untitled"),
                    source_type=doc.get("source_type", "policy"),
                    source_system=doc.get("source_system", "kb"),
                    chunk_count=int(doc.get("chunk_count") or 0),
                    tags=list(doc.get("tags") or []),
                    created_at=doc.get("created_at") or utc_now(),
                    agent_id=doc.get("agent_id", "ticket-investigation-agent"),
                )
            )
        return results

    async def search(self, query: str, top_k: int = 5, agent_id: Optional[str] = None) -> List[KbHit]:
        query_embedding = await self.embeddings.embed(query)
        docs = await self.store.find_many("kb_chunks", {"status": "approved"}, limit=300, sort=[("created_at", DESCENDING)])
        ranked: list[tuple[float, dict]] = []
        for doc in docs:
            if agent_id and doc.get("agent_id") and doc.get("agent_id") != agent_id:
                # Soft filter: still allow generic KB shared across agents
                if doc.get("agent_id") not in {agent_id, "support_agent", "ticket-investigation-agent"}:
                    continue
            score = rank_score(
                query=query,
                document_text=f"{doc.get('title', '')} {doc.get('text', '')}",
                query_embedding=query_embedding,
                doc_embedding=doc.get("embedding", []) or [],
                title=doc.get("title", ""),
                tags=doc.get("tags") or [],
                hash_embeddings=self.embeddings.uses_hash,
            )
            if score > 0.08:
                ranked.append((score, doc))
        ranked.sort(key=lambda item: item[0], reverse=True)
        hits: List[KbHit] = []
        for score, doc in ranked[:top_k]:
            hits.append(
                KbHit(
                    chunk_id=doc.get("_id") or doc.get("id"),
                    document_id=doc.get("document_id", ""),
                    title=doc.get("title", "Untitled"),
                    score=round(float(score), 4),
                    text=doc.get("text", ""),
                    source_type=doc.get("source_type", "policy"),
                    source_system=doc.get("source_system", "kb"),
                )
            )
        return hits

    async def seed_demo(self, agent_id: str = "ticket-investigation-agent") -> List[KbIngestResponse]:
        existing = await self.store.find_many("kb_documents", limit=5)
        if existing:
            return []
        results: List[KbIngestResponse] = []
        for doc in DEMO_KB_DOCS:
            results.append(
                await self.ingest(
                    KbIngestRequest(
                        title=doc["title"],
                        text=doc["text"],
                        source_type=doc["source_type"],
                        source_system="kb_demo",
                        tags=doc["tags"],
                        agent_id=agent_id,
                    )
                )
            )
        return results

    def _chunk_text(self, text: str, chunk_chars: int, overlap: int) -> List[str]:
        cleaned = " ".join(text.split())
        if not cleaned:
            return []
        if len(cleaned) <= chunk_chars:
            return [cleaned]
        step = max(1, chunk_chars - overlap)
        chunks: List[str] = []
        start = 0
        while start < len(cleaned):
            end = min(len(cleaned), start + chunk_chars)
            piece = cleaned[start:end].strip()
            if piece:
                chunks.append(piece)
            if end >= len(cleaned):
                break
            start += step
        return chunks
