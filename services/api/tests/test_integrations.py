from cryptography.fernet import Fernet
import hashlib
import hmac
import json
import time
import httpx
import pytest

from app.config import Settings
from app.integrations.schemas import IntegrationCreateRequest, IntegrationUpdateRequest
from app.integrations.processor import IntegrationEventProcessor
from app.integrations.adapters import build_provider_request
from app.integrations.schemas import DeliveryCreateRequest
from app.integrations.service import IntegrationService
from app.integrations.vault import IntegrationCredentialVault
from app.integrations.webhooks import WebhookService, WebhookVerificationError
from app.integrations.oauth import OAuthService
from app.integrations.delivery_processor import DeliveryProcessor
from app.integrations.schemas import OAuthStartRequest
from app.main import validate_production_settings
from app.security import EnterprisePrincipal, scopes_for_role


class Store:
    def __init__(self):
        self.rows = {}

    async def insert_one(self, collection, doc):
        self.rows.setdefault(collection, []).append(dict(doc))
        return doc

    async def insert_if_absent(self, collection, doc):
        rows = self.rows.setdefault(collection, [])
        conflict = next((row for row in rows if row.get("_id") == doc.get("_id") or (
            collection == "integration_events" and row.get("integration_id") == doc.get("integration_id") and row.get("external_event_id") == doc.get("external_event_id")
        ) or (
            collection == "integration_deliveries" and row.get("direction") == "outbound" and row.get("integration_id") == doc.get("integration_id") and row.get("idempotency_key") == doc.get("idempotency_key")
        )), None)
        if conflict:
            return False
        rows.append(dict(doc))
        return True

    async def find_many(self, collection, query=None, limit=100, **kwargs):
        query = query or {}
        return [row for row in self.rows.get(collection, []) if all(row.get(k) == v for k, v in query.items())][:limit]

    async def find_one_by(self, collection, query):
        return next(iter(await self.find_many(collection, query, limit=1)), None)

    async def update_one(self, collection, query, update):
        row = await self.find_one_by(collection, query)
        if row:
            row.update(update.get("$set", update))

    async def upsert_one(self, collection, query, update):
        row = await self.find_one_by(collection, query)
        if row:
            row.update(update)
        else:
            await self.insert_one(collection, update)

    async def lease_integration_event(self, worker_id, lease_seconds=60):
        row = next((item for item in self.rows.get("integration_events", []) if item.get("status") in {"queued", "retrying"}), None)
        if row:
            row.update({"status": "processing", "lease_owner": worker_id})
        return dict(row) if row else None

    async def lease_integration_delivery(self, worker_id, lease_seconds=60):
        row = next((item for item in self.rows.get("integration_deliveries", []) if item.get("direction") == "outbound" and item.get("status") in {"queued", "retrying"}), None)
        if row:
            row.update({"status": "processing", "lease_owner": worker_id})
        return dict(row) if row else None

    async def delete_many(self, collection, query):
        before = len(self.rows.get(collection, []))
        self.rows[collection] = [row for row in self.rows.get(collection, []) if not all(row.get(k) == v for k, v in query.items())]
        return before - len(self.rows[collection])


def principal(org="org_a", workspace="wrk_a"):
    return EnterprisePrincipal(org, workspace, "prj_a", "prod", "actor", "admin", {"admin:manage"})


def test_credential_vault_encrypts_and_rejects_missing_key():
    key = Fernet.generate_key().decode()
    vault = IntegrationCredentialVault(Settings(INTEGRATION_ENCRYPTION_KEY=key))
    ciphertext = vault.encrypt({"access_token": "secret"})
    assert "secret" not in ciphertext
    assert vault.decrypt(ciphertext) == {"access_token": "secret"}
    with pytest.raises(RuntimeError, match="INTEGRATION_ENCRYPTION_KEY"):
        IntegrationCredentialVault(Settings(INTEGRATION_ENCRYPTION_KEY=None)).encrypt({"token": "x"})


