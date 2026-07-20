from __future__ import annotations

from typing import Any

from app.db.postgres import PostgresStore
from app.models.schemas import new_id, utc_now
from app.security import EnterprisePrincipal, create_audit_log


class JobQueueService:
    """Database-backed lightweight job queue foundation.

    This is intentionally simple for the enterprise v1 transition: it gives the
    API durable recovery jobs, dead-letter visibility, leases, and worker status
    without introducing Redis/Celery as a hard dependency. It can later be
    swapped for SQS, Temporal, BullMQ, Celery, or Kubernetes Jobs.
    """

    def __init__(self, store: PostgresStore):
        self.store = store

    async def enqueue(self, *, principal: EnterprisePrincipal, job_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        job_id = new_id("job")
        doc = {
            "_id": job_id,
            **principal.context_dict(),
            "job_id": job_id,
            "job_type": job_type,
            "payload": payload,
            "status": "queued",
            "attempts": 0,
            "max_attempts": payload.get("max_attempts", 3),
            "lease_owner": None,
            "lease_expires_at": None,
            "last_error": None,
            "created_at": utc_now(),
            "updated_at": utc_now(),
        }
        await self.store.insert_one("background_jobs", doc)
        await create_audit_log(self.store, action="job.enqueue", principal=principal, resource_type="background_job", resource_id=job_id, metadata={"job_type": job_type})
        return doc

    async def list(self, *, principal: EnterprisePrincipal, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        query = {"workspace_id": principal.workspace_id}
        if status:
            query["status"] = status
        return await self.store.find_many("background_jobs", query, limit=limit)
