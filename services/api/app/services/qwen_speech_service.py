from __future__ import annotations

import base64
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from app.config import Settings


class QwenSpeechService:
    """Qwen Cloud speech: TTS (Qwen-TTS) + ASR (Qwen-ASR) via DashScope.

    Uses the same QWEN_API_KEY as chat/vision. Falls back cleanly when unset.
    """

    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return bool(self.settings.qwen_api_key)

    @property
    def api_key(self) -> str:
        return self.settings.qwen_api_key or ""

    @property
    def dashscope_api_base(self) -> str:
        """Native DashScope API root, e.g. https://dashscope-intl.aliyuncs.com/api/v1"""
        configured = getattr(self.settings, "qwen_dashscope_api_base", None)
        if configured:
            return str(configured).rstrip("/")
        base = (self.settings.qwen_base_url or "").rstrip("/")
        # https://dashscope-intl.aliyuncs.com/compatible-mode/v1 → …/api/v1
        if "/compatible-mode/" in base:
            host = base.split("/compatible-mode/")[0]
            return f"{host}/api/v1"
        if base.endswith("/api/v1"):
            return base
        parsed = urlparse(base)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}/api/v1"
        return "https://dashscope-intl.aliyuncs.com/api/v1"

    @property
    def openai_compatible_base(self) -> str:
        return (self.settings.qwen_base_url or "https://dashscope-intl.aliyuncs.com/compatible-mode/v1").rstrip("/")

    async def synthesize(
        self,
        text: str,
        *,
        voice: Optional[str] = None,
        language_type: Optional[str] = None,
    ) -> tuple[Optional[str], str, dict[str, Any]]:
        """Text → speech. Returns (audio_base64, message, meta)."""
        if not self.enabled:
            return None, "Qwen TTS is not configured. Set QWEN_API_KEY.", {}

        model = getattr(self.settings, "qwen_tts_model", None) or "qwen3-tts-flash"
        selected_voice = voice or getattr(self.settings, "qwen_tts_voice", None) or "Cherry"
        lang = language_type or getattr(self.settings, "qwen_tts_language", None) or "Auto"
        url = f"{self.dashscope_api_base}/services/aigc/multimodal-generation/generation"
        payload = {
            "model": model,
            "input": {
                "text": text[:2000],
                "voice": selected_voice,
                "language_type": lang,
            },
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=self.settings.gateway_timeout_seconds) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                audio_url = (
                    (data.get("output") or {}).get("audio", {}) or {}
                ).get("url")
                if not audio_url:
                    return None, f"Qwen TTS returned no audio URL: {str(data)[:300]}", {
                        "provider": "qwen",
                        "model": model,
                        "voice": selected_voice,
                    }
                audio_resp = await client.get(audio_url)
                audio_resp.raise_for_status()
                audio_b64 = base64.b64encode(audio_resp.content).decode("ascii")
            return (
                audio_b64,
                "Voice summary generated via Qwen-TTS.",
                {
                    "provider": "qwen",
                    "model": model,
                    "voice": selected_voice,
                    "language_type": lang,
                    "audio_url": audio_url,
                    "mime_type": "audio/wav",
                },
            )
        except Exception as exc:  # noqa: BLE001
            return None, f"Qwen TTS failed: {str(exc)[:400]}", {
                "provider": "qwen",
                "model": model,
                "voice": selected_voice,
                "error": str(exc)[:400],
            }

    async def transcribe(
        self,
        *,
        audio_url: Optional[str] = None,
        audio_base64: Optional[str] = None,
        mime_type: str = "audio/wav",
        language: Optional[str] = None,
    ) -> tuple[Optional[str], str, dict[str, Any]]:
        """Speech → text via Qwen-ASR (OpenAI-compatible chat completions)."""
        if not self.enabled:
            return None, "Qwen ASR is not configured. Set QWEN_API_KEY.", {}

        if not audio_url and not audio_base64:
            return None, "Provide audio_url or audio_base64.", {}

        model = getattr(self.settings, "qwen_asr_model", None) or "qwen3-asr-flash"
        if audio_url:
            audio_data = audio_url
        else:
            raw = audio_base64 or ""
            if raw.startswith("data:"):
                audio_data = raw
            else:
                audio_data = f"data:{mime_type};base64,{raw}"

        asr_options: dict[str, Any] = {"enable_itn": False}
        if language:
            asr_options["language"] = language

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": {"data": audio_data},
                        }
                    ],
                }
            ],
            "asr_options": asr_options,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.openai_compatible_base}/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=self.settings.gateway_timeout_seconds) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
            content = (
                (((data.get("choices") or [{}])[0].get("message") or {}).get("content")) or ""
            ).strip()
            if not content:
                return None, f"Qwen ASR returned empty transcript: {str(data)[:300]}", {
                    "provider": "qwen",
                    "model": model,
                }
            return content, "Transcript generated via Qwen-ASR.", {
                "provider": "qwen",
                "model": model,
                "language": language,
            }
        except Exception as exc:  # noqa: BLE001
            return None, f"Qwen ASR failed: {str(exc)[:400]}", {
                "provider": "qwen",
                "model": model,
                "error": str(exc)[:400],
            }
