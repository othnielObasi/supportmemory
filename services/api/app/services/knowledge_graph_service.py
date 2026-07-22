from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Iterable

from app.db.postgres import PostgresStore
from app.models.schemas import GraphEdge, GraphNode, GraphPath
from app.services.search_ranking import tokenize


NODE_TYPES = {
    "customer", "account", "ticket", "incident", "policy", "product",
    "error_code", "kb_chunk", "execution_trace", "lesson", "tool_action",
    "contact_channel", "plan_tier",
}
RELATIONS = {
    "BELONGS_TO", "OPENED", "AFFECTED_BY", "MENTIONS", "RESOLVED_BY",
    "SUPPORTED_BY", "LEARNED_FROM", "APPLIES_TO", "SUPERSEDES", "PREFERS",
    "REQUIRES_APPROVAL", "USED", "EXECUTED", "INVESTIGATED",
}


class KnowledgeGraphService:
    """Small, tenant-scoped property graph stored in TraceMemory's JSONB store."""

    def __init__(self, store: PostgresStore):
        self.store = store

    async def upsert_node(
        self, *, node_type: str, canonical_key: str, organisation_id: str,
        workspace_id: str, project_id: str = "prj_default", environment_id: str = "dev",
        properties: dict | None = None, source_type: str = "manual",
        source_id: str = "manual", confidence: float = 1.0,
        valid_until: datetime | None = None,
    ) -> GraphNode:
        node_type = node_type.strip().lower()
        if node_type not in NODE_TYPES:
            raise ValueError(f"Unsupported graph node type: {node_type}")
        canonical_key = canonical_key.strip().lower()
        if not canonical_key:
            raise ValueError("canonical_key is required")
        query = {
            "organisation_id": organisation_id, "workspace_id": workspace_id,
            "node_type": node_type, "canonical_key": canonical_key,
        }
        existing = await self.store.find_one_by("knowledge_graph_nodes", query)
        if existing:
            merged = dict(existing)
            merged["properties"] = {**(existing.get("properties") or {}), **(properties or {})}
            merged["confidence"] = max(float(existing.get("confidence", 0)), confidence)
            merged["source_type"] = source_type
            merged["source_id"] = source_id
            if valid_until is not None:
                merged["valid_until"] = valid_until
            await self.store.insert_one("knowledge_graph_nodes", merged)
            return GraphNode.model_validate(merged)
        node = GraphNode(
            organisation_id=organisation_id, workspace_id=workspace_id,
            project_id=project_id, environment_id=environment_id,
            node_type=node_type, canonical_key=canonical_key, properties=properties or {},
            source_type=source_type, source_id=source_id, confidence=confidence,
            valid_until=valid_until,
        )
        await self.store.insert_one("knowledge_graph_nodes", node.model_dump(by_alias=True))
        return node

    async def link(
        self, *, source_node_id: str, target_node_id: str, relation: str,
        organisation_id: str, workspace_id: str, project_id: str = "prj_default",
        environment_id: str = "dev", evidence_ids: list[str] | None = None,
        confidence: float = 1.0, properties: dict | None = None,
        valid_until: datetime | None = None,
    ) -> GraphEdge:
        relation = relation.strip().upper()
        if relation not in RELATIONS:
            raise ValueError(f"Unsupported graph relation: {relation}")
        source = await self.store.find_one("knowledge_graph_nodes", source_node_id)
        target = await self.store.find_one("knowledge_graph_nodes", target_node_id)
        if not source or not target:
            raise ValueError("Both graph nodes must exist")
        for node in (source, target):
            if node.get("organisation_id") != organisation_id or node.get("workspace_id") != workspace_id:
                raise PermissionError("Cross-tenant graph edges are not allowed")
        query = {
            "organisation_id": organisation_id, "workspace_id": workspace_id,
            "source_node_id": source_node_id, "target_node_id": target_node_id,
            "relation": relation,
        }
        existing = await self.store.find_one_by("knowledge_graph_edges", query)
        if existing:
            existing["evidence_ids"] = sorted(set((existing.get("evidence_ids") or []) + (evidence_ids or [])))
            existing["confidence"] = max(float(existing.get("confidence", 0)), confidence)
            if valid_until is not None:
                existing["valid_until"] = valid_until
            await self.store.insert_one("knowledge_graph_edges", existing)
            return GraphEdge.model_validate(existing)
        edge = GraphEdge(
            organisation_id=organisation_id, workspace_id=workspace_id,
            project_id=project_id, environment_id=environment_id,
            source_node_id=source_node_id, target_node_id=target_node_id,
            relation=relation, evidence_ids=evidence_ids or [], confidence=confidence,
            properties=properties or {},
            valid_until=valid_until,
        )
        await self.store.insert_one("knowledge_graph_edges", edge.model_dump(by_alias=True))
        return edge

    async def resolve_seeds(self, query: str, *, organisation_id: str, workspace_id: str, limit: int = 6) -> list[GraphNode]:
        docs = await self.store.find_many(
            "knowledge_graph_nodes",
            {"organisation_id": organisation_id, "workspace_id": workspace_id},
            limit=300,
        )
        terms = set(tokenize(query))
        ranked: list[tuple[float, dict]] = []
        for doc in docs:
            if self._expired(doc.get("valid_until")):
                continue
            blob = " ".join([doc.get("canonical_key", ""), str(doc.get("properties") or {})]).lower()
            overlap = sum(1 for term in terms if term in blob)
            exact = 2 if doc.get("canonical_key", "") in query.lower() else 0
            score = overlap + exact
            if score:
                ranked.append((score, doc))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [GraphNode.model_validate(doc) for _, doc in ranked[:limit]]

    async def traverse(
        self, *, seed_node_ids: list[str], organisation_id: str, workspace_id: str,
        relations: Iterable[str] | None = None, max_depth: int = 2, max_paths: int = 12,
    ) -> list[GraphPath]:
        allowed = {r.upper() for r in (relations or [])}
        queue: list[tuple[str, list[str], list[str], list[str], float]] = [
            (node_id, [node_id], [], [], 1.0) for node_id in seed_node_ids
        ]
        paths: list[GraphPath] = []
        while queue and len(paths) < max_paths:
            current, node_ids, rels, evidence, confidence = queue.pop(0)
            if len(rels) >= max_depth:
                continue
            outgoing = await self.store.find_many(
                "knowledge_graph_edges",
                {"organisation_id": organisation_id, "workspace_id": workspace_id, "source_node_id": current},
                limit=50,
            )
            incoming = await self.store.find_many(
                "knowledge_graph_edges",
                {"organisation_id": organisation_id, "workspace_id": workspace_id, "target_node_id": current},
                limit=50,
            )
            for edge, reverse in [(e, False) for e in outgoing] + [(e, True) for e in incoming]:
                if self._expired(edge.get("valid_until")):
                    continue
                relation = edge.get("relation", "")
                if allowed and relation not in allowed:
                    continue
                next_id = edge.get("source_node_id") if reverse else edge.get("target_node_id")
                if not next_id or next_id in node_ids:
                    continue
                next_nodes = [*node_ids, next_id]
                next_rels = [*rels, f"{relation}:reverse" if reverse else relation]
                next_evidence = sorted(set([*evidence, *(edge.get("evidence_ids") or [])]))
                next_confidence = confidence * float(edge.get("confidence", 1.0))
                path = GraphPath(
                    node_ids=next_nodes, relations=next_rels, evidence_ids=next_evidence,
                    score=round(next_confidence / len(next_rels), 4),
                    explanation=" -> ".join(next_rels),
                )
                paths.append(path)
                queue.append((next_id, next_nodes, next_rels, next_evidence, next_confidence))
                if len(paths) >= max_paths:
                    break
        return paths

    @staticmethod
    def _expired(value) -> bool:
        if not value:
            return False
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")) <= datetime.now(timezone.utc)
        except ValueError:
            return True

    async def extract_from_trace(self, trace, *, organisation_id: str, workspace_id: str, project_id: str, environment_id: str) -> list[GraphNode]:
        trace_node = await self.upsert_node(
            node_type="execution_trace", canonical_key=trace.id,
            organisation_id=organisation_id, workspace_id=workspace_id,
            project_id=project_id, environment_id=environment_id,
            properties={"task_id": trace.task_id, "status": str(trace.status), "failure_type": str(trace.failure_type)},
            source_type="execution_trace", source_id=trace.id,
        )
        created = [trace_node]
        text = f"{trace.task_description} {trace.final_output}"
        identifiers = {
            "ticket": re.findall(r"\b(?:TX|TKT|TICKET)[-_ ]?\d{2,}\b", text, flags=re.I),
            "error_code": re.findall(r"\b(?:HTTP\s*)?[1-5]\d\d\b", text, flags=re.I),
            "account": re.findall(r"\bacct[_-][a-z0-9]+\b", text, flags=re.I),
        }
        for node_type, values in identifiers.items():
            for value in sorted(set(values))[:12]:
                node = await self.upsert_node(
                    node_type=node_type, canonical_key=value,
                    organisation_id=organisation_id, workspace_id=workspace_id,
                    project_id=project_id, environment_id=environment_id,
                    properties={"label": value}, source_type="execution_trace", source_id=trace.id,
                )
                await self.link(
                    source_node_id=trace_node.id, target_node_id=node.id,
                    relation="INVESTIGATED" if node_type == "ticket" else "MENTIONS",
                    organisation_id=organisation_id, workspace_id=workspace_id,
                    project_id=project_id, environment_id=environment_id,
                    evidence_ids=[trace.id], confidence=0.95,
                )
                created.append(node)
        return created

    async def format_paths(self, paths: list[GraphPath]) -> str:
        if not paths:
            return ""
        node_ids = sorted({node_id for path in paths for node_id in path.node_ids})
        nodes = {node_id: await self.store.find_one("knowledge_graph_nodes", node_id) for node_id in node_ids}
        lines = []
        for path in paths[:6]:
            labels = []
            for node_id in path.node_ids:
                node = nodes.get(node_id) or {}
                labels.append(f"{node.get('node_type', 'entity')}:{node.get('canonical_key', node_id)}")
            chain = labels[0]
            for relation, label in zip(path.relations, labels[1:]):
                chain += f" -[{relation}]-> {label}"
            evidence = f" evidence={','.join(path.evidence_ids)}" if path.evidence_ids else ""
            lines.append(f"- {chain}{evidence}")
        return "Relevant relationship evidence:\n" + "\n".join(lines)

    async def delete_node(self, node_id: str, *, organisation_id: str, workspace_id: str) -> int:
        node = await self.store.find_one("knowledge_graph_nodes", node_id)
        if not node or node.get("organisation_id") != organisation_id or node.get("workspace_id") != workspace_id:
            return 0
        await self.store.delete_many("knowledge_graph_edges", {"organisation_id": organisation_id, "workspace_id": workspace_id, "source_node_id": node_id})
        await self.store.delete_many("knowledge_graph_edges", {"organisation_id": organisation_id, "workspace_id": workspace_id, "target_node_id": node_id})
        return await self.store.delete_many("knowledge_graph_nodes", {"_id": node_id})
