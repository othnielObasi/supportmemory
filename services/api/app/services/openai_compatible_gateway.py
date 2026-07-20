from __future__ import annotations

import time
from typing import Any

import httpx

from app.config import Settings
from app.services.gateway_types import GatewayAttempt, GatewayResult


class OpenAICompatibleGatewayService:
    """OpenAI-compatible model gateway used as TraceMemory's portable default.

    It can call OpenAI or OpenRouter-compatible endpoints. If no key is configured,
    it cleanly reports disabled and the registry falls back to deterministic local.
    """

    def __init__(self, settings: Settings, *, provider: str = "openai"):
        self.settings = settings
        self.provider = provider

    @property
    def enabled(self) -> bool:
        if self.provider == "openrouter":
            return bool(self.settings.openrouter_api_key)
        if self.provider == "qwen":
            return bool(self.settings.qwen_api_key)
        return bool(self.settings.openai_api_key)

    @property
    def configured_models(self) -> dict[str, str]:
        if self.provider == "openrouter":
            return {"primary": self.settings.openrouter_model}
        if self.provider == "qwen":
            return {"primary": self.settings.qwen_model}
        return {"primary": self.settings.openai_chat_model, "embedding": self.settings.openai_embedding_model}

    async def chat(self, **kwargs: Any) -> GatewayResult:
        system = kwargs.get("system", "You are a reliable agent runtime planner.")
        user = kwargs.get("user", "")
        images = kwargs.get("images") or []
        model = kwargs.get("model") or self.configured_models["primary"]
        if images and self.provider == "qwen" and not kwargs.get("model"):
            model = self.settings.qwen_vl_model
        if self.provider == "openrouter":
            base_url = "https://openrouter.ai/api/v1"
        elif self.provider == "qwen":
            # Qwen Cloud (DashScope) OpenAI-compatible endpoint, hosted on Alibaba
            # Cloud infra. Base URL is overridable for region-specific endpoints.
            base_url = self.settings.qwen_base_url
        else:
            base_url = "https://api.openai.com/v1"
        if self.provider == "openrouter":
            api_key = self.settings.openrouter_api_key
        elif self.provider == "qwen":
            api_key = self.settings.qwen_api_key
        else:
            api_key = self.settings.openai_api_key
        started = time.perf_counter()
        if not api_key:
            return GatewayResult("", self.provider, model, False, [GatewayAttempt(model, "primary", "disabled", 0, "API key not configured")])
        user_content: Any = user
        if images:
            parts: list[dict[str, Any]] = [{"type": "text", "text": user}]
            for image in images:
                parts.append({"type": "image_url", "image_url": {"url": image}})
            user_content = parts
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            "temperature": kwargs.get("temperature", 0),
        }
        if kwargs.get("max_tokens") is not None:
            payload["max_tokens"] = kwargs.get("max_tokens")
        try:
            async with httpx.AsyncClient(timeout=self.settings.gateway_timeout_seconds) as client:
                response = await client.post(
                    f"{base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
            content = data["choices"][0]["message"]["content"]
            return GatewayResult(content, self.provider, model, False, [GatewayAttempt(model, "primary", "success", int((time.perf_counter()-started)*1000))])
        except Exception as exc:  # noqa: BLE001
            return GatewayResult("", self.provider, model, False, [GatewayAttempt(model, "primary", "failed", int((time.perf_counter()-started)*1000), str(exc)[:500])])

    async def embed(self, text: str) -> list[float] | None:
        return None

    def attempts_as_dicts(self, attempts):
        return [attempt.__dict__ for attempt in attempts]
