from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.config import Settings, get_settings
from app.db.postgres import DESCENDING, PostgresStore, PRODUCTION_COLLECTIONS
from app.models.schemas import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyResponse,
    AuditLogResponse,
    BackgroundJobRequest,
    BackgroundJobResponse,
    EnterpriseContextResponse,
    EnterpriseReadinessResponse,
    ModelGatewayConfigRequest,
    ModelGatewayConfigResponse,
    OrganisationCreateRequest,
    OrganisationResponse,
    ProjectCreateRequest,
    ProjectResponse,
    TenantContext,
    ToolRegistryCreateRequest,
    ToolRegistryResponse,
    WorkspaceCreateRequest,
    WorkspaceResponse,
    new_id,
    stable_hash,
    utc_now,
)
from app.security import (
    EnterprisePrincipal,
    create_api_key_value,
    create_audit_log,
    hash_api_key,
    resolve_principal,
    scopes_for_role,
)
from app.services.job_queue import JobQueueService
from app.services.model_gateway import ModelGatewayRegistry
from app.services.tool_registry import ToolRegistryService

router = APIRouter(tags=["enterprise"])


def get_store() -> PostgresStore:
    from app.main import store

    return store


async def principal_dependency(
    request: Request,
    x_tracememory_api_key: str | None = Header(default=None, alias="X-TraceMemory-API-Key"),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_organisation_id: str | None = Header(default=None, alias="X-Organisation-Id"),
    x_workspace_id: str | None = Header(default=None, alias="X-Workspace-Id"),
    x_project_id: str | None = Header(default=None, alias="X-Project-Id"),
    x_environment_id: str | None = Header(default=None, alias="X-Environment-Id"),
    store: PostgresStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> EnterprisePrincipal:
    return await resolve_principal(
        request,
        store,
        settings,
        x_tracememory_api_key=x_tracememory_api_key,
        authorization=authorization,
        x_organisation_id=x_organisation_id,
        x_workspace_id=x_workspace_id,
        x_project_id=x_project_id,
        x_environment_id=x_environment_id,
    )


def _tenant_response(principal: EnterprisePrincipal) -> TenantContext:
    return TenantContext(**principal.context_dict())


@router.get("/context", response_model=EnterpriseContextResponse)
async def enterprise_context(principal: EnterprisePrincipal = Depends(principal_dependency), settings: Settings = Depends(get_settings)):
    return EnterpriseContextResponse(
        principal=_tenant_response(principal),
        role=principal.role,
        scopes=sorted(principal.scopes),
        auth_required=settings.auth_required,
    )


@router.post("/bootstrap", response_model=ApiKeyCreateResponse)
async def bootstrap_enterprise_account(
    payload: OrganisationCreateRequest,
    bootstrap_token: str | None = Header(default=None, alias="X-Bootstrap-Token"),
    store: PostgresStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
):
    if settings.environment == "production" and settings.bootstrap_admin_token and bootstrap_token != settings.bootstrap_admin_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid bootstrap token")
    if settings.environment == "production" and not settings.bootstrap_admin_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="BOOTSTRAP_ADMIN_TOKEN must be set in production")

    organisation_id = new_id("org")
    workspace_id = new_id("wrk")
    project_id = new_id("prj")
    created_at = utc_now()
    await store.insert_one("organisations", {"_id": organisation_id, "organisation_id": organisation_id, "name": payload.name, "slug": payload.slug, "metadata": payload.metadata, "created_at": created_at})
    await store.insert_one("workspaces", {"_id": workspace_id, "workspace_id": workspace_id, "organisation_id": organisation_id, "name": "Default Workspace", "slug": "default", "metadata": {}, "created_at": created_at})
    await store.insert_one("projects", {"_id": project_id, "project_id": project_id, "workspace_id": workspace_id, "organisation_id": organisation_id, "environment_id": "dev", "name": "Default Project", "slug": "default", "metadata": {}, "created_at": created_at})

    raw_key = create_api_key_value()
    key_id = new_id("key")
    role = "owner"
    scopes = sorted(scopes_for_role(role))
    key_preview = f"{raw_key[:10]}...{raw_key[-6:]}"
    await store.insert_one(
        "api_keys",
        {
            "_id": key_id,
            "api_key_id": key_id,
            "organisation_id": organisation_id,
            "workspace_id": workspace_id,
            "project_id": project_id,
            "environment_id": "dev",
            "name": "bootstrap-owner-key",
            "role": role,
            "scopes": scopes,
            "key_hash": hash_api_key(raw_key, settings),
            "key_preview": key_preview,
            "status": "active",
            "actor_id": "bootstrap-owner",
            "created_at": created_at,
        },
    )
    await create_audit_log(store, action="enterprise.bootstrap", principal=None, resource_type="organisation", resource_id=organisation_id, metadata={"workspace_id": workspace_id, "project_id": project_id})
    return ApiKeyCreateResponse(api_key_id=key_id, name="bootstrap-owner-key", role=role, scopes=scopes, key_preview=key_preview, api_key=raw_key, created_at=created_at)


