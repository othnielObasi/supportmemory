# Production integrations

SupportMemory treats Zendesk, Intercom, Freshdesk, Slack, and custom APIs as systems of record or collaboration surfaces. SupportMemory remains the tenant-scoped memory, evidence, governance, and execution layer.

## Required platform configuration

Generate a Fernet key and store it only in the deployment secret manager:

```text
INTEGRATION_ENCRYPTION_KEY=<urlsafe base64 Fernet key>
SIGNING_SECRET=<independent high-entropy application signing secret>
PUBLIC_API_BASE_URL=https://api.supportmemory.example
PUBLIC_CONSOLE_URL=https://app.supportmemory.example
INTEGRATION_ALLOWED_REST_HOSTS=hooks.example.com,events.internal.example
AUTH_REQUIRED=true
```

Production startup fails if the integration encryption key is absent or the default signing secret remains configured. Do not reuse either value as a vendor credential.

The private administration page is `/integrations.html`. Stored credentials are encrypted before entering PostgreSQL and are never returned by the API.

## Zendesk

Preferred installation uses OAuth. Configure `ZENDESK_OAUTH_CLIENT_ID` and `ZENDESK_OAUTH_CLIENT_SECRET`, and register this callback:

```text
https://api.supportmemory.example/api/integrations/oauth/callback/zendesk
```

The webhook destination shown in the administration page is:

```text
https://api.supportmemory.example/api/webhooks/zendesk/<integration_id>
```

Configure Zendesk webhook signing and supply its signing secret during installation. SupportMemory verifies the Zendesk signature and timestamp before parsing the body. Ticket replies use OAuth bearer authentication and the Tickets API.

## Intercom

Configure `INTERCOM_OAUTH_CLIENT_ID` and `INTERCOM_OAUTH_CLIENT_SECRET`, with callback:

```text
https://api.supportmemory.example/api/integrations/oauth/callback/intercom
```

Subscribe the application webhook to the required conversation topics and point it to `/api/webhooks/intercom/<integration_id>`. SupportMemory validates `X-Hub-Signature`. Outbound replies require an Intercom administrator ID, supplied as connector configuration or per delivery.

## Slack

Configure `SLACK_OAUTH_CLIENT_ID`, `SLACK_OAUTH_CLIENT_SECRET`, and `SLACK_SIGNING_SECRET`, with callback:

```text
https://api.supportmemory.example/api/integrations/oauth/callback/slack
```

Point Slack Events API requests to `/api/webhooks/slack/<integration_id>`. SupportMemory verifies `X-Slack-Signature`, rejects timestamps outside five minutes, handles the URL-verification challenge, and suppresses repeated event IDs. Outbound notifications use `chat.postMessage` and require `chat:write`.

## Freshdesk

Freshdesk ticket APIs use an agent API key. Store the account domain, API key, and an independent webhook secret in the connector form. In the Freshdesk automation webhook configuration:

- use the URL `/api/webhooks/freshdesk/<integration_id>`;
- add custom header `X-SupportMemory-Webhook-Secret: <webhook_secret>`;
- send a JSON body containing a stable event or ticket identifier.

Freshdesk does not emit the same platform HMAC signature used by Slack or Zendesk. The custom secret header authenticates the sender, while stable event IDs provide replay idempotency.

## Generic REST and signed webhooks

Custom outbound destinations must use HTTPS. SupportMemory sends:

```text
Authorization: Bearer <bearer_token>
Idempotency-Key: <delivery idempotency key>
```

Inbound custom webhooks must send:

```text
X-SupportMemory-Timestamp: <unix seconds>
X-SupportMemory-Signature: sha256=<HMAC_SHA256(webhook_secret, timestamp + "." + raw_body)>
```

Timestamps outside five minutes are rejected. The raw body is authenticated before JSON parsing.

## Reliability and operations

Inbound events and outbound deliveries are acknowledged only after durable PostgreSQL storage. Workers use atomic `FOR UPDATE SKIP LOCKED` leasing. Retryable network failures, HTTP 429, and HTTP 5xx responses use bounded exponential backoff; `Retry-After` is honored. After eight attempts, records enter `dead_letter` for operator intervention.

All connector creation, changes, tests, event outcomes, and delivery outcomes create tenant-scoped audit records. Provider tokens and webhook secrets are excluded from API responses, event records, delivery records, and audit metadata.

Connector creation, OAuth installation, credential rotation, and enable/disable operations require `integrations:write` and are reserved for owners and administrators. Operators receive `integrations:deliver` for governed outbound replies without credential-management access. Read-only roles can inspect connector health through `integrations:read`.
