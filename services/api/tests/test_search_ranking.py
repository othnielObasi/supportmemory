import pytest

from app.config import Settings
from app.models.schemas import KbIngestRequest
from app.services.embedding_service import EmbeddingService
from app.services.kb_ingest_service import KbIngestService
from app.services.search_ranking import coverage_score, rank_score, tokenize


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


def test_coverage_prefers_query_term_overlap_over_jaccard_style_penalty():
    query_terms = tokenize("When can we refund a payment failure?")
    doc_terms = set(tokenize(
        "Refunds may be approved within 30 days when the customer reports a payment failure or duplicate charge."
    ))
    cov = coverage_score(query_terms, doc_terms)
    assert cov >= 0.4


@pytest.mark.asyncio
async def test_rank_score_boosts_on_topic_policy():
    query = "When can we refund a payment failure?"
    on_topic = (
        "Refunds may be approved within 30 days of purchase when the customer reports a payment failure "
        "or duplicate charge. Prefer issuing a refund over forcing a retry."
    )
    off_topic = "International cooperation and certification ecosystem for AI governance standards."
    emb = EmbeddingService(Settings(EMBEDDING_PROVIDER="hash", embedding_dimensions=64))
    q_emb = await emb.embed(query)
    on_emb = await emb.embed(on_topic)
    off_emb = await emb.embed(off_topic)
    on_score = rank_score(
        query=query,
        document_text=on_topic,
        query_embedding=q_emb,
        doc_embedding=on_emb,
        title="Refund policy",
        tags=["refunds"],
        hash_embeddings=True,
    )
    off_score = rank_score(
        query=query,
        document_text=off_topic,
        query_embedding=q_emb,
        doc_embedding=off_emb,
        title="AI governance",
        tags=["governance"],
        hash_embeddings=True,
    )
    assert on_score > off_score
    assert on_score >= 0.35


@pytest.mark.asyncio
async def test_kb_search_ranks_refund_policy_high():
    settings = Settings(EMBEDDING_PROVIDER="hash", embedding_dimensions=128)
    store = MemoryStore()
    kb = KbIngestService(store, EmbeddingService(settings), settings)
    await kb.ingest(
        KbIngestRequest(
            title="Refund policy",
            text=(
                "Refunds may be approved within 30 days of purchase when the customer reports a payment failure "
                "or duplicate charge. Prefer issuing a refund over forcing a retry when the processor settled the charge."
            ),
            tags=["refunds", "billing"],
        )
    )
    await kb.ingest(
        KbIngestRequest(
            title="AI governance notes",
            text="A five-layer framework for AI governance integrating regulation standards and certification.",
            tags=["governance"],
        )
    )
    hits = await kb.search("When can we refund a payment failure?", top_k=2)
    assert hits
    assert hits[0].title == "Refund policy"
    assert hits[0].score >= 0.35
