from __future__ import annotations

from typing import List

import httpx

from app.config import Settings


class FireworksService:
    """Small Fireworks AI adapter used for agent planning and run summaries.

    The service is safe for local demos: if FIREWORKS_API_KEY is absent it returns
    a deterministic fallback plan so the rest of the runtime still works.
    """

    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return bool(self.settings.fireworks_api_key)

    async def generate_plan(self, task_description: str, run_events: List[str] | None = None) -> tuple[str, bool]:
        events = run_events or []
        fallback = (
            "1. Confirm the task scope and completion condition.\n"
            "2. Retrieve the required records through governed tools.\n"
            "3. Save a PostgreSQL checkpoint after each durable step.\n"
            "4. Restore from checkpoint if interrupted.\n"
            "5. Apply approved execution memory before final retrieval.\n"
            "6. Return the result only after validation conditions are satisfied."
        )
        if not self.enabled:
            return fallback, True

        payload = {
            "model": self.settings.fireworks_model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are generating concise execution plans for long-running agent workflows. Do not reveal private chain-of-thought. Return operational steps only.",
                },
                {
                    "role": "user",
                    "content": f"Task: {task_description}\nCompleted runtime events: {', '.join(events) if events else 'none'}\nReturn a short durable execution plan using checkpoints, recovery, and validation.",
                },
            ],
            "temperature": 0.2,
            "max_tokens": 450,
        }
        headers = {"Authorization": f"Bearer {self.settings.fireworks_api_key}"}
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{self.settings.fireworks_base_url}/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        return data["choices"][0]["message"]["content"], False
