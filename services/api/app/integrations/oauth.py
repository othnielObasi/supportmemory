from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

from app.config import Settings
from app.db.postgres import PostgresStore
from app.integrations.schemas import IntegrationCreateRequest, OAuthStartRequest, OAuthStartResponse
from app.integrations.service import IntegrationService
from app.models.schemas import stable_hash, utc_now
from app.security import EnterprisePrincipal, create_audit_log


class OAuthService:
    TTL_MINUTES = 10

    def __init__(self, store: PostgresStore, settings: Settings, integrations: IntegrationService):
        self.store, self.settings, self.integrations = store, settings, integrations

    def redirect_uri(self, provider: str) -> str:
        return f"{self.settings.public_api_base_url.rstrip('/')}/api/integrations/oauth/callback/{provider}"

    async def start(self, payload: OAuthStartRequest, principal: EnterprisePrincipal) -> OAuthStartResponse:
        self._require_provider_config(payload.provider)
        if payload.provider == "zendesk" and (not payload.subdomain or not payload.webhook_signing_secret):
            raise ValueError("Zendesk OAuth requires subdomain and webhook_signing_secret")
        state = secrets.token_urlsafe(32)
        state_hash = stable_hash(state)
        expires = utc_now() + timedelta(minutes=self.TTL_MINUTES)
        await self.store.insert_one("integration_oauth_states", {
            "_id": state_hash, "state_hash": state_hash, "provider": payload.provider, "name": payload.name,
            "encrypted_setup": self.integrations.vault.encrypt({key: value for key, value in {"subdomain": payload.subdomain, "webhook_signing_secret": payload.webhook_signing_secret}.items() if value}),
            **principal.context_dict(), "role": principal.role, "expires_at": expires, "created_at": utc_now(),
        })
        redirect = self.redirect_uri(payload.provider)
        if payload.provider == "slack":
            query = urlencode({"client_id": self.settings.slack_oauth_client_id, "scope": "chat:write,channels:history,groups:history", "redirect_uri": redirect, "state": state})
            url = f"https://slack.com/oauth/v2/authorize?{query}"
        elif payload.provider == "intercom":
            query = urlencode({"client_id": self.settings.intercom_oauth_client_id, "redirect_uri": redirect, "state": state})
            url = f"https://app.intercom.com/oauth?{query}"
        else:
            query = urlencode({"response_type": "code", "redirect_uri": redirect, "client_id": self.settings.zendesk_oauth_client_id, "scope": "read write", "state": state})
            url = f"https://{payload.subdomain}.zendesk.com/oauth/authorizations/new?{query}"
        await create_audit_log(self.store, action="integration.oauth.started", principal=principal, resource_type="integration_oauth", resource_id="oauth_" + stable_hash(state)[:16], metadata={"provider": payload.provider})
        return OAuthStartResponse(authorization_url=url, state_expires_at=expires)

    async def callback(self, provider: str, state: str, code: str) -> str:
        state_hash = stable_hash(state)
        record = await self.store.find_one_by("integration_oauth_states", {"state_hash": state_hash, "provider": provider})
        if not record:
            raise ValueError("OAuth state is invalid or already used")
        await self.store.delete_many("integration_oauth_states", {"state_hash": state_hash})
        expires_at = record.get("expires_at")
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        if not isinstance(expires_at, datetime):
            raise ValueError("OAuth state expiry is invalid")
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if utc_now() > expires_at:
            raise ValueError("OAuth state has expired")
        redirect = self.redirect_uri(provider)
        setup = self.integrations.vault.decrypt(record["encrypted_setup"])
        credentials = await self._exchange(provider, code, redirect, {**record, **setup})
        principal = EnterprisePrincipal(record["organisation_id"], record["workspace_id"], record["project_id"], record["environment_id"], record["actor_id"], record.get("role") or "admin", {"admin:manage"})
        integration = await self.integrations.create(IntegrationCreateRequest(provider=provider, name=record["name"], credentials=credentials), principal)
        return integration.integration_id

    async def _exchange(self, provider: str, code: str, redirect: str, record: dict) -> dict[str, str]:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            if provider == "slack":
                response = await client.post("https://slack.com/api/oauth.v2.access", data={"client_id": self.settings.slack_oauth_client_id, "client_secret": self.settings.slack_oauth_client_secret, "code": code, "redirect_uri": redirect})
                data = response.json()
                if not response.is_success or not data.get("ok"):
                    raise ValueError("Slack OAuth token exchange failed")
                return {"bot_token": data["access_token"], "signing_secret": self.settings.slack_signing_secret or ""}
            if provider == "intercom":
                response = await client.post("https://api.intercom.io/auth/eagle/token", data={"client_id": self.settings.intercom_oauth_client_id, "client_secret": self.settings.intercom_oauth_client_secret, "code": code, "redirect_uri": redirect})
                data = response.json()
                if not response.is_success or not data.get("access_token"):
                    raise ValueError("Intercom OAuth token exchange failed")
                return {"access_token": data["access_token"], "webhook_secret": self.settings.intercom_oauth_client_secret or ""}
            response = await client.post(f"https://{record['subdomain']}.zendesk.com/oauth/tokens", json={"grant_type": "authorization_code", "code": code, "client_id": self.settings.zendesk_oauth_client_id, "client_secret": self.settings.zendesk_oauth_client_secret, "redirect_uri": redirect, "scope": "read write"})
            data = response.json()
            if not response.is_success or not data.get("access_token"):
                raise ValueError("Zendesk OAuth token exchange failed")
            return {"access_token": data["access_token"], "subdomain": record["subdomain"], "webhook_signing_secret": record["webhook_signing_secret"]}

    def _require_provider_config(self, provider: str) -> None:
        configured = {
            "slack": self.settings.slack_oauth_client_id and self.settings.slack_oauth_client_secret and self.settings.slack_signing_secret,
            "intercom": self.settings.intercom_oauth_client_id and self.settings.intercom_oauth_client_secret,
            "zendesk": self.settings.zendesk_oauth_client_id and self.settings.zendesk_oauth_client_secret,
        }[provider]
        if not configured:
            raise ValueError(f"{provider.title()} OAuth application is not configured")
