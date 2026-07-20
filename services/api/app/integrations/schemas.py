from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl

IntegrationProvider = Literal["rest", "zendesk", "intercom", "slack", "freshdesk"]


class IntegrationCreateRequest(BaseModel):
    provider: IntegrationProvider
    name: str = Field(min_length=2, max_length=120)
    base_url: HttpUrl | None = None
    credentials: dict[str, str] = Field(default_factory=dict)
    settings: dict[str, Any] = Field(default_factory=dict)


class IntegrationResponse(BaseModel):
    integration_id: str
    provider: IntegrationProvider
    name: str
    base_url: str | None = None
    status: Literal["configured", "connected", "degraded", "disabled"]
    credential_fields: list[str] = Field(default_factory=list)
    settings: dict[str, Any] = Field(default_factory=dict)
    last_checked_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime


class IntegrationUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    credentials: dict[str, str] | None = None
    settings: dict[str, Any] | None = None
    enabled: bool | None = None


class OAuthStartRequest(BaseModel):
    provider: Literal["zendesk", "intercom", "slack"]
    name: str = Field(min_length=2, max_length=120)
    subdomain: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9-]{0,62}$")
    webhook_signing_secret: str | None = Field(default=None, min_length=8, max_length=512)


class OAuthStartResponse(BaseModel):
    authorization_url: HttpUrl
    state_expires_at: datetime


class IntegrationTestResponse(BaseModel):
    integration_id: str
    connected: bool
    provider: IntegrationProvider
    checked_at: datetime
    detail: str


class DeliveryCreateRequest(BaseModel):
    target_id: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1, max_length=100_000)
    public: bool = True
    status: str | None = Field(default=None, max_length=40)
    author_id: str | None = Field(default=None, max_length=255)
    idempotency_key: str = Field(min_length=8, max_length=255)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliveryResponse(BaseModel):
    delivery_id: str
    integration_id: str
    provider: IntegrationProvider
    target_id: str
    status: Literal["queued", "processing", "retrying", "delivered", "dead_letter"]
    attempt_count: int
    provider_reference: str | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime
