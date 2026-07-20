from __future__ import annotations

from datetime import timedelta
from typing import Any

import httpx

from app.db.postgres import PostgresStore
from app.integrations.adapters import build_provider_request, provider_reference
from app.integrations.vault import IntegrationCredentialVault
from app.models.schemas import utc_now
from app.security import EnterprisePrincipal, create_audit_log


class DeliveryProcessor:
    MAX_ATTEMPTS = 8

    def __init__(self, store: PostgresStore, vault: IntegrationCredentialVault, worker_id: str, transport: httpx.AsyncBaseTransport | None = None):
        self.store, self.vault, self.worker_id, self.transport = store, vault, worker_id, transport

    async def process_next(self) -> dict[str, Any] | None:
        delivery = await self.store.lease_integration_delivery(self.worker_id)
        if not delivery:
            return None
        integration = await self.store.find_one_by("integrations", {"integration_id": delivery["integration_id"], "organisation_id": delivery["organisation_id"], "workspace_id": delivery["workspace_id"]})
        if not integration or integration.get("status") == "disabled":
            return await self._fail(delivery, RuntimeError("Integration is missing or disabled"), permanent=True)
        try:
            request = build_provider_request(integration["provider"], self.vault.decrypt(integration["encrypted_credentials"]), integration.get("base_url"), delivery)
            async with httpx.AsyncClient(timeout=20, follow_redirects=False, transport=self.transport) as client:
                response = await client.request(request.method, request.url, headers=request.headers, json=request.json, auth=request.auth)
            payload = response.json() if response.content else {}
            provider_rejected = integration["provider"] == "slack" and not payload.get("ok", False)
            if response.status_code == 429 or response.status_code >= 500:
                raise RetryableDeliveryError(f"Provider returned HTTP {response.status_code}", self._retry_after(response))
            if not response.is_success or provider_rejected:
                detail = payload.get("error") if isinstance(payload, dict) else None
                return await self._fail(delivery, RuntimeError(f"Provider rejected delivery: {detail or response.status_code}"), permanent=True)
            reference = provider_reference(integration["provider"], payload if isinstance(payload, dict) else {})
            await self.store.update_one("integration_deliveries", {"delivery_id": delivery["delivery_id"]}, {"status": "delivered", "provider_reference": reference, "attempt_count": int(delivery.get("attempt_count") or 0) + 1, "last_error": None, "lease_owner": None, "lease_expires_at": None, "updated_at": utc_now()})
            await self._audit(delivery, "integration.delivery.completed", "success", {"provider_reference": reference})
            return {"delivery_id": delivery["delivery_id"], "status": "delivered", "provider_reference": reference}
        except RetryableDeliveryError as exc:
            return await self._fail(delivery, exc, retry_after=exc.retry_after)
        except (httpx.HTTPError, RuntimeError, ValueError) as exc:
            return await self._fail(delivery, exc)

    async def _fail(self, delivery: dict[str, Any], exc: Exception, *, permanent: bool = False, retry_after: int | None = None) -> dict[str, Any]:
        attempts = int(delivery.get("attempt_count") or 0) + 1
        dead = permanent or attempts >= self.MAX_ATTEMPTS
        delay = retry_after or min(3600, 5 * (2 ** attempts))
        status = "dead_letter" if dead else "retrying"
        await self.store.update_one("integration_deliveries", {"delivery_id": delivery["delivery_id"]}, {"status": status, "attempt_count": attempts, "next_attempt_at": utc_now() + timedelta(seconds=delay), "last_error": f"{type(exc).__name__}: {exc}"[:500], "lease_owner": None, "lease_expires_at": None, "updated_at": utc_now()})
        await self._audit(delivery, "integration.delivery.failed", "failure", {"attempt": attempts, "dead_letter": dead, "error_type": type(exc).__name__})
        return {"delivery_id": delivery["delivery_id"], "status": status, "attempt": attempts}

    async def _audit(self, delivery: dict[str, Any], action: str, outcome: str, metadata: dict[str, Any]) -> None:
        principal = EnterprisePrincipal(delivery["organisation_id"], delivery["workspace_id"], delivery.get("project_id") or "", "prod", self.worker_id, "service", {"admin:manage"})
        await create_audit_log(self.store, action=action, principal=principal, resource_type="integration_delivery", resource_id=delivery["delivery_id"], outcome=outcome, metadata=metadata)

    @staticmethod
    def _retry_after(response: httpx.Response) -> int | None:
        try:
            return max(1, min(3600, int(response.headers.get("retry-after", ""))))
        except ValueError:
            return None


class RetryableDeliveryError(RuntimeError):
    def __init__(self, message: str, retry_after: int | None = None):
        super().__init__(message)
        self.retry_after = retry_after
