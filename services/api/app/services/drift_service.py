from __future__ import annotations

import json
from typing import Any, Optional

from app.db.postgres import PostgresStore
from app.models.schemas import TaskContract, new_id


DRIFT_SYSTEM_PROMPT = (
    "You are the drift-detection component of an AI agent's execution-continuity system. "
    "You are given a task CONTRACT (the original goal, approved scope, and forbidden actions) "
    "and the agent's CURRENT ACTION. Decide whether the current action is still in service of "
    "the original goal, or whether the agent has drifted onto a different problem. "
    "You judge CONTINUITY only — whether the work still matches the original task. You do NOT "
    "judge whether the action is permitted, safe, or compliant; that is a separate governance "
    "concern. Return STRICT JSON only, no prose, no code fences, with exactly these keys: "
    '{"aligned": <true|false>, '
    '"severity": "<none|minor|major>", '
    '"reason": "<one sentence explaining the judgement, referencing the goal>"}'
)


class DriftService:
    """Stores task contracts and judges whether a current action still serves the
    original task. Uses the model gateway for a real judgement; falls back to a
    deterministic keyword heuristic only when no live gateway is available, and
    labels which path was used so the result is always auditable."""

    def __init__(self, store: PostgresStore, gateway: Any | None = None):
        self.store = store
        self.gateway = gateway

    async def set_contract(self, task_id: str, req) -> TaskContract:
        contract = TaskContract(
            _id=new_id("contract"),
            task_id=task_id,
            agent_id=getattr(req, "agent_id", "agent_demo"),
            original_goal=req.original_goal,
            approved_scope=getattr(req, "approved_scope", "") or "",
            success_criteria=list(getattr(req, "success_criteria", []) or []),
            forbidden_actions=list(getattr(req, "forbidden_actions", []) or []),
            task_version=1,
        )
        await self.store.insert_one("task_contracts", contract.model_dump(by_alias=True))
        return contract

    async def get_contract(self, task_id: str) -> Optional[TaskContract]:
        docs = await self.store.find_many("task_contracts", {"task_id": task_id}, limit=1)
        return TaskContract.model_validate(docs[0]) if docs else None

    async def check(self, contract: TaskContract, current_action: str) -> dict:
        result = await self._check_with_model(contract, current_action)
        derivation = "llm"
        if result is None:
            derivation = "deterministic_fallback"
            result = self._check_fallback(contract, current_action)
        aligned, severity, reason = result
        return {
            "aligned": aligned,
            "severity": severity,
            "reason": reason,
            "contract_goal": contract.original_goal,
            "derivation": derivation,
        }

    async def _check_with_model(self, contract: TaskContract, action: str) -> Optional[tuple[bool, str, str]]:
        if self.gateway is None:
            return None
        if "local-deterministic" in str(getattr(self.gateway, "configured_models", {})):
            return None
        user = (
            f"CONTRACT\n"
            f"  original_goal: {contract.original_goal}\n"
            f"  approved_scope: {contract.approved_scope or '(not specified)'}\n"
            f"  forbidden_actions: {', '.join(contract.forbidden_actions) or '(none)'}\n\n"
            f"CURRENT ACTION\n  {action}\n"
        )
        try:
            res = await self.gateway.chat(system=DRIFT_SYSTEM_PROMPT, user=user, temperature=0.1, max_tokens=250)
        except Exception:
            return None
        parsed = self._parse_json(getattr(res, "content", "") or "")
        if not parsed:
            return None
        aligned = bool(parsed.get("aligned"))
        severity = str(parsed.get("severity", "none")).strip().lower()
        if severity not in {"none", "minor", "major"}:
            severity = "none" if aligned else "major"
        reason = str(parsed.get("reason", "")).strip()
        if not reason:
            return None
        return (aligned, severity, reason)

    @staticmethod
    def _parse_json(content: str) -> Optional[dict]:
        content = content.strip()
        if content.startswith("```"):
            content = content.strip("`")
            if content.lower().startswith("json"):
                content = content[4:]
        start = content.find("{"); end = content.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            return json.loads(content[start:end + 1])
        except json.JSONDecodeError:
            return None

    def _check_fallback(self, contract: TaskContract, action: str) -> tuple[bool, str, str]:
        """Deterministic, offline-safe heuristic: keyword overlap between goal and action,
        plus an explicit forbidden-action check. Used only when no live model is available."""
        a = action.lower()
        for f in contract.forbidden_actions:
            if f and f.lower() in a:
                return (False, "major", f"Action matches a forbidden action in the contract: {f}.")
        goal_words = {w for w in contract.original_goal.lower().replace(",", " ").split() if len(w) > 3}
        scope_words = {w for w in contract.approved_scope.lower().replace(",", " ").split() if len(w) > 3}
        ref = goal_words | scope_words
        action_words = {w for w in a.replace(",", " ").split() if len(w) > 3}
        overlap = len(ref & action_words)
        if overlap == 0 and ref:
            return (False, "major", "The action shares no terms with the original goal or approved scope, indicating the agent has moved to a different task.")
        if overlap == 1 and len(ref) > 3:
            return (False, "minor", "The action only weakly overlaps with the original goal; it may be straying from the task.")
        return (True, "none", "The action overlaps with the original goal and approved scope and appears to continue the task.")
