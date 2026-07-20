from __future__ import annotations
from app.db.postgres import DESCENDING
from app.db.postgres import PostgresStore
from app.models.schemas import ExecutionTrace


class TraceService:
    def __init__(self, store: PostgresStore):
        self.store = store

    async def save(self, trace: ExecutionTrace) -> ExecutionTrace:
        await self.store.insert_one('execution_traces', trace.model_dump(by_alias=True))
        return trace

    async def get(self, trace_id: str) -> ExecutionTrace | None:
        doc = await self.store.find_one('execution_traces', trace_id)
        return ExecutionTrace.model_validate(doc) if doc else None

    async def list(self, limit: int = 25) -> list[ExecutionTrace]:
        docs = await self.store.find_many('execution_traces', limit=limit, sort=[('created_at', DESCENDING)])
        return [ExecutionTrace.model_validate(doc) for doc in docs]
