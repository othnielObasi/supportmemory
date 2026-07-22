from __future__ import annotations

from typing import List, Optional, TYPE_CHECKING

from app.db.postgres import DESCENDING

from app.config import Settings
from app.db.postgres import PostgresStore
from app.models.schemas import KbHit, LessonStatus, RetrievalEvent, RetrievedRule, new_id
from app.services.context_builder import ContextBuilder
from app.services.embedding_service import EmbeddingService
from app.services.search_ranking import rank_score
from app.services.knowledge_graph_service import KnowledgeGraphService

if TYPE_CHECKING:
    from app.services.kb_ingest_service import KbIngestService


class RetrievalService:
    def __init__(
        self,
        store: PostgresStore,
        embeddings: EmbeddingService,
        settings: Settings,
        kb: Optional["KbIngestService"] = None,
        graph: Optional[KnowledgeGraphService] = None,
    ):
        self.store = store
        self.embeddings = embeddings
        self.settings = settings
        self.kb = kb
        self.graph = graph
        self.context_builder = ContextBuilder()

    async def retrieve(
        self,
        task_description: str,
        agent_id: str,
        top_k: int = 3,
        task_id: str | None = None,
        include_kb: bool = True,
        kb_top_k: int = 3,
        organisation_id: str = "org_default",
        workspace_id: str = "wrk_default",
        project_id: str = "prj_default",
        environment_id: str = "dev",
        trace_id: str | None = None,
        include_graph: bool = True,
    ) -> tuple[List[RetrievedRule], str, List[KbHit]]:
        query_embedding = await self.embeddings.embed(task_description)
        rules = await self._local_search(task_description, query_embedding, top_k, organisation_id=organisation_id, workspace_id=workspace_id, agent_id=agent_id)
        kb_hits: List[KbHit] = []
        if include_kb and kb_top_k > 0 and self.kb is not None:
            kb_hits = await self.kb.search(task_description, top_k=kb_top_k, agent_id=agent_id, organisation_id=organisation_id, workspace_id=workspace_id)
        graph_paths = []
        graph_context = ""
        if include_graph and self.graph is not None:
            seeds = await self.graph.resolve_seeds(task_description, organisation_id=organisation_id, workspace_id=workspace_id)
            graph_paths = await self.graph.traverse(
                seed_node_ids=[node.id for node in seeds], organisation_id=organisation_id,
                workspace_id=workspace_id, max_depth=self.settings.knowledge_graph_max_depth,
                max_paths=self.settings.knowledge_graph_max_paths,
            )
            graph_context = await self.graph.format_paths(graph_paths)
        context_prefix = self.context_builder.build(rules, kb_hits=kb_hits, graph_context=graph_context)
        if task_id:
            event = RetrievalEvent(
                _id=new_id("retrieval"),
                task_id=task_id,
                agent_id=agent_id,
                query=task_description,
                retrieved_rules=rules,
                context_prefix=context_prefix,
                organisation_id=organisation_id,
                workspace_id=workspace_id,
                project_id=project_id,
                environment_id=environment_id,
                trace_id=trace_id,
                kb_hits=[hit.model_dump() for hit in kb_hits],
                graph_paths=[path.model_dump() for path in graph_paths],
                embedding_provider=self.embeddings.provider,
            )
            await self.store.insert_one("retrieval_events", event.model_dump(by_alias=True))
            for rule in rules:
                doc = await self.store.find_one("playbook_rules", rule.rule_id)
                if doc:
                    applied = list(doc.get("applied_runs") or [])
                    if task_id not in applied:
                        applied.append(task_id)
                        await self.store.update_one("playbook_rules", {"_id": rule.rule_id}, {"$set": {"applied_runs": applied[-200:]}})
        return rules, context_prefix, kb_hits

    async def _local_search(self, task_description: str, query_embedding: List[float], top_k: int, *, organisation_id: str, workspace_id: str, agent_id: str) -> List[RetrievedRule]:
        docs = await self.store.find_many(
            "playbook_rules",
            {"status": LessonStatus.approved.value},
            limit=100,
            sort=[("created_at", DESCENDING)],
        )
        ranked = []
        lower_task = task_description.lower()
        for doc in docs:
            if doc.get("organisation_id", "org_default") != organisation_id or doc.get("workspace_id", "wrk_default") != workspace_id:
                continue
            scope = doc.get("scope") or []
            if scope and not any(value in scope for value in ("global", agent_id, workspace_id)):
                continue
            if doc.get("agent_id") and doc.get("agent_id") not in {agent_id, "support_agent", "ticket-investigation-agent"}:
                continue
            expires_at = doc.get("expires_at")
            if expires_at:
                from datetime import datetime, timezone
                try:
                    if datetime.fromisoformat(str(expires_at).replace("Z", "+00:00")) <= datetime.now(timezone.utc):
                        continue
                except ValueError:
                    continue
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
                evidence_ids=[doc.get("source_trace_id")] if doc.get("source_trace_id") else [],
            )
            for score, doc in ranked[:top_k]
            if score > 0.08
        ]
