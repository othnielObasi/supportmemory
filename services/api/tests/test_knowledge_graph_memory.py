import pytest

from app.config import Settings
from app.context_health.service import ContextHealthService
from app.models.schemas import KbIngestRequest
from app.services.embedding_service import EmbeddingService
from app.services.kb_ingest_service import KbIngestService
from app.services.knowledge_graph_service import KnowledgeGraphService
from app.services.retrieval_service import RetrievalService


class MemoryStore:
    def __init__(self):
        self.data = {}

    async def insert_one(self, collection, doc):
        rows = self.data.setdefault(collection, [])
        doc_id = doc.get("_id") or doc.get("id")
        rows[:] = [row for row in rows if (row.get("_id") or row.get("id")) != doc_id]
        rows.append(dict(doc))
        return doc_id

    async def find_one(self, collection, doc_id):
        for row in self.data.get(collection, []):
            if (row.get("_id") or row.get("id")) == doc_id:
                return dict(row)
        return None

    async def find_one_by(self, collection, query=None, sort=None):
        rows = await self.find_many(collection, query=query, limit=1, sort=sort)
        return rows[0] if rows else None

    async def find_many(self, collection, query=None, limit=50, sort=None):
        query = query or {}
        rows = [dict(row) for row in self.data.get(collection, []) if all(str(row.get(k)) == str(v) for k, v in query.items())]
        return rows[:limit]

    async def update_one(self, collection, query, update):
        for row in self.data.get(collection, []):
            if all(str(row.get(k)) == str(v) for k, v in query.items()):
                row.update(update.get("$set", {}))
                for key, amount in update.get("$inc", {}).items():
                    row[key] = row.get(key, 0) + amount


@pytest.mark.asyncio
async def test_graph_traversal_is_tenant_scoped_and_returns_evidence_path():
    store = MemoryStore()
    graph = KnowledgeGraphService(store)
    ticket = await graph.upsert_node(
        node_type="ticket", canonical_key="TX-3104", organisation_id="org_a", workspace_id="wrk_a"
    )
    incident = await graph.upsert_node(
        node_type="incident", canonical_key="secret-rotation", organisation_id="org_a", workspace_id="wrk_a"
    )
    await graph.link(
        source_node_id=ticket.id, target_node_id=incident.id, relation="AFFECTED_BY",
        organisation_id="org_a", workspace_id="wrk_a", evidence_ids=["trace_1"], confidence=0.9,
    )
    paths = await graph.traverse(
        seed_node_ids=[ticket.id], organisation_id="org_a", workspace_id="wrk_a", max_depth=2
    )
    assert paths
    assert paths[0].relations == ["AFFECTED_BY"]
    assert paths[0].evidence_ids == ["trace_1"]
    assert await graph.traverse(seed_node_ids=[ticket.id], organisation_id="org_b", workspace_id="wrk_b") == []


@pytest.mark.asyncio
async def test_retrieval_combines_kb_and_graph_without_cross_tenant_leakage():
    settings = Settings(EMBEDDING_PROVIDER="hash", EMBEDDING_DIMENSIONS=64)
    store = MemoryStore()
    embeddings = EmbeddingService(settings)
    kb = KbIngestService(store, embeddings, settings)
    graph = KnowledgeGraphService(store)
    await kb.ingest(KbIngestRequest(
        title="Workspace A refund policy",
        text="Refunds for payment failures require the original ticket and processor reference.",
        organisation_id="org_a", workspace_id="wrk_a",
    ))
    await kb.ingest(KbIngestRequest(
        title="Workspace B private policy",
        text="Private workspace B refund exception must never be shown to another tenant.",
        organisation_id="org_b", workspace_id="wrk_b",
    ))
    ticket = await graph.upsert_node(
        node_type="ticket", canonical_key="TX-3104", organisation_id="org_a", workspace_id="wrk_a"
    )
    policy = await graph.upsert_node(
        node_type="policy", canonical_key="refund-policy", organisation_id="org_a", workspace_id="wrk_a"
    )
    await graph.link(
        source_node_id=ticket.id, target_node_id=policy.id, relation="SUPPORTED_BY",
        organisation_id="org_a", workspace_id="wrk_a", evidence_ids=["chk_a"],
    )
    retrieval = RetrievalService(store, embeddings, settings, kb=kb, graph=graph)
    _, context, hits = await retrieval.retrieve(
        "Check refund policy for TX-3104", "support_agent", task_id="task_a",
        organisation_id="org_a", workspace_id="wrk_a",
    )
    assert hits and all("Workspace B" not in hit.title for hit in hits)
    assert "Relevant relationship evidence" in context
    assert "AFFECTED_BY" not in context
    assert "SUPPORTED_BY" in context
    event = store.data["retrieval_events"][0]
    assert event["graph_paths"]
    assert event["workspace_id"] == "wrk_a"


def test_context_health_redacts_common_customer_pii_and_credentials():
    text = "Email sarah@example.com phone +44 7700 900123 password=hunter2 card 4111 1111 1111 1111"
    clean = ContextHealthService().sanitize_text(text)
    assert "sarah@example.com" not in clean
    assert "hunter2" not in clean
    assert "4111" not in clean
    assert "[redacted_email]" in clean
