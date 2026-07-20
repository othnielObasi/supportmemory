from __future__ import annotations

from typing import Any

from app.db.postgres import PostgresStore
from app.models.schemas import new_id, stable_hash, utc_now
from app.security import EnterprisePrincipal, create_audit_log

DEFAULT_TOOL_POLICY = {
    "timeout_seconds": 30,
    "retry_count": 1,
    "requires_human_review": False,
    "allowed_tool_types": ["read"],
    "result_validation": {"require_no_error": True, "allow_model_context": True},
}


class ToolRegistryService:
    def __init__(self, store: PostgresStore):
        self.store = store

    async def register(self, *, principal: EnterprisePrincipal, payload: dict[str, Any]) -> dict[str, Any]:
        tool_id = payload.get("tool_id") or new_id("tool")
        doc = {
            "_id": tool_id,
            **principal.context_dict(),
            "tool_id": tool_id,
            "name": payload["name"],
            "description": payload.get("description", ""),
            "tool_type": payload.get("tool_type", "read"),
            "schema": payload.get("schema", {}),
            "auth_profile_id": payload.get("auth_profile_id"),
            "permission_scope": payload.get("permission_scope", "tools:execute"),
            "gateway": payload.get("gateway", "mcp"),
            "policy": {**DEFAULT_TOOL_POLICY, **payload.get("policy", {})},
            "enabled": bool(payload.get("enabled", True)),
            "created_at": utc_now(),
            "updated_at": utc_now(),
        }
        await self.store.insert_one("tool_registry", doc)
        await create_audit_log(self.store, action="tool.register", principal=principal, resource_type="tool", resource_id=tool_id, metadata={"name": doc["name"]})
        return doc

    async def list(self, *, principal: EnterprisePrincipal, limit: int = 100) -> list[dict[str, Any]]:
        return await self.store.find_many("tool_registry", {"workspace_id": principal.workspace_id}, limit=limit)

    async def get(self, *, principal: EnterprisePrincipal, tool_id: str) -> dict[str, Any] | None:
        doc = await self.store.find_one("tool_registry", tool_id)
        if not doc or doc.get("workspace_id") != principal.workspace_id:
            return None
        return doc

    async def validate_invocation(self, *, principal: EnterprisePrincipal, tool_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
        tool = await self.get(principal=principal, tool_id=tool_id)
        if not tool:
            return {"passed": False, "reason": "tool_not_registered", "tool_id": tool_id}
        if not tool.get("enabled", True):
            return {"passed": False, "reason": "tool_disabled", "tool_id": tool_id}
        required_scope = tool.get("permission_scope", "tools:execute")
        try:
            principal.require([required_scope])
        except Exception:
            return {"passed": False, "reason": "missing_scope", "required_scope": required_scope}
        return {
            "passed": True,
            "tool_id": tool_id,
            "tool_name": tool.get("name"),
            "input_hash": stable_hash(arguments),
            "policy": tool.get("policy", DEFAULT_TOOL_POLICY),
        }
