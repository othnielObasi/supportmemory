"""TraceMemory enterprise recovery worker scaffold.

This worker intentionally avoids taking a hard dependency on a queue backend.
It documents the execution contract and can be wired to the database-backed
`background_jobs` table or swapped for SQS/Temporal/Celery/BullMQ.
"""
from __future__ import annotations

import asyncio
import os

import httpx

API_BASE_URL = os.getenv("TRACEMEMORY_API_BASE_URL", "http://localhost:8000")
API_KEY = os.getenv("TRACEMEMORY_WORKER_API_KEY", "")
POLL_SECONDS = float(os.getenv("TRACEMEMORY_WORKER_POLL_SECONDS", "5"))


async def poll_once() -> None:
    headers = {"X-TraceMemory-API-Key": API_KEY} if API_KEY else {}
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(f"{API_BASE_URL}/api/enterprise/jobs", headers=headers, params={"status": "queued"})
        response.raise_for_status()
        jobs = response.json()
    for job in jobs:
        print(f"[tracememory-worker] queued job: {job['job_id']} type={job['job_type']}")


async def main() -> None:
    while True:
        await poll_once()
        await asyncio.sleep(POLL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
