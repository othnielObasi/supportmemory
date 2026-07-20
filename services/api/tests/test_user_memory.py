import pytest

from app.services.conversation_history_service import ConversationHistoryService
from app.services.language_preference_service import LanguagePreferenceService
from app.services.user_preference_service import UserPreferenceService


class MemoryStore:
    def __init__(self):
        self.data = {}

    async def find_one_by(self, collection, query=None, sort=None):
        rows = list(self.data.get(collection, []))
        query = query or {}
        matches = [row for row in rows if all(str(row.get(k)) == str(v) for k, v in query.items())]
        if sort:
            for key, direction in reversed(sort):
                reverse = direction in (-1, "desc", "DESC")
                matches.sort(key=lambda r: str(r.get(key) or ""), reverse=reverse)
        return matches[0] if matches else None

    async def find_many(self, collection, query=None, limit=50, sort=None):
        rows = list(self.data.get(collection, []))
        query = query or {}
        matches = [row for row in rows if all(str(row.get(k)) == str(v) for k, v in query.items())]
        if sort:
            for key, direction in reversed(sort):
                reverse = direction in (-1, "desc", "DESC")
                matches.sort(key=lambda r: str(r.get(key) or ""), reverse=reverse)
        return matches[:limit]

    async def upsert_one(self, collection, query, update):
        payload = dict(update)
        existing = await self.find_one_by(collection, query)
        if existing:
            existing.clear()
            existing.update(payload)
            return
        self.data.setdefault(collection, []).append(payload)


@pytest.mark.asyncio
async def test_user_preferences_upsert_and_profile_prefix():
    store = MemoryStore()
    langs = LanguagePreferenceService(store)
    prefs = UserPreferenceService(store, language_prefs=langs)

    profile = await prefs.upsert(
        "user_apex",
        display_name="Sarah Jenkins",
        company="Apex Cloud",
        contact_channel="zendesk",
        plan_tier="enterprise",
        preferred_language="English",
        extras={"account_id": "acct_99"},
    )
    assert profile["display_name"] == "Sarah Jenkins"
    assert profile["plan_tier"] == "enterprise"
    assert profile["extras"]["account_id"] == "acct_99"

    lang = await langs.get("user_apex")
    assert lang["preferred_language"] == "English"

    prefix = prefs.context_prefix(profile)
    assert "Sarah Jenkins" in prefix
    assert "enterprise" in prefix
    assert "acct_99" in prefix


@pytest.mark.asyncio
async def test_conversation_history_append_and_context():
    store = MemoryStore()
    history = ConversationHistoryService(store, max_messages=10)

    conv = await history.get_or_create_default("user_apex")
    assert conv["is_default"] is True

    await history.append_turn(
        "user_apex",
        user_content="Webhook 401 after secret rotation",
        assistant_content="Checking auth-node-04b and prior ticket TX-3104.",
        conversation_id=conv["conversation_id"],
    )
    again = await history.get(conv["conversation_id"])
    assert again["message_count"] == 2
    assert again["messages"][0]["role"] == "user"
    assert again["messages"][1]["role"] == "assistant"

    prefix = history.recent_context_prefix(again)
    assert "Webhook 401" in prefix
    assert "assistant:" in prefix


@pytest.mark.asyncio
async def test_conversation_truncates_to_max_messages():
    store = MemoryStore()
    history = ConversationHistoryService(store, max_messages=4)
    conv = await history.create("user_bolt", title="Burst")
    for i in range(6):
        await history.append_message(conv["conversation_id"], role="user", content=f"msg {i}")
    final = await history.get(conv["conversation_id"])
    assert final["message_count"] == 4
    assert final["messages"][0]["content"] == "msg 2"