@router.post("/organisations", response_model=OrganisationResponse)
async def create_organisation(payload: OrganisationCreateRequest, principal: EnterprisePrincipal = Depends(principal_dependency), store: PostgresStore = Depends(get_store)):
    principal.require(["admin:manage"])
    organisation_id = new_id("org")
    created_at = utc_now()
    doc = {"_id": organisation_id, "organisation_id": organisation_id, "name": payload.name, "slug": payload.slug, "metadata": payload.metadata, "created_at": created_at}
    await store.insert_one("organisations", doc)
    await create_audit_log(store, action="organisation.create", principal=principal, resource_type="organisation", resource_id=organisation_id)
    return OrganisationResponse(**doc)


@router.post("/workspaces", response_model=WorkspaceResponse)
async def create_workspace(payload: WorkspaceCreateRequest, principal: EnterprisePrincipal = Depends(principal_dependency), store: PostgresStore = Depends(get_store)):
    principal.require(["admin:manage"])
    workspace_id = new_id("wrk")
    doc = {
        "_id": workspace_id,
        "workspace_id": workspace_id,
        "organisation_id": payload.organisation_id or principal.organisation_id,
        "name": payload.name,
        "slug": payload.slug,
        "metadata": payload.metadata,
        "created_at": utc_now(),
    }
    await store.insert_one("workspaces", doc)
    await create_audit_log(store, action="workspace.create", principal=principal, resource_type="workspace", resource_id=workspace_id)
    return WorkspaceResponse(**doc)


@router.get("/workspaces", response_model=list[WorkspaceResponse])
async def list_workspaces(principal: EnterprisePrincipal = Depends(principal_dependency), store: PostgresStore = Depends(get_store)):
    principal.require(["runs:read"])
    docs = await store.find_many("workspaces", {"organisation_id": principal.organisation_id}, limit=100)
    return [WorkspaceResponse(**doc) for doc in docs]


@router.post("/projects", response_model=ProjectResponse)
async def create_project(payload: ProjectCreateRequest, principal: EnterprisePrincipal = Depends(principal_dependency), store: PostgresStore = Depends(get_store)):
    principal.require(["admin:manage"])
    project_id = new_id("prj")
    doc = {
        "_id": project_id,
        "project_id": project_id,
        "workspace_id": payload.workspace_id or principal.workspace_id,
        "organisation_id": principal.organisation_id,
        "name": payload.name,
        "slug": payload.slug,
        "environment_id": payload.environment_id,
        "metadata": payload.metadata,
        "created_at": utc_now(),
    }
    await store.insert_one("projects", doc)
    await create_audit_log(store, action="project.create", principal=principal, resource_type="project", resource_id=project_id)
    return ProjectResponse(**doc)


@router.get("/projects", response_model=list[ProjectResponse])
async def list_projects(principal: EnterprisePrincipal = Depends(principal_dependency), store: PostgresStore = Depends(get_store)):
    principal.require(["runs:read"])
    docs = await store.find_many("projects", {"workspace_id": principal.workspace_id}, limit=100)
    return [ProjectResponse(**doc) for doc in docs]


@router.post("/api-keys", response_model=ApiKeyCreateResponse)
async def create_api_key(payload: ApiKeyCreateRequest, principal: EnterprisePrincipal = Depends(principal_dependency), store: PostgresStore = Depends(get_store), settings: Settings = Depends(get_settings)):
    principal.require(["admin:manage"])
    raw_key = create_api_key_value()
    key_id = new_id("key")
    scopes = payload.scopes or sorted(scopes_for_role(payload.role.value))
    key_preview = f"{raw_key[:10]}...{raw_key[-6:]}"
    doc = {
        "_id": key_id,
        "api_key_id": key_id,
        **principal.context_dict(),
        "project_id": payload.project_id or principal.project_id,
        "environment_id": payload.environment_id or principal.environment_id,
        "name": payload.name,
        "role": payload.role.value,
        "scopes": scopes,
        "key_hash": hash_api_key(raw_key, settings),
        "key_preview": key_preview,
        "status": "active",
        "actor_id": payload.name,
        "expires_at": payload.expires_at,
        "created_at": utc_now(),
    }
    await store.insert_one("api_keys", doc)
    await create_audit_log(store, action="api_key.create", principal=principal, resource_type="api_key", resource_id=key_id, metadata={"role": payload.role.value})
    return ApiKeyCreateResponse(api_key_id=key_id, name=payload.name, role=payload.role, scopes=scopes, key_preview=key_preview, api_key=raw_key, created_at=doc["created_at"])


