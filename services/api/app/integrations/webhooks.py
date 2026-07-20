from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any, Mapping

from app.db.postgres import PostgresStore
from app.integrations.vault import IntegrationCredentialVault
from app.models.schemas import new_id, stable_hash, utc_now
from app.security import EnterprisePrincipal, create_audit_log


class WebhookVerificationError(ValueError):
    pass


@dataclass(frozen=True)
class NormalizedEvent:
    external_event_id: str
    event_type: str
    payload: dict[str, Any]


class WebhookService:
    MAX_CLOCK_SKEW_SECONDS = 300

    def __init__(self, store: PostgresStore, vault: IntegrationCredentialVault):
        self.store = store
        self.vault = vault

    async def receive(self, provider: str, integration_id: str, headers: Mapping[str, str], raw_body: bytes) -> tuple[str, bool, dict[str, Any] | None]:
        integration = await self.store.find_one_by("integrations", {"integration_id": integration_id, "provider": provider})
        if not integration or integration.get("status") == "disabled":
            raise LookupError("Active integration not found")
        credentials = self.vault.decrypt(integration["encrypted_credentials"])
        self.verify(provider, headers, raw_body, credentials)
        try:
            payload = json.loads(raw_body or b"{}")
        except json.JSONDecodeError as exc:
            raise WebhookVerificationError("Webhook body must be valid JSON") from exc
        if not isinstance(payload, dict):
            raise WebhookVerificationError("Webhook body must be a JSON object")
        if provider == "slack" and payload.get("type") == "url_verification":
            return "challenge", False, {"challenge": payload.get("challenge", "")}
        if provider == "slack":
            slack_event = payload.get("event") or {}
            if slack_event.get("bot_id") or slack_event.get("subtype") == "bot_message":
                return "ignored", False, {"accepted": True, "ignored": True}
        event = self.normalize(provider, payload, headers)
        existing = await self.store.find_one_by("integration_events", {"integration_id": integration_id, "external_event_id": event.external_event_id})
        if existing:
            return existing["event_id"], True, None
        now = utc_now()
        event_id = "evt_" + hashlib.sha256(f"{integration_id}:{event.external_event_id}".encode()).hexdigest()[:32]
        doc = {
            "_id": event_id,
            "event_id": event_id,
            "integration_id": integration_id,
            "provider": provider,
            "organisation_id": integration["organisation_id"],
            "workspace_id": integration["workspace_id"],
            "project_id": integration.get("project_id"),
            "external_event_id": event.external_event_id,
            "event_type": event.event_type,
            "payload": event.payload,
            "payload_hash": stable_hash(event.payload),
            "status": "queued",
            "attempt_count": 0,
            "next_attempt_at": now,
            "created_at": now,
            "updated_at": now,
        }
        if not await self.store.insert_if_absent("integration_events", doc):
            existing = await self.store.find_one_by("integration_events", {"integration_id": integration_id, "external_event_id": event.external_event_id})
            return (existing or doc)["event_id"], True, None
        principal = EnterprisePrincipal(
            integration["organisation_id"], integration["workspace_id"], integration.get("project_id") or "",
            integration.get("environment_id") or "prod", "integration-webhook", "service", {"admin:manage"},
        )
        await create_audit_log(
            self.store, action="integration.event.accepted", principal=principal,
            resource_type="integration_event", resource_id=event_id,
            metadata={"provider": provider, "event_type": event.event_type},
        )
        return event_id, False, None

    def verify(self, provider: str, headers: Mapping[str, str], raw_body: bytes, credentials: dict[str, str]) -> None:
        lowered = {key.lower(): value for key, value in headers.items()}
        if provider == "slack":
            timestamp = self._fresh_timestamp(lowered.get("x-slack-request-timestamp"))
            expected = "v0=" + hmac.new(credentials["signing_secret"].encode(), b"v0:" + str(timestamp).encode() + b":" + raw_body, hashlib.sha256).hexdigest()
            self._compare(expected, lowered.get("x-slack-signature"))
        elif provider == "zendesk":
            timestamp = lowered.get("x-zendesk-webhook-signature-timestamp")
            self._fresh_iso_or_epoch(timestamp)
            expected = hmac.new(credentials["webhook_signing_secret"].encode(), (timestamp or "").encode() + raw_body, hashlib.sha256).hexdigest()
            self._compare(expected, lowered.get("x-zendesk-webhook-signature"))
        elif provider == "intercom":
            expected = "sha1=" + hmac.new(credentials["webhook_secret"].encode(), raw_body, hashlib.sha1).hexdigest()
            self._compare(expected, lowered.get("x-hub-signature"))
        elif provider == "freshdesk":
            # Freshdesk automation webhooks support administrator-configured custom
            # headers, but do not emit a platform HMAC signature.
            self._compare(credentials["webhook_secret"], lowered.get("x-supportmemory-webhook-secret"))
        else:
            timestamp = self._fresh_timestamp(lowered.get("x-supportmemory-timestamp"))
            secret = credentials.get("webhook_secret") or credentials.get("api_key")
            if not secret:
                raise WebhookVerificationError("Webhook secret is not configured")
            expected = "sha256=" + hmac.new(secret.encode(), str(timestamp).encode() + b"." + raw_body, hashlib.sha256).hexdigest()
            self._compare(expected, lowered.get("x-supportmemory-signature"))

    @staticmethod
    def normalize(provider: str, payload: dict[str, Any], headers: Mapping[str, str]) -> NormalizedEvent:
        if provider == "slack":
            body = payload.get("event") or {}
            external_id = payload.get("event_id")
            event_type = body.get("type") or payload.get("type") or "unknown"
            thread_id = body.get("thread_ts") or body.get("ts") or body.get("channel")
            normalized = {
                "ticket_id": thread_id,
                "user_id": body.get("user") or body.get("bot_id"),
                "body": body.get("text"),
                "subject": f"Slack conversation in {body.get('channel')}" if body.get("channel") else "Slack conversation",
                "channel": body.get("channel"),
                "message_ts": body.get("ts"),
                "thread_ts": body.get("thread_ts"),
            }
        elif provider == "intercom":
            body = payload.get("data", {}).get("item") or payload
            external_id = payload.get("id")
            event_type = payload.get("topic") or "unknown"
            source = body.get("source") if isinstance(body, dict) else {}
            source = source if isinstance(source, dict) else {}
            author = source.get("author") if isinstance(source.get("author"), dict) else {}
            parts_container = body.get("conversation_parts") if isinstance(body, dict) else {}
            parts = parts_container.get("conversation_parts", []) if isinstance(parts_container, dict) else []
            latest_part = parts[-1] if isinstance(parts, list) and parts and isinstance(parts[-1], dict) else {}
            latest_author = latest_part.get("author") if isinstance(latest_part.get("author"), dict) else {}
            normalized = {
                "ticket_id": body.get("id") if isinstance(body, dict) else None,
                "user_id": latest_author.get("id") or author.get("id"),
                "body": latest_part.get("body") or source.get("body"),
                "subject": source.get("subject") or "Intercom conversation",
            }
        elif provider == "zendesk":
            body = payload.get("detail") or payload
            external_id = payload.get("id") or payload.get("event", {}).get("id")
            event_type = payload.get("type") or payload.get("event", {}).get("type") or "unknown"
            normalized = body if isinstance(body, dict) else payload
        else:
            body = payload
            external_id = payload.get("event_id") or payload.get("id")
            event_type = payload.get("event_type") or payload.get("type") or "unknown"
            normalized = body
        external_id = str(external_id or headers.get("x-request-id") or stable_hash(payload))
        clean = {key: value for key, value in normalized.items() if value is not None}
        return NormalizedEvent(external_event_id=external_id, event_type=str(event_type), payload=clean)

    def _fresh_timestamp(self, value: str | None) -> int:
        try:
            timestamp = int(value or "")
        except ValueError as exc:
            raise WebhookVerificationError("Missing or invalid webhook timestamp") from exc
        if abs(int(time.time()) - timestamp) > self.MAX_CLOCK_SKEW_SECONDS:
            raise WebhookVerificationError("Webhook timestamp is outside the replay window")
        return timestamp

    def _fresh_iso_or_epoch(self, value: str | None) -> None:
        if not value:
            raise WebhookVerificationError("Missing webhook timestamp")
        if value.isdigit():
            self._fresh_timestamp(value)
            return
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            timestamp = parsed.astimezone(timezone.utc).timestamp()
        except ValueError as exc:
            raise WebhookVerificationError("Invalid webhook timestamp") from exc
        if abs(time.time() - timestamp) > self.MAX_CLOCK_SKEW_SECONDS:
            raise WebhookVerificationError("Webhook timestamp is outside the replay window")

    @staticmethod
    def _compare(expected: str, supplied: str | None) -> None:
        if not supplied or not hmac.compare_digest(expected, supplied):
            raise WebhookVerificationError("Webhook signature verification failed")
