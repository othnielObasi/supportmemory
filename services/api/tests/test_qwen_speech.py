import pytest

from app.config import Settings
from app.services.language_preference_service import LanguagePreferenceService
from app.services.qwen_speech_service import QwenSpeechService
from app.services.voice_service import VoiceService


class MemoryStore:
    def __init__(self):
        self.data = {}

    async def find_one_by(self, collection, query=None, sort=None):
        rows = list(self.data.get(collection, []))
        query = query or {}
        for row in rows:
            if all(str(row.get(k)) == str(v) for k, v in query.items()):
                return row
        return None

    async def upsert_one(self, collection, query, update):
        existing = await self.find_one_by(collection, query)
        if existing:
            existing.update(update)
            return
        self.data.setdefault(collection, []).append(update)


def test_qwen_speech_disabled_without_key():
    settings = Settings(QWEN_API_KEY=None)
    speech = QwenSpeechService(settings)
    assert speech.enabled is False


def test_dashscope_api_base_derived_from_compatible_url():
    settings = Settings(
        QWEN_API_KEY="k",
        QWEN_BASE_URL="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    )
    speech = QwenSpeechService(settings)
    assert speech.dashscope_api_base == "https://dashscope-intl.aliyuncs.com/api/v1"


@pytest.mark.asyncio
async def test_tts_reports_disabled_without_key():
    settings = Settings(QWEN_API_KEY=None)
    voice = VoiceService(settings)
    audio, message, meta = await voice.synthesize("Hello SupportMemory")
    assert audio is None
    assert voice.enabled is False
    assert "QWEN_API_KEY" in message


@pytest.mark.asyncio
async def test_asr_requires_qwen_key():
    settings = Settings(QWEN_API_KEY=None)
    voice = VoiceService(settings)
    text, message, meta = await voice.transcribe(audio_url="https://example.com/a.mp3")
    assert text is None
    assert "QWEN_API_KEY" in message


def test_voice_status_is_qwen_only():
    settings = Settings(QWEN_API_KEY="k")
    status = VoiceService(settings).status()
    assert status["provider"] == "qwen"
    assert status["qwen_enabled"] is True
    assert "elevenlabs" not in status


def test_detect_chinese_and_english():
    svc = LanguagePreferenceService(MemoryStore())
    assert svc.detect_language("请帮我处理退款问题")["language_type"] == "Chinese"
    assert svc.detect_language("Please refund the ticket and thanks")["language_type"] == "English"


@pytest.mark.asyncio
async def test_language_preference_self_adjusts_and_drives_tts_resolve():
    store = MemoryStore()
    prefs = LanguagePreferenceService(store)
    await prefs.set("user_fr", "French", source="explicit")
    resolved = await prefs.resolve_for_tts(
        user_id="user_fr",
        explicit_language=None,
        text="Bonjour, merci pour votre aide",
        auto_learn=True,
    )
    assert resolved["language_type"] == "French"
    assert resolved["source"] == "user_preference"

    # New user: detect from text and learn
    learned = await prefs.resolve_for_tts(
        user_id="user_zh",
        explicit_language=None,
        text="你好，我的订单需要退款",
        auto_learn=True,
    )
    assert learned["language_type"] == "Chinese"
    pref = await prefs.get("user_zh")
    assert pref["preferred_language"] == "Chinese"
