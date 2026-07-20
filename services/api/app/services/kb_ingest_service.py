from __future__ import annotations

import io
from datetime import datetime, timezone
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
        organisation_id: str = "org_default",
        workspace_id: str = "wrk_default",
        project_id: str = "prj_default",
        environment_id: str = "dev",
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
                organisation_id=organisation_id,
                workspace_id=workspace_id,
                project_id=project_id,
                environment_id=environment_id,
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
                    "organisation_id": payload.organisation_id,
                    "workspace_id": payload.workspace_id,
                    "project_id": payload.project_id,
                    "environment_id": payload.environment_id,
                    "expires_at": payload.expires_at.isoformat() if payload.expires_at else None,
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
                "organisation_id": payload.organisation_id,
                "workspace_id": payload.workspace_id,
                "project_id": payload.project_id,
                "environment_id": payload.environment_id,
                "expires_at": payload.expires_at.isoformat() if payload.expires_at else None,
            },
        )

        return KbIngestResponse(
            document_id=document_id,
            title=payload.title,
            chunk_count=len(chunk_summaries),
            embedding_provider=self.embeddings.provider,
            chunks=chunk_summaries,
            source_type=payload.source_type,
            source_system=payload.source_system,
            organisation_id=payload.organisation_id,
            workspace_id=payload.workspace_id,
        )

    async def list_documents(self, limit: int = 50, organisation_id: str = "org_default", workspace_id: str = "wrk_default") -> List[KbDocumentSummary]:
        docs = await self.store.find_many("kb_documents", limit=limit, sort=[("created_at", DESCENDING)])
        results: List[KbDocumentSummary] = []
        for doc in docs:
            if doc.get("organisation_id", "org_default") != organisation_id or doc.get("workspace_id", "wrk_default") != workspace_id:
                continue
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

    async def search(self, query: str, top_k: int = 5, agent_id: Optional[str] = None, organisation_id: str = "org_default", workspace_id: str = "wrk_default") -> List[KbHit]:
        query_embedding = await self.embeddings.embed(query)
        docs = await self.store.find_many("kb_chunks", {"status": "approved"}, limit=300, sort=[("created_at", DESCENDING)])
        ranked: list[tuple[float, dict]] = []
        for doc in docs:
            if doc.get("organisation_id", "org_default") != organisation_id or doc.get("workspace_id", "wrk_default") != workspace_id:
                continue
            expires_at = doc.get("expires_at")
            if expires_at:
                try:
                    if datetime.fromisoformat(str(expires_at).replace("Z", "+00:00")) <= datetime.now(timezone.utc):
                        continue
                except ValueError:
                    continue
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
                    evidence_ids=[doc.get("_id") or doc.get("id")],
                )
            )
        return hits

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
