from __future__ import annotations

import json
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence
from uuid import UUID

try:
    import asyncpg
except ModuleNotFoundError:  # pragma: no cover - lets contract tests import without local PostgreSQL deps.
    class _MissingAsyncpg:
        class Pool: ...
        class Record(dict): ...
        async def create_pool(self, *args, **kwargs):
            raise RuntimeError("asyncpg is not installed. Install services/api/requirements.txt for PostgreSQL runtime.")
    asyncpg = _MissingAsyncpg()

from app.config import Settings

ASCENDING = 1
DESCENDING = -1

PRODUCTION_COLLECTIONS = [
    'agent_runs',
    'run_events',
    'task_checkpoints',
    'task_versions',
    'execution_traces',
    'tool_traces',
    'governor_decisions',
    'action_executions',
    'reflection_insights',
    'playbook_rules',
    'retrieval_events',
    'kb_documents',
    'kb_chunks',
    'user_language_preferences',
    'idempotency_keys',
    'organisations',
    'workspaces',
    'projects',
    'environments',
    'users',
    'service_accounts',
    'api_keys',
    'rbac_assignments',
    'model_gateway_configs',
    'tool_registry',
    'background_jobs',
    'audit_logs',
    'model_attempts',
    'fallback_events',
    'recovery_records',
    'audit_reports',
]


