from __future__ import annotations

from typing import Any, Optional

from app.db.postgres import DESCENDING, PostgresStore
from app.models.schemas import new_id, utc_now


class ConversationHistoryService:
    """Per-user conversation history store for cross-session SupportMemory recall.

    One document per conversation thread. Messages are appended in order and
    truncated to a max length so context stays bounded.
    """

    COLLECTION = "user_conversations"

    def __init__(self, store: PostgresStore, *, max_messages: int = 100):
        self.store = store
        self.max_messages = max_messages

    async def create(
        self,
        user_id: str,
        *,
        title: Optional[str] = None,
        channel: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        now = utc_now().isoformat()
        conversation_id = new_id("conv")
        meta = dict(metadata or {})
        # Store as string so JSONB text equality matches PostgresStore queries.
        is_default = "true" if meta.pop("is_default", False) else "false"
        payload = {
            "_id": conversation_id,
            "id": conversation_id,
            "conversation_id": conversation_id,
            "user_id": user_id,
            "title": title or "Support conversation",
            "channel": channel or "chat",
            "messages": [],
            "metadata": meta,
            "is_default": is_default,
            "created_at": now,
            "updated_at": now,
        }
        await self.store.upsert_one(self.COLLECTION, {"conversation_id": conversation_id}, payload)
        return await self.get(conversation_id)

    async def get(self, conversation_id: str) -> dict[str, Any]:
        doc = await self.store.find_one_by(self.COLLECTION, {"conversation_id": conversation_id})
        if not doc:
            raise KeyError(f"conversation not found: {conversation_id}")
        return self._public(doc)

    async def list_for_user(self, user_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
        docs = await self.store.find_many(
            self.COLLECTION,
            query={"user_id": user_id},
            limit=limit,
            sort=[("updated_at", DESCENDING)],
        )
        return [self._public(doc, include_messages=False) for doc in docs]

    async def get_or_create_default(self, user_id: str) -> dict[str, Any]:
        docs = await self.store.find_many(
            self.COLLECTION,
            query={"user_id": user_id, "is_default": "true"},
            limit=1,
            sort=[("updated_at", DESCENDING)],
        )
        if docs:
            return self._public(docs[0])
        return await self.create(
            user_id,
            title="Default support thread",
            metadata={"is_default": True},
        )

    async def append_message(
        self,
        conversation_id: str,
        *,
        role: str,
        content: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        doc = await self.store.find_one_by(self.COLLECTION, {"conversation_id": conversation_id})
        if not doc:
            raise KeyError(f"conversation not found: {conversation_id}")
        role_norm = (role or "user").strip().lower()
        if role_norm not in {"user", "assistant", "system", "tool"}:
            role_norm = "user"
        messages = list(doc.get("messages") or [])
        messages.append(
            {
                "message_id": new_id("msg"),
                "role": role_norm,
                "content": (content or "").strip(),
                "metadata": metadata or {},
                "created_at": utc_now().isoformat(),
            }
        )
        if len(messages) > self.max_messages:
            messages = messages[-self.max_messages :]
        doc["messages"] = messages
        doc["updated_at"] = utc_now().isoformat()
        # Keep title fresh from first user message if still default
        if doc.get("title") in {"Support conversation", "Default support thread"} and role_norm == "user":
            snippet = (content or "").strip().replace("\n", " ")
            if snippet:
                doc["title"] = snippet[:72]
        await self.store.upsert_one(self.COLLECTION, {"conversation_id": conversation_id}, doc)
        return self._public(doc)

    async def append_turn(
        self,
        user_id: str,
        *,
        user_content: str,
        assistant_content: str,
        conversation_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Append a user+assistant pair, creating/using the default thread when needed."""
        if conversation_id:
            conv = await self.get(conversation_id)
            if conv["user_id"] != user_id:
                raise PermissionError("conversation does not belong to user")
        else:
            conv = await self.get_or_create_default(user_id)
            conversation_id = conv["conversation_id"]
        await self.append_message(
            conversation_id,
            role="user",
            content=user_content,
            metadata=metadata,
        )
        if assistant_content:
            await self.append_message(
                conversation_id,
                role="assistant",
                content=assistant_content,
                metadata=metadata,
            )
        return await self.get(conversation_id)

    def recent_context_prefix(
        self,
        conversation: dict[str, Any],
        *,
        max_messages: int = 12,
        max_chars: int = 3500,
    ) -> str:
        messages = list(conversation.get("messages") or [])[-max_messages:]
        if not messages:
            return ""
        lines = [f"[Conversation history · {conversation.get('conversation_id')}]"]
        for msg in messages:
            role = msg.get("role", "user")
            content = (msg.get("content") or "").strip()
            if not content:
                continue
            lines.append(f"{role}: {content}")
        text = "\n".join(lines)
        if len(text) > max_chars:
            text = text[-max_chars:]
            text = "[Conversation history · truncated]\n" + text
        return text

    def _public(self, doc: dict[str, Any], *, include_messages: bool = True) -> dict[str, Any]:
        messages = list(doc.get("messages") or [])
        return {
            "conversation_id": doc.get("conversation_id") or doc.get("id"),
            "user_id": doc.get("user_id"),
            "title": doc.get("title") or "Support conversation",
            "channel": doc.get("channel") or "chat",
            "is_default": str(doc.get("is_default")).lower() in {"true", "1", "yes"},
            "message_count": len(messages),
            "messages": messages if include_messages else [],
            "metadata": doc.get("metadata") or {},
            "created_at": doc.get("created_at"),
            "updated_at": doc.get("updated_at"),
        }