@router.get("/api-keys", response_model=list[ApiKeyResponse])
async def list_api_keys(principal: EnterprisePrincipal = Depends(principal_dependency), store: PostgresStore = Depends(get_store)):
    principal.require(["admin:manage"])
    docs = await store.find_many("api_keys", {"workspace_id": principal.workspace_id}, limit=100)
    return [ApiKeyResponse(api_key_id=doc.get("api_key_id") or doc.get("_id"), name=doc["name"], role=doc.get("role", "developer"), scopes=doc.get("scopes", []), status=doc.get("status", "active"), key_preview=doc.get("key_preview", "hidden"), created_at=doc["created_at"], last_used_at=doc.get("last_used_at")) for doc in docs]


@router.get("/gateways", response_model=list[ModelGatewayConfigResponse])
async def list_gateways(principal: EnterprisePrincipal = Depends(principal_dependency), settings: Settings = Depends(get_settings), store: PostgresStore = Depends(get_store)):
    principal.require(["gateways:read"])
    registry = ModelGatewayRegistry(settings)
    dynamic = await store.find_many("model_gateway_configs", {"workspace_id": principal.workspace_id}, limit=100)
    out: list[ModelGatewayConfigResponse] = []
    for desc in registry.descriptors():
        out.append(ModelGatewayConfigResponse(gateway_id=f"builtin-{desc.name}", name=desc.name, provider=desc.provider, enabled=desc.enabled, model_map=desc.models, health={"capabilities": desc.capabilities, "source": "builtin"}, created_at=utc_now()))
    for doc in dynamic:
        out.append(ModelGatewayConfigResponse(gateway_id=doc.get("gateway_id") or doc.get("_id"), name=doc["name"], provider=doc["provider"], enabled=doc.get("enabled", True), model_map=doc.get("model_map", {}), health=doc.get("health", {}), created_at=doc["created_at"]))
    return out


@router.post("/gateways", response_model=ModelGatewayConfigResponse)
async def create_gateway_config(payload: ModelGatewayConfigRequest, principal: EnterprisePrincipal = Depends(principal_dependency), store: PostgresStore = Depends(get_store)):
    principal.require(["gateways:write"])
    gateway_id = new_id("gw")
    doc = {
        "_id": gateway_id,
        "gateway_id": gateway_id,
        **principal.context_dict(),
        "name": payload.name,
        "provider": payload.provider,
        "base_url": payload.base_url,
        "model_map": payload.model_map,
        "enabled": payload.enabled,
        "metadata": payload.metadata,
        "health": {"status": "configured", "source": "workspace"},
        "created_at": utc_now(),
    }
    await store.insert_one("model_gateway_configs", doc)
    await create_audit_log(store, action="gateway.create", principal=principal, resource_type="model_gateway", resource_id=gateway_id, metadata={"provider": payload.provider})
    return ModelGatewayConfigResponse(gateway_id=gateway_id, name=payload.name, provider=payload.provider, enabled=payload.enabled, model_map=payload.model_map, health=doc["health"], created_at=doc["created_at"])


@router.post("/tools", response_model=ToolRegistryResponse)
async def register_tool(payload: ToolRegistryCreateRequest, principal: EnterprisePrincipal = Depends(principal_dependency), store: PostgresStore = Depends(get_store)):
    principal.require(["tools:read"])
    service = ToolRegistryService(store)
    doc = await service.register(principal=principal, payload=payload.model_dump())
    return ToolRegistryResponse(tool_id=doc["tool_id"], name=doc["name"], description=doc["description"], tool_type=doc["tool_type"], permission_scope=doc["permission_scope"], gateway=doc["gateway"], enabled=doc["enabled"], policy=doc["policy"], created_at=doc["created_at"])


@router.get("/tools", response_model=list[ToolRegistryResponse])
async def list_tools(principal: EnterprisePrincipal = Depends(principal_dependency), store: PostgresStore = Depends(get_store)):
    principal.require(["tools:read"])
    docs = await ToolRegistryService(store).list(principal=principal)
    return [ToolRegistryResponse(tool_id=doc["tool_id"], name=doc["name"], description=doc.get("description", ""), tool_type=doc.get("tool_type", "read"), permission_scope=doc.get("permission_scope", "tools:execute"), gateway=doc.get("gateway", "mcp"), enabled=doc.get("enabled", True), policy=doc.get("policy", {}), created_at=doc["created_at"]) for doc in docs]


@router.post("/jobs", response_model=BackgroundJobResponse)
async def enqueue_job(payload: BackgroundJobRequest, principal: EnterprisePrincipal = Depends(principal_dependency), store: PostgresStore = Depends(get_store)):
    principal.require(["runs:write"])
    doc = await JobQueueService(store).enqueue(principal=principal, job_type=payload.job_type, payload=payload.payload)
    return BackgroundJobResponse(job_id=doc["job_id"], job_type=doc["job_type"], status=doc["status"], attempts=doc["attempts"], payload=doc["payload"], created_at=doc["created_at"])


@router.get("/jobs", response_model=list[BackgroundJobResponse])
async def list_jobs(status: str | None = None, principal: EnterprisePrincipal = Depends(principal_dependency), store: PostgresStore = Depends(get_store)):
    principal.require(["runs:read"])
    docs = await JobQueueService(store).list(principal=principal, status=status)
    return [BackgroundJobResponse(job_id=doc["job_id"], job_type=doc["job_type"], status=doc["status"], attempts=doc.get("attempts", 0), payload=doc.get("payload", {}), created_at=doc["created_at"]) for doc in docs]


@router.get("/audit-logs", response_model=list[AuditLogResponse])
async def list_audit_logs(principal: EnterprisePrincipal = Depends(principal_dependency), store: PostgresStore = Depends(get_store)):
    principal.require(["audit:read"])
    docs = await store.find_many("audit_logs", {"workspace_id": principal.workspace_id}, limit=200, sort=[("created_at", DESCENDING)])
    return [AuditLogResponse(audit_id=doc.get("_id") or doc.get("id"), action=doc["action"], resource_type=doc["resource_type"], resource_id=doc.get("resource_id"), outcome=doc.get("outcome", "success"), actor_id=doc.get("actor_id"), workspace_id=doc.get("workspace_id"), created_at=doc["created_at"], metadata=doc.get("metadata", {})) for doc in docs]


@router.get("/readiness", response_model=EnterpriseReadinessResponse)
async def enterprise_readiness(principal: EnterprisePrincipal = Depends(principal_dependency), settings: Settings = Depends(get_settings)):
    principal.require(["runs:read"])
    implemented = [
        {"capability": "Multi-tenancy", "status": "implemented", "evidence": ["organisation_id", "workspace_id", "project_id", "environment_id"]},
        {"capability": "API key authentication", "status": "implemented", "evidence": ["hashed keys", "scopes", "roles", "bootstrap flow"]},
        {"capability": "RBAC", "status": "implemented", "evidence": ["owner", "admin", "developer", "operator", "auditor", "viewer"]},
        {"capability": "Provider-agnostic model gateway", "status": "implemented", "evidence": ["ModelGatewayRegistry", "local adapter"]},
        {"capability": "Tool registry", "status": "implemented", "evidence": ["schemas", "permission scopes", "policies", "MCP-compatible gateway"]},
        {"capability": "Background job foundation", "status": "implemented", "evidence": ["database-backed jobs", "leases-ready structure", "recovery job types"]},
        {"capability": "Audit logs", "status": "implemented", "evidence": ["enterprise audit endpoint", "tenant-scoped audit records"]},
        {"capability": "Durable runtime state", "status": "implemented", "evidence": ["PostgreSQL JSONB", "tenant-aware indexes", "checkpoints", "tool traces"]},
    ]
    remaining = [
        "SSO/SAML/OIDC integration for human users",
        "Dedicated external queue backend such as SQS, Temporal, Celery, or BullMQ for high-scale workloads",
        "Full OpenTelemetry exporter wiring to customer observability stacks",
        "Formal Alembic migration chain for managed production upgrades",
    ]
    return EnterpriseReadinessResponse(
        readiness_score="enterprise-foundation-v1",
        verdict="TraceMemory is now structured as an enterprise-adoption platform foundation rather than only a hackathon demo.",
        implemented_capabilities=implemented,
        remaining_hardening=remaining,
        enterprise_architecture={
            "runtime": "TraceMemory Runtime API + Continuity Engine",
            "model_gateway_layer": ["openai-compatible", "openrouter", "google", "local", "adapter-ready: bedrock-direct/azure/anthropic/self-hosted"],
            "tool_gateway_layer": ["MCP-compatible tool adapter", "internal API adapters"],
            "storage": "PostgreSQL JSONB durable runtime store",
            "tenant_context": principal.context_dict(),
            "collections": PRODUCTION_COLLECTIONS,
        },
    )
