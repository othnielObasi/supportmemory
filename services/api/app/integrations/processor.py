from __future__ import annotations

from datetime import timedelta
from typing import Any

from app.db.postgres import PostgresStore
from app.models.schemas import new_id, utc_now
from app.security import EnterprisePrincipal, create_audit_log
from app.services.conversation_history_service import ConversationHistoryService


class IntegrationEventProcessor:
    MAX_ATTEMPTS = 8

    def __init__(self, store: PostgresStore, worker_id: str):
        self.store = store
        self.worker_id = worker_id
        self.conversations = ConversationHistoryService(store)

    async def process_next(self) -> dict[str, Any] | None:
        event = await self.store.lease_integration_event(self.worker_id)
        if not event:
            return None
        try:
            conversation_id = await self._ingest(event)
            await self.store.update_one("integration_events", {"event_id": event["event_id"]}, {
                "status": "completed", "conversation_id": conversation_id,
                "lease_owner": None, "lease_expires_at": None, "last_error": None, "updated_at": utc_now(),
            })
            await self._audit(event, "integration.event.completed", "success", {"conversation_id": conversation_id})
            return {"event_id": event["event_id"], "status": "completed", "conversation_id": conversation_id}
        except Exception as exc:
            attempts = int(event.get("attempt_count") or 0) + 1
            dead = attempts >= self.MAX_ATTEMPTS
            delay = min(3600, 2 ** attempts * 5)
            await self.store.update_one("integration_events", {"event_id": event["event_id"]}, {
                "status": "dead_letter" if dead else "retrying", "attempt_count": attempts,
                "next_attempt_at": utc_now() + timedelta(seconds=delay), "last_error": f"{type(exc).__name__}: {exc}"[:500],
                "lease_owner": None, "lease_expires_at": None, "updated_at": utc_now(),
            })
            await self._audit(event, "integration.event.failed", "failure", {"attempt": attempts, "dead_letter": dead, "error_type": type(exc).__name__})
            return {"event_id": event["event_id"], "status": "dead_letter" if dead else "retrying", "attempt": attempts}

    async def _ingest(self, event: dict[str, Any]) -> str:
        payload = event.get("payload") or {}
        provider = event["provider"]
        ticket_id = self._first(payload, "ticket_id", "conversation_id", "id") or event["external_event_id"]
        user_id = str(self._first(payload, "user_id", "contact_id", "requester_id", "author_id") or f"{provider}:{ticket_id}")
        text = self._extract_text(payload)
        if not text:
            raise ValueError("Event does not contain a supported message body")
        mapping = await self.store.find_one_by("integration_deliveries", {
            "integration_id": event["integration_id"], "external_thread_id": str(ticket_id), "direction": "inbound_mapping",
        })
        if mapping:
            conversation_id = mapping["conversation_id"]
        else:
            conversation = await self.conversations.create(
                user_id, title=str(self._first(payload, "subject", "title") or f"{provider.title()} conversation {ticket_id}"),
                channel=provider, organisation_id=event["organisation_id"], workspace_id=event["workspace_id"],
                metadata={"ticket_id": str(ticket_id), "source_system": provider, "integration_id": event["integration_id"]},
            )
            conversation_id = conversation["conversation_id"]
            await self.store.insert_one("integration_deliveries", {
                "_id": new_id("map"), "integration_id": event["integration_id"], "external_thread_id": str(ticket_id),
                "conversation_id": conversation_id, "direction": "inbound_mapping",
                "organisation_id": event["organisation_id"], "workspace_id": event["workspace_id"], "created_at": utc_now(),
            })
        await self.conversations.append_message(
            conversation_id, role="user", content=text,
            metadata={"provider": provider, "external_event_id": event["external_event_id"], "event_type": event["event_type"]},
            organisation_id=event["organisation_id"], workspace_id=event["workspace_id"],
        )
        return conversation_id

    async def _audit(self, event: dict[str, Any], action: str, outcome: str, metadata: dict[str, Any]) -> None:
        principal = EnterprisePrincipal(event["organisation_id"], event["workspace_id"], event.get("project_id") or "", "prod", self.worker_id, "service", {"admin:manage"})
        await create_audit_log(self.store, action=action, principal=principal, resource_type="integration_event", resource_id=event["event_id"], outcome=outcome, metadata=metadata)

    @staticmethod
    def _first(payload: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            if payload.get(key) is not None:
                return payload[key]
        for container in ("ticket", "conversation", "message", "author", "requester", "contact"):
            nested = payload.get(container)
            if isinstance(nested, dict):
                value = IntegrationEventProcessor._first(nested, *keys)
                if value is not None:
                    return value
        return None

    @staticmethod
    def _extract_text(payload: dict[str, Any]) -> str:
        value = IntegrationEventProcessor._first(payload, "body", "text", "body_text", "plain_body", "description", "content")
        if isinstance(value, dict):
            value = value.get("text") or value.get("body")
        return str(value or "").strip()
