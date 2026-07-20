from __future__ import annotations

from typing import Any

from app.config import Settings
from app.services.gateway_types import GatewayResult


class GoogleGeminiGatewayService:
    """Google/Gemini reference gateway adapter.

    This adapter keeps TraceMemory's runtime model provider-agnostic. It is a
    lightweight enterprise integration point for Google Agent Development Kit,
    Gemini, Vertex AI, or an organisation's approved Google model gateway.
    In offline mode it returns deterministic responses with the same evidence
    shape used by live gateways, so tests and demos remain reproducible.
    """

    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return bool(self.settings.google_gemini_api_key or self.settings.google_vertex_project)

    @property
    def configured_models(self) -> dict[str, str]:
        return {
            "primary": self.settings.google_gemini_model,
            "fallback": self.settings.google_gemini_fallback_model,
            "embedding": self.settings.google_embedding_model,
        }

    async def chat(self, **kwargs: Any) -> GatewayResult:
        user = kwargs.get("user", "")
        # The live Vertex/Gemini call can be wired here without changing the
        # TraceMemory run, checkpoint, recovery, or audit model.
        return GatewayResult(
            content=(
                "TraceMemory Google reference gateway response: runtime state, checkpointing, "
                "tool evidence, fallback metadata, and audit records were preserved around "
                "a Gemini/ADK-compatible agent workflow.\n\n"
                f"Task context: {user[:500]}"
            ),
            provider="google-gemini-reference-gateway",
            model=self.settings.google_gemini_model,
            used_fallback=False,
            attempts=[],
        )

    async def embed(self, text: str) -> list[float] | None:
        return None

    def attempts_as_dicts(self, attempts):
        return [attempt.__dict__ for attempt in attempts]