@pytest.mark.asyncio
async def test_integrations_are_tenant_scoped_and_never_return_secrets():
    store = Store()
    vault = IntegrationCredentialVault(Settings(INTEGRATION_ENCRYPTION_KEY=Fernet.generate_key().decode()))
    service = IntegrationService(store, vault)
    created = await service.create(IntegrationCreateRequest(provider="zendesk", name="Zendesk", credentials={"access_token": "live-token", "subdomain": "acme", "webhook_signing_secret": "hook-secret"}), principal())
    assert created.credential_fields == ["access_token", "subdomain", "webhook_signing_secret"]
    assert not hasattr(created, "credentials")
    assert len(await service.list(principal())) == 1
    assert await service.list(principal("org_b", "wrk_b")) == []
    stored = store.rows["integrations"][0]
    assert "live-token" not in str(stored)


@pytest.mark.asyncio
async def test_required_provider_credentials_are_enforced():
    service = IntegrationService(Store(), IntegrationCredentialVault(Settings(INTEGRATION_ENCRYPTION_KEY=Fernet.generate_key().decode())))
    with pytest.raises(ValueError, match="signing_secret"):
        await service.create(IntegrationCreateRequest(provider="slack", name="Slack", credentials={"bot_token": "x"}), principal())
    with pytest.raises(ValueError, match="cannot be empty"):
        await service.create(IntegrationCreateRequest(provider="slack", name="Slack", credentials={"bot_token": "", "signing_secret": "x"}), principal())
    with pytest.raises(ValueError, match="not a URL"):
        await service.create(IntegrationCreateRequest(provider="freshdesk", name="Freshdesk", credentials={"api_key": "x", "domain": "https://acme.freshdesk.com", "webhook_secret": "x"}), principal())


