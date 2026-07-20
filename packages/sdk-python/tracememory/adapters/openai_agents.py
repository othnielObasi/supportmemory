"""OpenAI Agents SDK style middleware for TraceMemory.

The implementation avoids importing the OpenAI Agents SDK directly. It exposes a
small middleware/wrapper API that can wrap tool callables or lifecycle hooks in
projects using the SDK.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from ..client import TraceMemoryClient
from .tool_wrapper import ToolWrapperConfig, trace_tool


class TraceMemoryOpenAIAgentsMiddleware:
    """TraceMemory middleware for OpenAI Agents SDK style applications."""

    def __init__(self, client: TraceMemoryClient, task_id: str, agent_id: str):
        self.client = client
        self.task_id = task_id
        self.agent_id = agent_id

    def on_agent_start(self, instructions: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self.client.record_event(
            self.task_id,
            "request_received",
            {"framework": "openai-agents", "agent_id": self.agent_id, "instructions": instructions, "metadata": metadata or {}},
        )

    def on_plan(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        return self.client.record_event(
            self.task_id,
            "plan_prepared",
            {"framework": "openai-agents", "agent_id": self.agent_id, "plan": plan},
        )

    def wrap_tool(self, tool_name: str, fn: Callable[..., Any], tool_type: str = "read") -> Callable[..., Any]:
        return trace_tool(
            self.client,
            self.task_id,
            ToolWrapperConfig(tool_name=tool_name, tool_type=tool_type, checkpoint_after=tool_type == "read"),
        )(fn)

    def on_final_answer(self, answer: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self.client.record_event(
            self.task_id,
            "final_answer",
            {"framework": "openai-agents", "agent_id": self.agent_id, "answer": answer, "metadata": metadata or {}},
        )
