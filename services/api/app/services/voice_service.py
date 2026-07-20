from __future__ import annotations

from typing import Any, Optional

from app.config import Settings
from app.services.language_preference_service import LanguagePreferenceService
from app.services.qwen_speech_service import QwenSpeechService


class VoiceService:
    """Qwen Cloud-only voice: TTS + ASR with self-adjusting language preference."""

    def __init__(
        self,
        settings: Settings,
        language_prefs: Optional[LanguagePreferenceService] = None,
    ):
        self.settings = settings
        self.qwen = QwenSpeechService(settings)
        self.language_prefs = language_prefs

    @property
    def enabled(self) -> bool:
        return self.qwen.enabled

    def status(self) -> dict[str, Any]:
        return {
            "provider": "qwen",
            "qwen_enabled": self.qwen.enabled,
            "qwen_tts_model": getattr(self.settings, "qwen_tts_model", "qwen3-tts-flash"),
            "qwen_asr_model": getattr(self.settings, "qwen_asr_model", "qwen3-asr-flash"),
            "qwen_tts_voice": getattr(self.settings, "qwen_tts_voice", "Cherry"),
            "multilingual": True,
            "self_adjusting_language": self.language_prefs is not None,
        }

    async def synthesize(
        self,
        text: str,
        *,
        voice_id: Optional[str] = None,
        language_type: Optional[str] = None,
        user_id: Optional[str] = None,
        auto_learn: bool = True,
    ) -> tuple[Optional[str], str, dict[str, Any]]:
        """Returns (audio_base64, message, meta)."""
        if not self.qwen.enabled:
            return None, "Qwen TTS is not configured. Set QWEN_API_KEY.", {"provider": "qwen"}

        resolved = {"language_type": language_type or self.settings.qwen_tts_language or "Auto", "source": "request_or_default"}
        if self.language_prefs is not None:
            resolved = await self.language_prefs.resolve_for_tts(
                user_id=user_id,
                explicit_language=language_type,
                text=text,
                auto_learn=auto_learn,
            )

        audio, message, meta = await self.qwen.synthesize(
            text,
            voice=voice_id,
            language_type=resolved.get("language_type"),
        )
        meta = {
            **meta,
            "mime_type": meta.get("mime_type", "audio/wav"),
            "language_source": resolved.get("source"),
            "resolved_language": resolved.get("language_type"),
            "user_id": user_id,
        }
        return audio, message, meta

    async def transcribe(
        self,
        *,
        audio_url: Optional[str] = None,
        audio_base64: Optional[str] = None,
        mime_type: str = "audio/wav",
        language: Optional[str] = None,
        user_id: Optional[str] = None,
        auto_learn: bool = True,
    ) -> tuple[Optional[str], str, dict[str, Any]]:
        if not self.qwen.enabled:
            return (
                None,
                "Qwen ASR requires QWEN_API_KEY.",
                {"provider": "qwen", "enabled": False},
            )

        resolved = {"asr_language": language, "language_type": language or "Auto", "source": "request_or_default"}
        if self.language_prefs is not None:
            resolved = await self.language_prefs.resolve_for_asr(
                user_id=user_id,
                explicit_language=language,
                auto_learn=auto_learn,
            )

        transcript, message, meta = await self.qwen.transcribe(
            audio_url=audio_url,
            audio_base64=audio_base64,
            mime_type=mime_type,
            language=resolved.get("asr_language"),
        )
        if transcript and self.language_prefs is not None and user_id and auto_learn:
            learned = await self.language_prefs.learn_from_transcript(user_id, transcript, auto_learn=True)
            if learned:
                meta["learned_preference"] = learned

        meta = {
            **meta,
            "language_source": resolved.get("source"),
            "resolved_language": resolved.get("language_type"),
            "asr_language": resolved.get("asr_language"),
            "user_id": user_id,
            "enabled": True,
        }
        return transcript, message, meta
