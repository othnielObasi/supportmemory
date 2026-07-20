import pytest

from app.config import Settings
from app.models.schemas import HelpdeskMockTicketRequest, KbIngestRequest
from app.services.context_builder import ContextBuilder
from app.services.embedding_service import EmbeddingService
from app.services.helpdesk_connector import fetch_helpdesk_mock
from app.services.kb_ingest_service import KbIngestService
from app.db.postgres import PRODUCTION_COLLECTIONS


class MemoryStore:
    def __init__(self):
        self.data = {}

    async def insert_one(self, collection, doc):
        self.data.setdefault(collection, []).append(doc)
        return doc

    async def find_many(self, collection, query=None, limit=50, sort=None):
        rows = list(self.data.get(collection, []))
        query = query or {}
        filtered = []
        for row in rows:
            if all(str(row.get(k)) == str(v) for k, v in query.items()):
                filtered.append(row)
        return filtered[:limit]


@pytest.mark.asyncio
async def test_kb_ingest_chunks_embeds_and_searches():
    settings = Settings(embedding_provider="hash", embedding_dimensions=64)
    store = MemoryStore()
    kb = KbIngestService(store, EmbeddingService(settings), settings)
    ingested = await kb.ingest(
        KbIngestRequest(
            title="Refund policy",
            text=(
                "Refunds may be approved within 30 days of purchase when the customer reports a payment failure "
                "or duplicate charge. Prefer issuing a refund over forcing a retry when the processor settled the charge."
            ),
            tags=["refunds"],
        )
    )
    assert ingested.chunk_count >= 1
    assert ingested.embedding_provider == "hash"
    assert len(store.data["kb_chunks"]) == ingested.chunk_count
    assert len(store.data["kb_documents"]) == 1

    hits = await kb.search("When can we refund a payment failure?", top_k=3)
    assert hits
    assert hits[0].document_id == ingested.document_id
    assert hits[0].score > 0


@pytest.mark.asyncio
async def test_kb_context_builder_includes_knowledge_section():
    settings = Settings(embedding_provider="hash", embedding_dimensions=64)
    store = MemoryStore()
    kb = KbIngestService(store, EmbeddingService(settings), settings)
    await kb.ingest(
        KbIngestRequest(
            title="Pagination SOP",
            text=(
                "When fetching support tickets from a paginated helpdesk API, continue fetching until "
                "next_page_token is null before producing a final answer."
            ),
        )
    )
    hits = await kb.search("paginate support tickets next_page_token", top_k=2)
    prefix = ContextBuilder().build([], kb_hits=hits)
    assert "Relevant knowledge" in prefix
    assert "next_page_token" in prefix


def test_helpdesk_mock_connector_is_zendesk_shaped():
    response = fetch_helpdesk_mock(HelpdeskMockTicketRequest(source_system="zendesk_mock"))
    assert response.source_system == "zendesk_mock"
    assert response.connector == "helpdesk_webhook_api"
    assert "id" in response.ticket
    assert "subject" in response.ticket
    assert isinstance(response.comments, list)


def test_production_collections_include_kb():
    assert "kb_documents" in PRODUCTION_COLLECTIONS
    assert "kb_chunks" in PRODUCTION_COLLECTIONS


@pytest.mark.asyncio
async def test_seed_demo_is_idempotent():
    settings = Settings(embedding_provider="hash", embedding_dimensions=64)
    store = MemoryStore()
    kb = KbIngestService(store, EmbeddingService(settings), settings)

    first = await kb.seed_demo()
    second = await kb.seed_demo()
    assert len(first) == 3
    assert second == []
