from __future__ import annotations

import re
from typing import Any, Optional

from app.db.postgres import DESCENDING, PostgresStore
from app.models.schemas import new_id, utc_now

# Qwen-TTS language_type values
TTS_LANGUAGES = {
    "auto": "Auto",
    "en": "English",
    "english": "English",
    "zh": "Chinese",
    "zh-cn": "Chinese",
    "zh-tw": "Chinese",
    "chinese": "Chinese",
    "ja": "Japanese",
    "japanese": "Japanese",
    "ko": "Korean",
    "korean": "Korean",
    "fr": "French",
    "french": "French",
    "de": "German",
    "german": "German",
    "es": "Spanish",
    "spanish": "Spanish",
    "pt": "Portuguese",
    "portuguese": "Portuguese",
    "it": "Italian",
    "italian": "Italian",
    "ru": "Russian",
    "russian": "Russian",
}

# Qwen-ASR language codes (when specified)
ASR_LANGUAGES = {
    "English": "en",
    "Chinese": "zh",
    "Japanese": "ja",
    "Korean": "ko",
    "French": "fr",
    "German": "de",
    "Spanish": "es",
    "Portuguese": "pt",
    "Italian": "it",
    "Russian": "ru",
    "Auto": None,
}


class LanguagePreferenceService:
    """Remember and self-adjust the user's preferred language for multilingual voice.

    Priority for TTS/ASR language:
      1. Explicit override on the request
      2. Stored user preference
      3. Detected from current text/transcript
      4. Settings default / Auto
    """

    def __init__(self, store: PostgresStore):
        self.store = store

    async def get(self, user_id: str) -> dict[str, Any]:
        doc = await self.store.find_one_by("user_language_preferences", {"user_id": user_id})
        if not doc:
            return {
                "user_id": user_id,
                "preferred_language": "Auto",
                "preferred_code": "auto",
                "source": "default",
                "updated_at": None,
            }
        return {
            "user_id": user_id,
            "preferred_language": doc.get("preferred_language", "Auto"),
            "preferred_code": doc.get("preferred_code", "auto"),
            "source": doc.get("source", "stored"),
            "updated_at": doc.get("updated_at"),
            "detection_history": doc.get("detection_history", [])[-5:],
        }

    async def set(
        self,
        user_id: str,
        language: str,
        *,
        source: str = "explicit",
    ) -> dict[str, Any]:
        tts_lang, code = self.normalize(language)
        existing = await self.store.find_one_by("user_language_preferences", {"user_id": user_id})
        payload = {
            "_id": (existing or {}).get("_id") or new_id("langpref"),
            "id": (existing or {}).get("id") or new_id("langpref"),
            "user_id": user_id,
            "preferred_language": tts_lang,
            "preferred_code": code,
            "source": source,
            "updated_at": utc_now().isoformat(),
            "detection_history": list((existing or {}).get("detection_history") or []),
        }
        await self.store.upsert_one("user_language_preferences", {"user_id": user_id}, payload)
        return await self.get(user_id)

    async def resolve_for_tts(
        self,
        *,
        user_id: Optional[str],
        explicit_language: Optional[str],
        text: str,
        auto_learn: bool = True,
    ) -> dict[str, Any]:
        if explicit_language:
            tts_lang, code = self.normalize(explicit_language)
            if user_id and auto_learn and tts_lang != "Auto":
                await self.set(user_id, tts_lang, source="explicit")
            return {"language_type": tts_lang, "code": code, "source": "explicit"}

        if user_id:
            pref = await self.get(user_id)
            if pref.get("preferred_language") and pref["preferred_language"] != "Auto":
                return {
                    "language_type": pref["preferred_language"],
                    "code": pref.get("preferred_code", "auto"),
                    "source": "user_preference",
                }

        detected = self.detect_language(text)
        if detected["language_type"] != "Auto" and user_id and auto_learn:
            await self._learn(user_id, detected["language_type"], detected["code"], sample=text[:80])
        return {
            "language_type": detected["language_type"],
            "code": detected["code"],
            "source": "detected" if detected["language_type"] != "Auto" else "auto",
        }

    async def resolve_for_asr(
        self,
        *,
        user_id: Optional[str],
        explicit_language: Optional[str],
        auto_learn: bool = True,
    ) -> dict[str, Any]:
        if explicit_language:
            tts_lang, code = self.normalize(explicit_language)
            asr_code = ASR_LANGUAGES.get(tts_lang)
            if user_id and auto_learn and tts_lang != "Auto":
                await self.set(user_id, tts_lang, source="explicit")
            return {"language_type": tts_lang, "asr_language": asr_code, "code": code, "source": "explicit"}

        if user_id:
            pref = await self.get(user_id)
            tts_lang = pref.get("preferred_language") or "Auto"
            if tts_lang != "Auto":
                return {
                    "language_type": tts_lang,
                    "asr_language": ASR_LANGUAGES.get(tts_lang),
                    "code": pref.get("preferred_code", "auto"),
                    "source": "user_preference",
                }

        return {"language_type": "Auto", "asr_language": None, "code": "auto", "source": "auto"}

    async def learn_from_transcript(
        self,
        user_id: Optional[str],
        transcript: str,
        *,
        auto_learn: bool = True,
    ) -> Optional[dict[str, Any]]:
        if not user_id or not auto_learn or not transcript:
            return None
        detected = self.detect_language(transcript)
        if detected["language_type"] == "Auto":
            return None
        return await self._learn(
            user_id,
            detected["language_type"],
            detected["code"],
            sample=transcript[:80],
        )

    def normalize(self, language: str) -> tuple[str, str]:
        key = (language or "auto").strip().lower()
        tts = TTS_LANGUAGES.get(key)
        if tts:
            code = key if key in {"en", "zh", "ja", "ko", "fr", "de", "es", "pt", "it", "ru", "auto"} else self._code_for_tts(tts)
            return tts, code
        # Already a Qwen language_type?
        for code, name in [
            ("en", "English"),
            ("zh", "Chinese"),
            ("ja", "Japanese"),
            ("ko", "Korean"),
            ("fr", "French"),
            ("de", "German"),
            ("es", "Spanish"),
            ("pt", "Portuguese"),
            ("it", "Italian"),
            ("ru", "Russian"),
            ("auto", "Auto"),
        ]:
            if key == name.lower():
                return name, code
        return "Auto", "auto"

    def detect_language(self, text: str) -> dict[str, str]:
        sample = (text or "").strip()
        if not sample:
            return {"language_type": "Auto", "code": "auto"}

        if re.search(r"[\u4e00-\u9fff]", sample):
            return {"language_type": "Chinese", "code": "zh"}
        if re.search(r"[\u3040-\u30ff]", sample):
            return {"language_type": "Japanese", "code": "ja"}
        if re.search(r"[\uac00-\ud7af]", sample):
            return {"language_type": "Korean", "code": "ko"}
        if re.search(r"[\u0400-\u04ff]", sample):
            return {"language_type": "Russian", "code": "ru"}

        lower = sample.lower()
        # Lightweight word cues for Latin-script languages
        scores = {
            "French": len(re.findall(r"\b(le|la|les|des|une|bonjour|merci|est|pas)\b", lower)),
            "German": len(re.findall(r"\b(der|die|das|und|nicht|ist|ein|eine|danke)\b", lower)),
            "Spanish": len(re.findall(r"\b(el|la|los|las|una|hola|gracias|que|por)\b", lower)),
            "Portuguese": len(re.findall(r"\b(uma|não|obrigado|você|para|como)\b", lower)),
            "Italian": len(re.findall(r"\b(il|una|ciao|grazie|non|per|che)\b", lower)),
            "English": len(re.findall(r"\b(the|and|is|are|you|please|thanks|ticket|refund)\b", lower)),
        }
        best = max(scores.items(), key=lambda item: item[1])
        if best[1] >= 2:
            return {"language_type": best[0], "code": self._code_for_tts(best[0])}
        if re.search(r"[A-Za-z]", sample):
            return {"language_type": "English", "code": "en"}
        return {"language_type": "Auto", "code": "auto"}

    async def _learn(self, user_id: str, language_type: str, code: str, sample: str) -> dict[str, Any]:
        existing = await self.store.find_one_by("user_language_preferences", {"user_id": user_id})
        history = list((existing or {}).get("detection_history") or [])
        history.append({"language": language_type, "sample": sample, "at": utc_now().isoformat()})
        payload = {
            "_id": (existing or {}).get("_id") or new_id("langpref"),
            "id": (existing or {}).get("id") or new_id("langpref"),
            "user_id": user_id,
            "preferred_language": language_type,
            "preferred_code": code,
            "source": "auto_learn",
            "updated_at": utc_now().isoformat(),
            "detection_history": history[-20:],
        }
        await self.store.upsert_one("user_language_preferences", {"user_id": user_id}, payload)
        return await self.get(user_id)

    def _code_for_tts(self, tts_lang: str) -> str:
        reverse = {v: k for k, v in ASR_LANGUAGES.items() if v}
        # ASR_LANGUAGES maps TTS name -> code; invert carefully
        for name, code in ASR_LANGUAGES.items():
            if name == tts_lang and code:
                return code
        return "auto"
