from __future__ import annotations

from typing import List, Optional, TYPE_CHECKING

from app.db.postgres import DESCENDING

from app.config import Settings
from app.db.postgres import PostgresStore
from app.models.schemas import KbHit, LessonStatus, RetrievalEvent, RetrievedRule, new_id
from app.services.context_builder import ContextBuilder
from app.services.embedding_service import EmbeddingService
from app.services.search_ranking import rank_score

if TYPE_CHECKING:
    from app.services.kb_ingest_service import KbIngestService


class RetrievalService:
    def __init__(
        self,
        store: PostgresStore,
        embeddings: EmbeddingService,
        settings: Settings,
        kb: Optional["KbIngestService"] = None,
    ):
        self.store = store
        self.embeddings = embeddings
        self.settings = settings
        self.kb = kb
        self.context_builder = ContextBuilder()

    async def retrieve(
        self,
        task_description: str,
        agent_id: str,
        top_k: int = 3,
        task_id: str | None = None,
        include_kb: bool = True,
        kb_top_k: int = 3,
    ) -> tuple[List[RetrievedRule], str, List[KbHit]]:
        query_embedding = await self.embeddings.embed(task_description)
        rules = await self._local_search(task_description, query_embedding, top_k)
        kb_hits: List[KbHit] = []
        if include_kb and kb_top_k > 0 and self.kb is not None:
            kb_hits = await self.kb.search(task_description, top_k=kb_top_k, agent_id=agent_id)
        context_prefix = self.context_builder.build(rules, kb_hits=kb_hits)
        if task_id:
            event = RetrievalEvent(
                _id=new_id("retrieval"),
                task_id=task_id,
                agent_id=agent_id,
                query=task_description,
                retrieved_rules=rules,
                context_prefix=context_prefix,
            )
            await self.store.insert_one("retrieval_events", event.model_dump(by_alias=True))
        return rules, context_prefix, kb_hits

    async def _local_search(self, task_description: str, query_embedding: List[float], top_k: int) -> List[RetrievedRule]:
        docs = await self.store.find_many(
            "playbook_rules",
            {"status": LessonStatus.approved.value},
            limit=100,
            sort=[("created_at", DESCENDING)],
        )
        ranked = []
        lower_task = task_description.lower()
        for doc in docs:
            category_boost = 0.0
            if doc.get("category") == "pagination" and any(
                x in lower_task for x in ["ticket", "records", "api", "analyse", "analyze", "paginat"]
            ):
                category_boost = 0.2
            if "refund" in lower_task and "refund" in (doc.get("rule_text") or "").lower():
                category_boost += 0.1
            score = rank_score(
                query=task_description,
                document_text=doc.get("rule_text", ""),
                query_embedding=query_embedding,
                doc_embedding=doc.get("embedding", []) or [],
                title=doc.get("category", ""),
                tags=[doc.get("category", "")],
                extra_boost=category_boost,
                hash_embeddings=self.embeddings.uses_hash,
            )
            ranked.append((score, doc))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [
            RetrievedRule(
                rule_id=doc["_id"],
                score=round(float(score), 4),
                rule_text=doc["rule_text"],
                category=doc.get("category", "tool_use"),
            )
            for score, doc in ranked[:top_k]
            if score > 0.08
        ]