class PostgresStore:
    """
    PostgreSQL-backed document store for TraceMemory.

    The service stores each TraceMemory logical collection as JSONB
    records in PostgreSQL. This gives you a durable relational database option that
    works locally with Docker, on Render/Railway/Fly, and later on AWS RDS.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.pool: Optional[asyncpg.Pool] = None
        self.indexes_ready: bool = False

    async def connect(self) -> None:
        self.pool = await asyncpg.create_pool(
            dsn=self.settings.database_url,
            min_size=self.settings.database_pool_min_size,
            max_size=self.settings.database_pool_max_size,
            command_timeout=self.settings.database_command_timeout_seconds,
        )
        await self.ensure_indexes()

    async def close(self) -> None:
        if self.pool:
            await self.pool.close()

    async def ping(self) -> bool:
        if self.pool is None:
            return False
        try:
            async with self.pool.acquire() as conn:
                await conn.fetchval('SELECT 1')
            return True
        except Exception:
            return False

    async def ensure_indexes(self) -> None:
        if self.pool is None:
            raise RuntimeError('PostgreSQL pool not connected')
        statements = [
            """
            CREATE TABLE IF NOT EXISTS trace_memory_records (
                collection TEXT NOT NULL,
                id TEXT NOT NULL,
                data JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                PRIMARY KEY (collection, id)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_tm_records_collection_created ON trace_memory_records (collection, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_tm_records_data_gin ON trace_memory_records USING GIN (data)",
            "CREATE INDEX IF NOT EXISTS idx_tm_records_task_id ON trace_memory_records (collection, (data->>'task_id'))",
            "CREATE INDEX IF NOT EXISTS idx_tm_records_trace_id ON trace_memory_records (collection, (data->>'trace_id'))",
            "CREATE INDEX IF NOT EXISTS idx_tm_records_checkpoint_id ON trace_memory_records (collection, (data->>'checkpoint_id'))",
            "CREATE INDEX IF NOT EXISTS idx_tm_records_status ON trace_memory_records (collection, (data->>'status'))",
            "CREATE INDEX IF NOT EXISTS idx_tm_records_idempotency ON trace_memory_records (collection, (data->>'idempotency_key'))",
            "CREATE INDEX IF NOT EXISTS idx_tm_records_org ON trace_memory_records (collection, (data->>'organisation_id'))",
            "CREATE INDEX IF NOT EXISTS idx_tm_records_workspace ON trace_memory_records (collection, (data->>'workspace_id'))",
            "CREATE INDEX IF NOT EXISTS idx_tm_records_project ON trace_memory_records (collection, (data->>'project_id'))",
            "CREATE INDEX IF NOT EXISTS idx_tm_records_environment ON trace_memory_records (collection, (data->>'environment_id'))",
            "CREATE INDEX IF NOT EXISTS idx_tm_records_agent ON trace_memory_records (collection, (data->>'agent_id'))",
            "CREATE INDEX IF NOT EXISTS idx_tm_records_job_status ON trace_memory_records (collection, (data->>'status')) WHERE collection = 'background_jobs'",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_tm_api_key_hash ON trace_memory_records ((data->>'key_hash')) WHERE collection = 'api_keys' AND data ? 'key_hash'",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_tm_action_idempotency ON trace_memory_records ((data->>'workspace_id'), (data->>'idempotency_key')) WHERE collection = 'action_executions' AND data ? 'idempotency_key'",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_tm_idempotency_keys ON trace_memory_records ((data->>'key')) WHERE collection = 'idempotency_keys' AND data ? 'key'",
        ]
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                for statement in statements:
                    await conn.execute(statement)
        self.indexes_ready = True

    def collection(self, name: str):
        """Compatibility guard for direct-database access paths."""
        raise RuntimeError(
            f"Direct collection access is not available for PostgreSQL logical collection '{name}'. "
            'Use PostgresStore insert/find/update methods instead.'
        )

    async def insert_one(self, collection: str, doc: Dict[str, Any]) -> str:
        record = self._normalise_doc(doc)
        record_id = str(record.get('_id') or record.get('id'))
        if not record_id or record_id == 'None':
            raise ValueError(f"Document inserted into {collection} must include '_id' or 'id'")
        created_at = self._coerce_datetime(record.get('created_at')) or datetime.now(timezone.utc)
        async with self._acquire() as conn:
            await conn.execute(
                """
                INSERT INTO trace_memory_records(collection, id, data, created_at, updated_at)
                VALUES ($1, $2, $3::jsonb, $4, now())
                ON CONFLICT (collection, id) DO UPDATE
                SET data = EXCLUDED.data,
                    created_at = EXCLUDED.created_at,
                    updated_at = now()
                """,
                collection,
                record_id,
                json.dumps(record, separators=(',', ':'), default=str),
                created_at,
            )
        return record_id

    async def upsert_one(self, collection: str, query: Dict[str, Any], update: Dict[str, Any]) -> None:
        existing = await self.find_one_by(collection, query)
        payload = self._normalise_doc(update)
        if existing:
            merged = {**existing, **payload}
            await self.insert_one(collection, merged)
            return
        if '_id' not in payload and 'id' not in payload:
            payload['_id'] = payload.get('key') or payload.get('idempotency_key')
        await self.insert_one(collection, payload)

    async def update_one(self, collection: str, query: Dict[str, Any], update: Dict[str, Any]) -> None:
        existing = await self.find_one_by(collection, query)
        if not existing:
            return
        updated = dict(existing)
        set_values = update.get('$set', {}) if any(k.startswith('$') for k in update) else update
        inc_values = update.get('$inc', {}) if isinstance(update.get('$inc'), dict) else {}
        updated.update(self._normalise_doc(set_values))
        for key, amount in inc_values.items():
            current = updated.get(key, 0) or 0
            updated[key] = current + amount
        await self.insert_one(collection, updated)

    async def find_one(self, collection: str, doc_id: str) -> Optional[Dict[str, Any]]:
        async with self._acquire() as conn:
            row = await conn.fetchrow(
                'SELECT data FROM trace_memory_records WHERE collection = $1 AND id = $2',
                collection,
                doc_id,
            )
        return self._decode_row(row)

    async def find_one_by(
        self,
        collection: str,
        query: Dict[str, Any],
        sort: List[tuple] | None = None,
    ) -> Optional[Dict[str, Any]]:
        docs = await self.find_many(collection, query=query, limit=1, sort=sort)
        return docs[0] if docs else None

    async def find_many(
        self,
        collection: str,
        query: Dict[str, Any] | None = None,
        limit: int = 50,
        sort: List[tuple] | None = None,
    ) -> List[Dict[str, Any]]:
        where, params = self._build_where(collection, query or {})
        order_by = self._build_order_by(sort)
        sql = f'SELECT data FROM trace_memory_records WHERE {where} {order_by} LIMIT ${len(params) + 1}'
        params.append(limit)
        async with self._acquire() as conn:
            rows = await conn.fetch(sql, *params)
        return [self._decode_row(row) for row in rows if row]

    async def count_documents(self, collection: str, query: Dict[str, Any] | None = None) -> int:
        where, params = self._build_where(collection, query or {})
        async with self._acquire() as conn:
            return int(await conn.fetchval(f'SELECT count(*) FROM trace_memory_records WHERE {where}', *params))

    async def latest_checkpoint(self, task_id: str) -> Optional[Dict[str, Any]]:
        return await self.find_one_by('task_checkpoints', {'task_id': task_id}, sort=[('created_at', DESCENDING)])

    async def delete_all(self) -> None:
        async with self._acquire() as conn:
            await conn.execute('DELETE FROM trace_memory_records')

    def _acquire(self):
        if self.pool is None:
            raise RuntimeError('PostgreSQL not connected')
        return self.pool.acquire()

    def _build_where(self, collection: str, query: Dict[str, Any]) -> tuple[str, list[Any]]:
        clauses = ['collection = $1']
        params: list[Any] = [collection]
        for key, value in query.items():
            params.append(str(value))
            if key in {'_id', 'id'}:
                clauses.append(f'id = ${len(params)}')
            else:
                clauses.append(f"data->>'{self._safe_json_key(key)}' = ${len(params)}")
        return ' AND '.join(clauses), params

    def _build_order_by(self, sort: Sequence[tuple] | None) -> str:
        if not sort:
            return 'ORDER BY created_at DESC'
        clauses: list[str] = []
        for key, direction in sort:
            direction_sql = 'DESC' if direction == DESCENDING or str(direction).lower() == 'desc' else 'ASC'
            safe_key = self._safe_json_key(str(key))
            if safe_key == 'created_at':
                expr = 'created_at'
            elif safe_key in {'version', 'task_version', 'risk_score', 'failure_count', 'confidence'}:
                expr = f"NULLIF(data->>'{safe_key}', '')::numeric"
            else:
                expr = f"data->>'{safe_key}'"
            clauses.append(f'{expr} {direction_sql} NULLS LAST')
        return 'ORDER BY ' + ', '.join(clauses)

    def _decode_row(self, row: asyncpg.Record | None) -> Optional[Dict[str, Any]]:
        if not row:
            return None
        value = row['data']
        if isinstance(value, str):
            return json.loads(value)
        return dict(value)

    def _normalise_doc(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        payload = self._jsonable(doc)
        if 'id' in payload and '_id' not in payload:
            payload['_id'] = payload['id']
        if '_id' in payload and 'id' not in payload:
            payload['id'] = payload['_id']
        return payload

    def _jsonable(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {str(k): self._jsonable(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._jsonable(v) for v in value]
        if isinstance(value, tuple):
            return [self._jsonable(v) for v in value]
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, UUID):
            return str(value)
        return value

    def _coerce_datetime(self, value: Any) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                return None
        return None

    def _safe_json_key(self, key: str) -> str:
        if not key.replace('_', '').isalnum():
            raise ValueError(f'Unsupported query key: {key}')
        return key
