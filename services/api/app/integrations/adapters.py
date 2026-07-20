from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx


@dataclass(frozen=True)
class ProviderRequest:
    method: str
    url: str
    headers: dict[str, str]
    json: dict[str, Any]
    auth: httpx.Auth | None = None


def build_provider_request(provider: str, credentials: dict[str, str], base_url: str | None, delivery: dict[str, Any]) -> ProviderRequest:
    target = quote(str(delivery["target_id"]), safe="")
    body = delivery["body"]
    headers = {"Content-Type": "application/json", "User-Agent": "SupportMemory-Connector/1.0"}
    if provider == "zendesk":
        headers["Authorization"] = f"Bearer {credentials['access_token']}"
        ticket: dict[str, Any] = {"comment": {"body": body, "public": bool(delivery.get("public", True))}}
        if delivery.get("status"):
            ticket["status"] = delivery["status"]
        return ProviderRequest("PUT", f"https://{credentials['subdomain']}.zendesk.com/api/v2/tickets/{target}.json", headers, {"ticket": ticket})
    if provider == "intercom":
        headers.update({"Authorization": f"Bearer {credentials['access_token']}", "Intercom-Version": "2.14"})
        author_id = delivery.get("author_id") or credentials.get("admin_id")
        if not author_id:
            raise ValueError("Intercom delivery requires author_id or configured admin_id")
        payload = {"message_type": "comment" if delivery.get("public", True) else "note", "type": "admin", "admin_id": author_id, "body": body}
        return ProviderRequest("POST", f"https://api.intercom.io/conversations/{target}/reply", headers, payload)
    if provider == "slack":
        headers["Authorization"] = f"Bearer {credentials['bot_token']}"
        payload = {"channel": target, "text": body, "unfurl_links": False, "unfurl_media": False}
        if delivery.get("metadata", {}).get("thread_ts"):
            payload["thread_ts"] = delivery["metadata"]["thread_ts"]
        return ProviderRequest("POST", "https://slack.com/api/chat.postMessage", headers, payload)
    if provider == "freshdesk":
        action = "reply" if delivery.get("public", True) else "notes"
        payload = {"body": body}
        if action == "notes":
            payload["private"] = True
        return ProviderRequest("POST", f"https://{credentials['domain']}.freshdesk.com/api/v2/tickets/{target}/{action}", headers, payload, httpx.BasicAuth(credentials["api_key"], "X"))
    if not base_url:
        raise ValueError("REST integration requires base_url")
    headers.update({"Authorization": f"Bearer {credentials['bearer_token']}", "Idempotency-Key": delivery["idempotency_key"]})
    return ProviderRequest("POST", base_url, headers, {"event": "supportmemory.delivery", "target_id": delivery["target_id"], "body": body, "public": delivery.get("public", True), "status": delivery.get("status"), "metadata": delivery.get("metadata") or {}})


def provider_reference(provider: str, payload: dict[str, Any]) -> str | None:
    if provider == "zendesk":
        return str((payload.get("audit") or {}).get("id") or (payload.get("ticket") or {}).get("id") or "") or None
    if provider == "intercom":
        return str(payload.get("id") or (payload.get("conversation") or {}).get("id") or "") or None
    if provider == "slack":
        return str(payload.get("ts") or "") or None
    if provider == "freshdesk":
        return str(payload.get("id") or "") or None
    return str(payload.get("id") or payload.get("delivery_id") or "") or None
