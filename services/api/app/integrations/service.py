from __future__ import annotations

from typing import Any
import ipaddress
import re

import httpx

from app.db.postgres import PostgresStore
from app.integrations.schemas import DeliveryCreateRequest, DeliveryResponse, IntegrationCreateRequest, IntegrationResponse, IntegrationTestResponse, IntegrationUpdateRequest
from app.integrations.vault import IntegrationCredentialVault
from app.models.schemas import new_id, stable_hash, utc_now
from app.security import EnterprisePrincipal, create_audit_log


REQUIRED_CREDENTIALS: dict[str, set[str]] = {
    "rest": {"bearer_token", "webhook_secret"},
    "zendesk": {"access_token", "subdomain", "webhook_signing_secret"},
    "intercom": {"access_token", "webhook_secret"},
    "slack": {"bot_token", "signing_secret"},
    "freshdesk": {"api_key", "domain", "webhook_secret"},
}


class IntegrationService:
    def __init__(self, store: PostgresStore, vault: IntegrationCredentialVault):
        self.store = store
        self.vault = vault

    async def create(self, payload: IntegrationCreateRequest, principal: EnterprisePrincipal) -> IntegrationResponse:
        required = REQUIRED_CREDENTIALS[payload.provider]
        missing = sorted(required.difference(payload.credentials))
        if missing:
            raise ValueError(f"Missing credential fields: {', '.join(missing)}")
        self._validate_credentials(payload.provider, payload.credentials)
        if payload.base_url and payload.base_url.scheme != "https":
            raise ValueError("Connector base_url must use HTTPS")
        if payload.provider == "rest":
            host = (payload.base_url.host if payload.base_url else "").lower()
            if not host:
                raise ValueError("REST integration requires base_url")
            if host == "localhost" or host.endswith(".localhost"):
                raise ValueError("Connector base_url cannot target localhost")
            try:
                if ipaddress.ip_address(host).is_private or ipaddress.ip_address(host).is_loopback or ipaddress.ip_address(host).is_link_local:
                    raise ValueError("Connector base_url cannot target a private network address")
            except ValueError as exc:
                if "cannot target" in str(exc):
                    raise
            allowed = {item.strip().lower() for item in self.vault.settings.integration_allowed_rest_hosts.split(",") if item.strip()}
            if self.vault.settings.environment == "production" and host not in allowed:
                raise ValueError("REST destination host is not in INTEGRATION_ALLOWED_REST_HOSTS")
        now = utc_now()
        integration_id = new_id("int")
        doc = {
            "_id": integration_id,
            "integration_id": integration_id,
            **principal.context_dict(),
            "provider": payload.provider,
            "name": payload.name,
            "base_url": str(payload.base_url) if payload.base_url else None,
            "status": "configured",
            "credential_fields": sorted(payload.credentials),
            "encrypted_credentials": self.vault.encrypt(payload.credentials),
            "settings": payload.settings,
            "last_checked_at": None,
            "last_error": None,
            "created_at": now,
            "updated_at": now,
        }
        await self.store.insert_one("integrations", doc)
        await create_audit_log(self.store, action="integration.create", principal=principal, resource_type="integration", resource_id=integration_id, metadata={"provider": payload.provider})
        return self._response(doc)

    async def list(self, principal: EnterprisePrincipal) -> list[IntegrationResponse]:
        docs = await self.store.find_many("integrations", {"organisation_id": principal.organisation_id, "workspace_id": principal.workspace_id}, limit=100)
        return [self._response(doc) for doc in docs]

    async def update(self, integration_id: str, payload: IntegrationUpdateRequest, principal: EnterprisePrincipal) -> IntegrationResponse:
        doc = await self.get_doc(integration_id, principal)
        if not doc:
            raise LookupError("Integration not found")
        changes: dict[str, Any] = {"updated_at": utc_now()}
        if payload.name is not None:
            changes["name"] = payload.name
        if payload.settings is not None:
            changes["settings"] = payload.settings
        if payload.enabled is not None:
            changes["status"] = "configured" if payload.enabled else "disabled"
        if payload.credentials is not None:
            current = self.vault.decrypt(doc["encrypted_credentials"])
            current.update(payload.credentials)
            missing = sorted(REQUIRED_CREDENTIALS[doc["provider"]].difference(current))
            if missing:
                raise ValueError(f"Missing credential fields: {', '.join(missing)}")
            self._validate_credentials(doc["provider"], current)
            changes["encrypted_credentials"] = self.vault.encrypt(current)
            changes["credential_fields"] = sorted(current)
            changes["status"] = "configured"
            changes["last_checked_at"] = None
            changes["last_error"] = None
        await self.store.update_one("integrations", {"integration_id": integration_id, "organisation_id": principal.organisation_id, "workspace_id": principal.workspace_id}, changes)
        await create_audit_log(self.store, action="integration.update", principal=principal, resource_type="integration", resource_id=integration_id, metadata={"rotated_credentials": payload.credentials is not None, "enabled": payload.enabled})
        return self._response({**doc, **changes})

    async def get_doc(self, integration_id: str, principal: EnterprisePrincipal) -> dict[str, Any] | None:
        return await self.store.find_one_by("integrations", {"integration_id": integration_id, "organisation_id": principal.organisation_id, "workspace_id": principal.workspace_id})

    async def test(self, integration_id: str, principal: EnterprisePrincipal) -> IntegrationTestResponse:
        doc = await self.get_doc(integration_id, principal)
        if not doc:
            raise LookupError("Integration not found")
        if doc.get("status") == "disabled":
            raise ValueError("Integration is disabled")
        credentials = self.vault.decrypt(doc["encrypted_credentials"])
        connected, detail = await self._probe(doc, credentials)
        checked_at = utc_now()
        await self.store.update_one("integrations", {"integration_id": integration_id, "organisation_id": principal.organisation_id, "workspace_id": principal.workspace_id}, {"status": "connected" if connected else "degraded", "last_checked_at": checked_at, "last_error": None if connected else detail, "updated_at": checked_at})
        await create_audit_log(self.store, action="integration.test", principal=principal, resource_type="integration", resource_id=integration_id, outcome="success" if connected else "failure", metadata={"provider": doc["provider"]})
        return IntegrationTestResponse(integration_id=integration_id, connected=connected, provider=doc["provider"], checked_at=checked_at, detail=detail)

    async def enqueue_delivery(self, integration_id: str, payload: DeliveryCreateRequest, principal: EnterprisePrincipal) -> DeliveryResponse:
        integration = await self.get_doc(integration_id, principal)
        if not integration:
            raise LookupError("Integration not found")
        existing = await self.store.find_one_by("integration_deliveries", {
            "integration_id": integration_id, "idempotency_key": payload.idempotency_key, "direction": "outbound",
        })
        if existing:
            return self._delivery_response(existing)
        now = utc_now()
        delivery_id = "del_" + stable_hash({"integration_id": integration_id, "idempotency_key": payload.idempotency_key})[:32]
        doc = {
            "_id": delivery_id, "delivery_id": delivery_id, "integration_id": integration_id,
            **principal.context_dict(), "provider": integration["provider"], "direction": "outbound",
            "target_id": payload.target_id, "body": payload.body, "public": payload.public,
            "requested_status": payload.status, "author_id": payload.author_id,
            "idempotency_key": payload.idempotency_key, "metadata": payload.metadata,
            "status": "queued", "attempt_count": 0, "next_attempt_at": now,
            "provider_reference": None, "last_error": None, "created_at": now, "updated_at": now,
        }
        if not await self.store.insert_if_absent("integration_deliveries", doc):
            existing = await self.store.find_one_by("integration_deliveries", {
                "integration_id": integration_id, "idempotency_key": payload.idempotency_key, "direction": "outbound",
            })
            if existing:
                return self._delivery_response(existing)
            raise RuntimeError("Delivery idempotency conflict could not be resolved")
        await create_audit_log(self.store, action="integration.delivery.queued", principal=principal, resource_type="integration_delivery", resource_id=delivery_id, metadata={"provider": integration["provider"], "target_id": payload.target_id})
        return self._delivery_response(doc)

    async def list_deliveries(self, integration_id: str, principal: EnterprisePrincipal) -> list[DeliveryResponse]:
        if not await self.get_doc(integration_id, principal):
            raise LookupError("Integration not found")
        docs = await self.store.find_many("integration_deliveries", {"integration_id": integration_id, "direction": "outbound", "organisation_id": principal.organisation_id, "workspace_id": principal.workspace_id}, limit=100)
        return [self._delivery_response(doc) for doc in docs]

    async def _probe(self, doc: dict[str, Any], credentials: dict[str, str]) -> tuple[bool, str]:
        provider = doc["provider"]
        if provider == "zendesk": url, headers = f"https://{credentials['subdomain']}.zendesk.com/api/v2/users/me.json", {"Authorization": f"Bearer {credentials['access_token']}"}
        elif provider == "intercom": url, headers = "https://api.intercom.io/me", {"Authorization": f"Bearer {credentials['access_token']}", "Intercom-Version": "2.14"}
        elif provider == "slack": url, headers = "https://slack.com/api/auth.test", {"Authorization": f"Bearer {credentials['bot_token']}"}
        elif provider == "freshdesk": url, headers = f"https://{credentials['domain']}.freshdesk.com/api/v2/agents/me", {}
        else:
            if not doc.get("base_url"):
                return False, "REST integration requires base_url"
            url, headers = doc["base_url"], {"Authorization": f"Bearer {credentials['bearer_token']}"}
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
                response = await client.get(url, headers=headers, auth=httpx.BasicAuth(credentials["api_key"], "X") if provider == "freshdesk" else None)
            if response.is_success:
                if provider == "slack" and not response.json().get("ok"):
                    return False, "Slack rejected the credentials"
                return True, "Connection verified"
            return False, f"Provider returned HTTP {response.status_code}"
        except httpx.HTTPError as exc:
            return False, f"Provider connection failed: {type(exc).__name__}"

    @staticmethod
    def _response(doc: dict[str, Any]) -> IntegrationResponse:
        return IntegrationResponse(**{key: doc.get(key) for key in IntegrationResponse.model_fields})

    @staticmethod
    def _delivery_response(doc: dict[str, Any]) -> DeliveryResponse:
        values = {key: doc.get(key) for key in DeliveryResponse.model_fields}
        values["status"] = doc.get("status", "queued")
        return DeliveryResponse(**values)

    @staticmethod
    def _validate_credentials(provider: str, credentials: dict[str, str]) -> None:
        required = REQUIRED_CREDENTIALS[provider]
        empty = sorted(key for key in required if not isinstance(credentials.get(key), str) or not credentials[key].strip())
        if empty:
            raise ValueError(f"Credential fields cannot be empty: {', '.join(empty)}")
        oversized = sorted(key for key, value in credentials.items() if not isinstance(value, str) or len(value) > 4096)
        if oversized:
            raise ValueError(f"Credential fields are invalid: {', '.join(oversized)}")
        tenant_key = "subdomain" if provider == "zendesk" else "domain" if provider == "freshdesk" else None
        if tenant_key and not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", credentials[tenant_key]):
            raise ValueError(f"{tenant_key} must be a valid provider account identifier, not a URL")
