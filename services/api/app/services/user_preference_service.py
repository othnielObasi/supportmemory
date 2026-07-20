from __future__ import annotations

from typing import Any, Optional

from app.db.postgres import PostgresStore
from app.models.schemas import new_id, utc_now

PLAN_TIERS = {"free", "starter", "pro", "enterprise", "unknown"}
CONTACT_CHANNELS = {
    "email",
    "phone",
    "sms",
    "chat",
    "zendesk",
    "freshdesk",
    "intercom",
    "slack",
    "other",
    "unknown",
}


class UserPreferenceService:
    """Generic per-user profile / preferences for SupportMemory.

    Stores durable attributes the agent should remember across tickets:
    display name, contact channel, plan tier, company, and free-form extras.
    Language preference can be mirrored here and synced to LanguagePreferenceService.
    """

    COLLECTION = "user_preferences"

    def __init__(self, store: PostgresStore, language_prefs=None):
        self.store = store
        self.language_prefs = language_prefs

    def _defaults(self, user_id: str, organisation_id: str = "org_default", workspace_id: str = "wrk_default") -> dict[str, Any]:
        return {
            "user_id": user_id,
            "display_name": None,
            "email": None,
            "phone": None,
            "company": None,
            "contact_channel": "unknown",
            "plan_tier": "unknown",
            "preferred_language": None,
            "timezone": None,
            "extras": {},
            "source": "default",
            "created_at": None,
            "updated_at": None,
            "organisation_id": organisation_id,
            "workspace_id": workspace_id,
        }

    async def get(self, user_id: str, organisation_id: str = "org_default", workspace_id: str = "wrk_default") -> dict[str, Any]:
        doc = await self.store.find_one_by(self.COLLECTION, {"user_id": user_id, "organisation_id": organisation_id, "workspace_id": workspace_id})
        if not doc and organisation_id == "org_default" and workspace_id == "wrk_default":
            doc = await self.store.find_one_by(self.COLLECTION, {"user_id": user_id})
        base = self._defaults(user_id, organisation_id, workspace_id)
        if not doc:
            return base
        extras = doc.get("extras") if isinstance(doc.get("extras"), dict) else {}
        return {
            **base,
            "display_name": doc.get("display_name"),
            "email": doc.get("email"),
            "phone": doc.get("phone"),
            "company": doc.get("company"),
            "contact_channel": doc.get("contact_channel") or "unknown",
            "plan_tier": doc.get("plan_tier") or "unknown",
            "preferred_language": doc.get("preferred_language"),
            "timezone": doc.get("timezone"),
            "extras": extras,
            "source": doc.get("source", "stored"),
            "created_at": doc.get("created_at"),
            "updated_at": doc.get("updated_at"),
        }

    async def upsert(
        self,
        user_id: str,
        *,
        display_name: Optional[str] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        company: Optional[str] = None,
        contact_channel: Optional[str] = None,
        plan_tier: Optional[str] = None,
        preferred_language: Optional[str] = None,
        timezone: Optional[str] = None,
        extras: Optional[dict[str, Any]] = None,
        source: str = "explicit",
        merge_extras: bool = True,
        organisation_id: str = "org_default",
        workspace_id: str = "wrk_default",
    ) -> dict[str, Any]:
        query = {"user_id": user_id, "organisation_id": organisation_id, "workspace_id": workspace_id}
        existing = await self.store.find_one_by(self.COLLECTION, query)
        now = utc_now().isoformat()
        prev_extras = (existing or {}).get("extras") if isinstance((existing or {}).get("extras"), dict) else {}
        next_extras = {**prev_extras, **(extras or {})} if merge_extras else (extras or {})

        channel = (contact_channel or (existing or {}).get("contact_channel") or "unknown").strip().lower()
        if channel not in CONTACT_CHANNELS:
            channel = "other"
        tier = (plan_tier or (existing or {}).get("plan_tier") or "unknown").strip().lower()
        if tier not in PLAN_TIERS:
            tier = "unknown"

        payload = {
            "_id": (existing or {}).get("_id") or new_id("userpref"),
            "id": (existing or {}).get("id") or new_id("userpref"),
            "user_id": user_id,
            "display_name": display_name if display_name is not None else (existing or {}).get("display_name"),
            "email": email if email is not None else (existing or {}).get("email"),
            "phone": phone if phone is not None else (existing or {}).get("phone"),
            "company": company if company is not None else (existing or {}).get("company"),
            "contact_channel": channel,
            "plan_tier": tier,
            "preferred_language": preferred_language
            if preferred_language is not None
            else (existing or {}).get("preferred_language"),
            "timezone": timezone if timezone is not None else (existing or {}).get("timezone"),
            "extras": next_extras,
            "source": source,
            "created_at": (existing or {}).get("created_at") or now,
            "updated_at": now,
            "organisation_id": organisation_id,
            "workspace_id": workspace_id,
        }
        await self.store.upsert_one(self.COLLECTION, query, payload)

        if preferred_language and self.language_prefs is not None:
            await self.language_prefs.set(user_id, preferred_language, source=source)

        return await self.get(user_id, organisation_id, workspace_id)

    async def delete(self, user_id: str, organisation_id: str = "org_default", workspace_id: str = "wrk_default") -> int:
        return await self.store.delete_many(self.COLLECTION, {"user_id": user_id, "organisation_id": organisation_id, "workspace_id": workspace_id})

    def context_prefix(self, profile: dict[str, Any]) -> str:
        """Compact profile block for agent context_prefix injection."""
        if not profile or profile.get("source") == "default" and not any(
            profile.get(k) for k in ("display_name", "email", "company", "phone")
        ):
            # Still emit tier/channel if set away from unknown
            if (profile or {}).get("plan_tier") in (None, "unknown") and (profile or {}).get(
                "contact_channel"
            ) in (None, "unknown"):
                return ""
        lines = ["[User profile]"]
        mapping = [
            ("display_name", "Name"),
            ("email", "Email"),
            ("phone", "Phone"),
            ("company", "Company"),
            ("contact_channel", "Preferred channel"),
            ("plan_tier", "Plan tier"),
            ("preferred_language", "Language"),
            ("timezone", "Timezone"),
        ]
        for key, label in mapping:
            value = profile.get(key)
            if value and value != "unknown":
                lines.append(f"- {label}: {value}")
        extras = profile.get("extras") or {}
        for key, value in list(extras.items())[:12]:
            if value is not None and value != "":
                lines.append(f"- {key}: {value}")
        return "\n".join(lines) if len(lines) > 1 else ""