@pytest.mark.asyncio
async def test_slack_webhook_is_verified_tenant_scoped_and_idempotent():
    store = Store()
    vault = IntegrationCredentialVault(Settings(INTEGRATION_ENCRYPTION_KEY=Fernet.generate_key().decode()))
    integration_service = IntegrationService(store, vault)
    integration = await integration_service.create(IntegrationCreateRequest(provider="slack", name="Slack", credentials={"bot_token": "xoxb-live", "signing_secret": "sign-me"}), principal())
    body = json.dumps({"event_id": "Ev123", "type": "event_callback", "event": {"type": "message", "text": "help"}}, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    signature = "v0=" + hmac.new(b"sign-me", b"v0:" + timestamp.encode() + b":" + body, hashlib.sha256).hexdigest()
    service = WebhookService(store, vault)
    first_id, duplicate, immediate = await service.receive("slack", integration.integration_id, {"x-slack-request-timestamp": timestamp, "x-slack-signature": signature}, body)
    assert not duplicate and immediate is None
    event = store.rows["integration_events"][0]
    assert event["organisation_id"] == "org_a" and event["workspace_id"] == "wrk_a"
    assert any(row["action"] == "integration.event.accepted" for row in store.rows["audit_logs"])
    second_id, duplicate, _ = await service.receive("slack", integration.integration_id, {"x-slack-request-timestamp": timestamp, "x-slack-signature": signature}, body)
    assert duplicate and second_id == first_id and len(store.rows["integration_events"]) == 1


@pytest.mark.asyncio
async def test_webhook_rejects_bad_signature_and_replay():
    store = Store()
    vault = IntegrationCredentialVault(Settings(INTEGRATION_ENCRYPTION_KEY=Fernet.generate_key().decode()))
    integration = await IntegrationService(store, vault).create(IntegrationCreateRequest(provider="slack", name="Slack", credentials={"bot_token": "x", "signing_secret": "secret"}), principal())
    service = WebhookService(store, vault)
    with pytest.raises(WebhookVerificationError, match="replay window"):
        await service.receive("slack", integration.integration_id, {"x-slack-request-timestamp": "1", "x-slack-signature": "v0=bad"}, b"{}")


@pytest.mark.asyncio
async def test_event_processor_creates_real_conversation_and_mapping():
    store = Store()
    event = {
        "_id": "evt_1", "event_id": "evt_1", "integration_id": "int_1", "provider": "zendesk",
        "organisation_id": "org_a", "workspace_id": "wrk_a", "project_id": "prj_a",
        "external_event_id": "zd-event-1", "event_type": "ticket.comment_created", "status": "queued",
        "attempt_count": 0, "payload": {"ticket_id": "42", "requester_id": "9", "subject": "Cannot sign in", "body": "Login returns 403"},
    }
    await store.insert_one("integration_events", event)
    result = await IntegrationEventProcessor(store, "worker-1").process_next()
    assert result["status"] == "completed"
    conversation = store.rows["user_conversations"][0]
    assert conversation["metadata"]["ticket_id"] == "42"
    assert conversation["messages"][0]["content"] == "Login returns 403"
    assert store.rows["integration_deliveries"][0]["external_thread_id"] == "42"
    assert store.rows["audit_logs"][0]["action"] == "integration.event.completed"


def test_vendor_delivery_requests_match_provider_contracts():
    delivery = {"target_id": "42", "body": "Resolved", "public": True, "status": "solved", "idempotency_key": "idem-12345678", "metadata": {}}
    zendesk = build_provider_request("zendesk", {"subdomain": "acme", "access_token": "token"}, None, delivery)
    assert zendesk.method == "PUT" and zendesk.url.endswith("/tickets/42.json")
    assert zendesk.json["ticket"]["comment"] == {"body": "Resolved", "public": True}
    slack = build_provider_request("slack", {"bot_token": "xoxb"}, None, delivery)
    assert slack.url == "https://slack.com/api/chat.postMessage" and slack.json["channel"] == "42"
    intercom = build_provider_request("intercom", {"access_token": "token", "admin_id": "7"}, None, delivery)
    assert intercom.url.endswith("/conversations/42/reply") and intercom.json["admin_id"] == "7"
    freshdesk = build_provider_request("freshdesk", {"domain": "acme", "api_key": "key"}, None, delivery)
    assert freshdesk.url.endswith("/tickets/42/reply") and freshdesk.auth is not None


def test_slack_event_is_normalized_for_memory_ingestion():
    event = WebhookService.normalize("slack", {
        "event_id": "Ev123", "type": "event_callback",
        "event": {"type": "message", "channel": "C123", "user": "U123", "text": "I need help", "ts": "1710000000.100"},
    }, {})
    assert event.external_event_id == "Ev123"
    assert event.payload == {
        "ticket_id": "1710000000.100", "user_id": "U123", "body": "I need help",
        "subject": "Slack conversation in C123", "channel": "C123", "message_ts": "1710000000.100",
    }


def test_intercom_event_is_normalized_for_memory_ingestion():
    event = WebhookService.normalize("intercom", {
        "id": "notif-1", "topic": "conversation.user.replied",
        "data": {"item": {"id": "conv-9", "source": {"body": "Original", "author": {"id": "contact-1"}},
                            "conversation_parts": {"conversation_parts": [{"body": "Latest reply", "author": {"id": "contact-1"}}]}}},
    }, {})
    assert event.external_event_id == "notif-1"
    assert event.payload["ticket_id"] == "conv-9"
    assert event.payload["user_id"] == "contact-1"
    assert event.payload["body"] == "Latest reply"


@pytest.mark.asyncio
async def test_slack_bot_events_are_acknowledged_without_feedback_loop():
    store = Store()
    vault = IntegrationCredentialVault(Settings(INTEGRATION_ENCRYPTION_KEY=Fernet.generate_key().decode()))
    integration = await IntegrationService(store, vault).create(IntegrationCreateRequest(provider="slack", name="Slack", credentials={"bot_token": "x", "signing_secret": "sign-me"}), principal())
    body = json.dumps({"event_id": "EvBot", "type": "event_callback", "event": {"type": "message", "bot_id": "B123", "text": "Automated"}}, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    signature = "v0=" + hmac.new(b"sign-me", b"v0:" + timestamp.encode() + b":" + body, hashlib.sha256).hexdigest()
    event_id, duplicate, immediate = await WebhookService(store, vault).receive("slack", integration.integration_id, {"x-slack-request-timestamp": timestamp, "x-slack-signature": signature}, body)
    assert event_id == "ignored" and not duplicate and immediate == {"accepted": True, "ignored": True}
    assert "integration_events" not in store.rows


@pytest.mark.asyncio
async def test_delivery_enqueue_is_idempotent_and_tenant_scoped():
    store = Store()
    vault = IntegrationCredentialVault(Settings(INTEGRATION_ENCRYPTION_KEY=Fernet.generate_key().decode()))
    service = IntegrationService(store, vault)
    integration = await service.create(IntegrationCreateRequest(provider="rest", name="Internal", base_url="https://hooks.example.com/support", credentials={"bearer_token": "token", "webhook_secret": "secret"}), principal())
    payload = DeliveryCreateRequest(target_id="case-1", body="Ready", idempotency_key="delivery-12345")
    first = await service.enqueue_delivery(integration.integration_id, payload, principal())
    second = await service.enqueue_delivery(integration.integration_id, payload, principal())
    assert first.delivery_id == second.delivery_id
    assert len([row for row in store.rows["integration_deliveries"] if row["direction"] == "outbound"]) == 1


@pytest.mark.asyncio
async def test_connector_can_be_disabled_and_credentials_rotated_without_exposure():
    store = Store()
    vault = IntegrationCredentialVault(Settings(INTEGRATION_ENCRYPTION_KEY=Fernet.generate_key().decode()))
    service = IntegrationService(store, vault)
    created = await service.create(IntegrationCreateRequest(provider="slack", name="Slack", credentials={"bot_token": "old", "signing_secret": "sign"}), principal())
    disabled = await service.update(created.integration_id, IntegrationUpdateRequest(enabled=False), principal())
    assert disabled.status == "disabled"
    rotated = await service.update(created.integration_id, IntegrationUpdateRequest(credentials={"bot_token": "new"}), principal())
    assert rotated.status == "configured" and not hasattr(rotated, "credentials")
    stored = await store.find_one_by("integrations", {"integration_id": created.integration_id})
    assert vault.decrypt(stored["encrypted_credentials"])["bot_token"] == "new"
    assert "old" not in str(stored) and "new" not in str(stored)


@pytest.mark.asyncio
async def test_oauth_start_is_tenant_scoped_one_time_state_and_encrypts_setup():
    store = Store()
    settings = Settings(
        INTEGRATION_ENCRYPTION_KEY=Fernet.generate_key().decode(),
        ZENDESK_OAUTH_CLIENT_ID="client", ZENDESK_OAUTH_CLIENT_SECRET="secret",
        PUBLIC_API_BASE_URL="https://api.supportmemory.example",
    )
    integrations = IntegrationService(store, IntegrationCredentialVault(settings))
    oauth = OAuthService(store, settings, integrations)
    result = await oauth.start(OAuthStartRequest(provider="zendesk", name="Zendesk", subdomain="acme", webhook_signing_secret="webhook-secret"), principal())
    assert str(result.authorization_url).startswith("https://acme.zendesk.com/oauth/authorizations/new?")
    state = store.rows["integration_oauth_states"][0]
    assert state["organisation_id"] == "org_a" and state["workspace_id"] == "wrk_a"
    assert "webhook-secret" not in str(state) and "subdomain" not in state and "state" not in state


@pytest.mark.asyncio
async def test_outbound_worker_records_provider_receipt_without_secret_leakage():
    store = Store()
    vault = IntegrationCredentialVault(Settings(INTEGRATION_ENCRYPTION_KEY=Fernet.generate_key().decode()))
    service = IntegrationService(store, vault)
    integration = await service.create(IntegrationCreateRequest(provider="rest", name="API", base_url="https://hooks.example.com/support", credentials={"bearer_token": "bearer-secret", "webhook_secret": "hook-secret"}), principal())
    delivery = await service.enqueue_delivery(integration.integration_id, DeliveryCreateRequest(target_id="case-9", body="Resolution", idempotency_key="outbound-12345"), principal())
    async def handler(request: httpx.Request):
        assert request.headers["Idempotency-Key"] == "outbound-12345"
        return httpx.Response(200, json={"delivery_id": "provider-77"})
    result = await DeliveryProcessor(store, vault, "worker", httpx.MockTransport(handler)).process_next()
    assert result == {"delivery_id": delivery.delivery_id, "status": "delivered", "provider_reference": "provider-77"}
    stored = await store.find_one_by("integration_deliveries", {"delivery_id": delivery.delivery_id})
    assert stored["status"] == "delivered" and "bearer-secret" not in str(stored)


@pytest.mark.asyncio
async def test_outbound_worker_honours_rate_limit_retry_after():
    store = Store()
    vault = IntegrationCredentialVault(Settings(INTEGRATION_ENCRYPTION_KEY=Fernet.generate_key().decode()))
    service = IntegrationService(store, vault)
    integration = await service.create(IntegrationCreateRequest(provider="rest", name="API", base_url="https://hooks.example.com/support", credentials={"bearer_token": "token", "webhook_secret": "secret"}), principal())
    delivery = await service.enqueue_delivery(integration.integration_id, DeliveryCreateRequest(target_id="case-1", body="Wait", idempotency_key="rate-limit-123"), principal())
    transport = httpx.MockTransport(lambda request: httpx.Response(429, headers={"Retry-After": "30"}, json={"error": "rate_limited"}))
    result = await DeliveryProcessor(store, vault, "worker", transport).process_next()
    assert result["status"] == "retrying" and result["attempt"] == 1
    stored = await store.find_one_by("integration_deliveries", {"delivery_id": delivery.delivery_id})
    assert stored["status"] == "retrying" and stored["attempt_count"] == 1


@pytest.mark.asyncio
async def test_production_rest_connector_requires_destination_allowlist():
    store = Store()
    settings = Settings(INTEGRATION_ENCRYPTION_KEY=Fernet.generate_key().decode(), ENVIRONMENT="production", INTEGRATION_ALLOWED_REST_HOSTS="approved.example.com")
    service = IntegrationService(store, IntegrationCredentialVault(settings))
    with pytest.raises(ValueError, match="INTEGRATION_ALLOWED_REST_HOSTS"):
        await service.create(IntegrationCreateRequest(provider="rest", name="Blocked", base_url="https://unapproved.example.com/hook", credentials={"bearer_token": "token", "webhook_secret": "secret"}), principal())
    created = await service.create(IntegrationCreateRequest(provider="rest", name="Approved", base_url="https://approved.example.com/hook", credentials={"bearer_token": "token", "webhook_secret": "secret"}), principal())
    assert created.status == "configured"


def test_operator_can_deliver_but_cannot_manage_connector_credentials():
    scopes = scopes_for_role("operator")
    assert "integrations:read" in scopes and "integrations:deliver" in scopes
    assert "integrations:write" not in scopes


def test_production_startup_fails_closed_without_auth_and_secret_keys():
    with pytest.raises(RuntimeError, match="AUTH_REQUIRED"):
        validate_production_settings(Settings(ENVIRONMENT="production", AUTH_REQUIRED=False))
    with pytest.raises(RuntimeError, match="INTEGRATION_ENCRYPTION_KEY"):
        validate_production_settings(Settings(ENVIRONMENT="production", AUTH_REQUIRED=True, SIGNING_SECRET="secure"))
    validate_production_settings(Settings(ENVIRONMENT="production", AUTH_REQUIRED=True, SIGNING_SECRET="secure", INTEGRATION_ENCRYPTION_KEY=Fernet.generate_key().decode()))
