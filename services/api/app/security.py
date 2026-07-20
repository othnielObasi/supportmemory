from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional

from fastapi import Header, HTTPException, Request, status

from app.config import Settings, get_settings
from app.db.postgres import PostgresStore
from app.models.schemas import new_id, utc_now

DEFAULT_SCOPES = {
    "runs:read",
    "runs:write",
    "checkpoints:read",
    "checkpoints:write",
    "memory:read",
    "memory:approve",
    "tools:read",
    "tools:execute",
    "gateways:read",
    "gateways:write",
    "audit:read",
    "admin:manage",
}

ROLE_SCOPES = {
    "owner": DEFAULT_SCOPES,
    "admin": DEFAULT_SCOPES,
    "developer": {
        "runs:read",
        "runs:write",
        "checkpoints:read",
        "checkpoints:write",
        "memory:read",
        "tools:read",
        "tools:execute",
        "gateways:read",
    },
    "operator": {
        "runs:read",
        "runs:write",
        "checkpoints:read",
        "checkpoints:write",
        "memory:read",
        "tools:read",
        "tools:execute",
        "audit:read",
    },
    "auditor": {"runs:read", "checkpoints:read", "memory:read", "tools:read", "gateways:read", "audit:read"},
    "viewer": {"runs:read", "checkpoints:read", "memory:read", "tools:read", "gateways:read"},
}


@dataclass(frozen=True)
class EnterprisePrincipal:
    organisation_id: str
    workspace_id: str
    project_id: str
    environment_id: str
    actor_id: str
    role: str
    scopes: set[str]
    api_key_id: Optional[str] = None

    def require(self, required_scopes: Iterable[str]) -> None:
        missing = [scope for scope in required_scopes if scope not in self.scopes and "admin:manage" not in self.scopes]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"message": "Missing required TraceMemory scope", "missing_scopes": missing},
            )

    def context_dict(self) -> dict[str, str]:
        return {
            "organisation_id": self.organisation_id,
            "workspace_id": self.workspace_id,
            "project_id": self.project_id,
            "environment_id": self.environment_id,
            "actor_id": self.actor_id,
        }


def hash_api_key(raw_key: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    return hmac.new(settings.signing_secret.encode("utf-8"), raw_key.encode("utf-8"), hashlib.sha256).hexdigest()


def create_api_key_value(prefix: str = "cnt") -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"


def scopes_for_role(role: str) -> set[str]:
    return set(ROLE_SCOPES.get(role.lower(), ROLE_SCOPES["viewer"]))


async def create_audit_log(
    store: PostgresStore,
    *,
    action: str,
    principal: EnterprisePrincipal | None,
    resource_type: str,
    resource_id: str | None = None,
    outcome: str = "success",
    metadata: dict | None = None,
) -> str:
    doc_id = new_id("audit")
    context = principal.context_dict() if principal else {}
    await store.insert_one(
        "audit_logs",
        {
            "_id": doc_id,
            **context,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "outcome": outcome,
            "metadata": metadata or {},
            "created_at": utc_now(),
        },
    )
    return doc_id


async def resolve_principal(
    request: Request,
    store: PostgresStore,
    settings: Settings,
    x_tracememory_api_key: str | None = Header(default=None, alias="X-TraceMemory-API-Key"),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_organisation_id: str | None = Header(default=None, alias="X-Organisation-Id"),
    x_workspace_id: str | None = Header(default=None, alias="X-Workspace-Id"),
    x_project_id: str | None = Header(default=None, alias="X-Project-Id"),
    x_environment_id: str | None = Header(default=None, alias="X-Environment-Id"),
) -> EnterprisePrincipal:
    raw_key = x_tracememory_api_key
    if not raw_key and authorization and authorization.lower().startswith("bearer "):
        raw_key = authorization.split(" ", 1)[1].strip()

    if raw_key:
        key_hash = hash_api_key(raw_key, settings)
        doc = await store.find_one_by("api_keys", {"key_hash": key_hash})
        if not doc or doc.get("status") != "active":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or inactive TraceMemory API key")
        scopes = set(doc.get("scopes") or scopes_for_role(doc.get("role", "viewer")))
        return EnterprisePrincipal(
            organisation_id=doc["organisation_id"],
            workspace_id=doc["workspace_id"],
            project_id=doc.get("project_id") or x_project_id or settings.default_project_id,
            environment_id=doc.get("environment_id") or x_environment_id or settings.default_environment_id,
            actor_id=doc.get("actor_id") or doc.get("name") or "service-account",
            role=doc.get("role", "developer"),
            scopes=scopes,
            api_key_id=doc.get("_id") or doc.get("id"),
        )

    if settings.auth_required:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="TraceMemory API key required")

    role = request.headers.get("X-TraceMemory-Role", "owner")
    return EnterprisePrincipal(
        organisation_id=x_organisation_id or settings.default_organisation_id,
        workspace_id=x_workspace_id or settings.default_workspace_id,
        project_id=x_project_id or settings.default_project_id,
        environment_id=x_environment_id or settings.default_environment_id,
        actor_id=request.headers.get("X-Actor-Id", "local-dev"),
        role=role,
        scopes=scopes_for_role(role),
        api_key_id=None,
    )
