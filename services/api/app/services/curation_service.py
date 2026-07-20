from __future__ import annotations

import hashlib
import hmac
import re
from datetime import datetime, timezone
from app.db.postgres import DESCENDING

from app.config import Settings
from app.db.postgres import PostgresStore
from app.models.schemas import LessonStatus, PlaybookRule, ReflectionInsight, new_id
from app.services.embedding_service import EmbeddingService, cosine_similarity


class CurationService:
    def __init__(self, store: PostgresStore, embeddings: EmbeddingService, settings: Settings):
        self.store = store
        self.embeddings = embeddings
        self.settings = settings

    async def curate(self, reflection: ReflectionInsight) -> tuple[PlaybookRule | None, str, str | None]:
        safe, reason = self._validate(reflection)
        if not safe:
            await self.store.update_one('reflection_insights', {'_id': reflection.id}, {'$set': {'status': LessonStatus.rejected.value}})
            return None, reason, None

        embedding = await self.embeddings.embed(reflection.candidate_rule)
        duplicate = await self._find_duplicate(reflection.candidate_rule, embedding)
        if duplicate:
            await self.store.update_one('playbook_rules', {'_id': duplicate['_id']}, {'$inc': {'failure_count': 1}, '$set': {'updated_at': datetime.now(timezone.utc)}})
            await self.store.update_one('reflection_insights', {'_id': reflection.id}, {'$set': {'status': LessonStatus.approved.value}})
            duplicate['failure_count'] = duplicate.get('failure_count', 0) + 1
            return PlaybookRule.model_validate(duplicate), 'Merged with existing similar approved rule.', duplicate.get('signature')

        signature = self._sign(reflection.candidate_rule, reflection.source_trace_id)
        rule = PlaybookRule(_id=new_id('rule'), rule_text=reflection.candidate_rule, category=self._category(reflection.candidate_rule), status=LessonStatus.approved, source_trace_id=reflection.source_trace_id, source_reflection_id=reflection.id, confidence=reflection.confidence, failure_count=1, signature=signature, policy_flags=[], embedding=embedding)
        await self.store.insert_one('playbook_rules', rule.model_dump(by_alias=True))
        await self.store.update_one('reflection_insights', {'_id': reflection.id}, {'$set': {'status': LessonStatus.approved.value}})
        return rule, 'Safe, generalisable, useful, no PII leakage.', signature

    def _validate(self, reflection: ReflectionInsight) -> tuple[bool, str]:
        text = reflection.candidate_rule.strip()
        if len(text) < 12:
            return False, 'Candidate lesson is too short to be useful.'
        pii_patterns = [r'\b\d{3}-\d{2}-\d{4}\b', r'\b\d{4}-\d{4}-\d{4}-\d{4}\b', r'[\w\.-]+@[\w\.-]+\.\w+']
        if any(re.search(pattern, text) for pattern in pii_patterns):
            return False, 'Candidate lesson appears to contain PII.'
        unsafe = ['bypass governance', 'ignore policy', 'disable safety', 'exfiltrate', 'steal']
        if any(phrase in text.lower() for phrase in unsafe):
            return False, 'Candidate lesson contains unsafe instruction.'
        return True, 'Approved.'

    async def _find_duplicate(self, rule_text: str, embedding: list[float]) -> dict | None:
        docs = await self.store.find_many('playbook_rules', {'status': LessonStatus.approved.value}, limit=100, sort=[('created_at', DESCENDING)])
        for doc in docs:
            if doc.get('rule_text', '').strip().lower() == rule_text.strip().lower():
                return doc
            if cosine_similarity(embedding, doc.get('embedding', [])) > 0.96:
                return doc
        return None

    def _sign(self, rule_text: str, source_trace_id: str) -> str:
        msg = f'{rule_text}:{source_trace_id}'.encode('utf-8')
        return hmac.new(self.settings.signing_secret.encode('utf-8'), msg, hashlib.sha256).hexdigest()

    def _category(self, text: str) -> str:
        lower = text.lower()
        if 'paginated' in lower or 'next_page_token' in lower:
            return 'pagination'
        if 'authenticate' in lower:
            return 'authentication'
        if 'schema' in lower:
            return 'validation'
        if 'pii' in lower or 'redact' in lower:
            return 'privacy'
        return 'tool_use'

    async def list_rules(self, limit: int = 50) -> list[PlaybookRule]:
        docs = await self.store.find_many('playbook_rules', limit=limit, sort=[('created_at', DESCENDING)])
        return [PlaybookRule.model_validate(doc) for doc in docs]
