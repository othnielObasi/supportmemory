from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.config import Settings
from app.services.gateway_types import GatewayResult
from app.services.google_gateway import GoogleGeminiGatewayService
from app.services.openai_compatible_gateway import OpenAICompatibleGatewayService


@dataclass
class ModelGatewayDescriptor:
    name: str
    provider: str
    enabled: bool
    models: dict[str, str]
    capabilities: list[str]


class ModelGateway(Protocol):
    @property
    def enabled(self) -> bool: ...
    @property
    def configured_models(self) -> dict[str, str]: ...
    async def chat(self, **kwargs: Any) -> GatewayResult: ...
    async def embed(self, text: str) -> list[float] | None: ...
    def attempts_as_dicts(self, attempts: Any) -> list[dict[str, Any]]: ...


class UnavailableGateway:
    def __init__(self, provider: str):
        self.provider = provider

    @property
    def enabled(self) -> bool:
        return False

    @property
    def configured_models(self) -> dict[str, str]:
        return {"primary": f"{self.provider}-not-configured"}

    async def chat(self, **kwargs: Any) -> GatewayResult:
        raise RuntimeError(f"Live model provider '{self.provider}' is not configured")

    async def embed(self, text: str) -> list[float] | None:
        return None

    def attempts_as_dicts(self, attempts):
        return []


class ModelGatewayRegistry:
    """Provider-agnostic gateway registry.

    OpenAI-compatible/local gateways are the portable defaults. Google, Bedrock, Anthropic, Azure or self-hosted gateways remain optional adapters that do not change the run/recovery model.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.openai = OpenAICompatibleGatewayService(settings, provider="openai")
        self.openrouter = OpenAICompatibleGatewayService(settings, provider="openrouter")
        self.qwen = OpenAICompatibleGatewayService(settings, provider="qwen")
        self.google = GoogleGeminiGatewayService(settings)

    def get(self, preferred: str | None = None) -> ModelGateway:
        provider = (preferred or self.settings.default_model_gateway).lower()
        if provider in {"qwen", "default"} and self.qwen.enabled:
            return self.qwen
        if provider == "openai" and self.openai.enabled:
            return self.openai
        if provider == "openrouter" and self.openrouter.enabled:
            return self.openrouter
        if provider in {"google", "gemini", "vertex"} and self.google.enabled:
            return self.google
        return UnavailableGateway(provider)

    def descriptors(self) -> list[ModelGatewayDescriptor]:
        return [
            ModelGatewayDescriptor(
                name="openai",
                provider="OpenAI-compatible API",
                enabled=self.openai.enabled,
                models=self.openai.configured_models,
                capabilities=["chat", "openai-compatible", "portable-default"],
            ),
            ModelGatewayDescriptor(
                name="openrouter",
                provider="OpenRouter / OpenAI-compatible API",
                enabled=self.openrouter.enabled,
                models=self.openrouter.configured_models,
                capabilities=["chat", "multi-model", "openai-compatible"],
            ),
            ModelGatewayDescriptor(
                name="qwen",
                provider="Qwen Cloud (Alibaba Cloud / DashScope)",
                enabled=self.qwen.enabled,
                models={**self.qwen.configured_models, "vision": self.settings.qwen_vl_model},
                capabilities=["chat", "vision", "multimodal", "primary", "openai-compatible", "alibaba-cloud"],
            ),
            ModelGatewayDescriptor(
                name="google",
                provider="Google Gemini / Vertex AI reference gateway",
                enabled=self.google.enabled,
                models=self.google.configured_models,
                capabilities=["chat", "fallback", "embedding", "adk_reference", "agent_engine_reference"],
            ),
        ]
