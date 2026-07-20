"""CrewAI adapter for TraceMemory.

CrewAI tasks and tools vary by project, so this adapter provides dependency-free
wrappers that can be used around task callbacks or tool functions.
"""

from __future__ import annotations

from typing import Any, Callable, Dict

from ..client import TraceMemoryClient
from .tool_wrapper import ToolWrapperConfig, trace_tool


class TraceMemoryCrewAIAdapter:
    """Records CrewAI task execution and tool calls into TraceMemory."""

    def __init__(self, client: TraceMemoryClient, task_id: str, crew_name: str = "crew"):
        self.client = client
        self.task_id = task_id
        self.crew_name = crew_name

    def wrap_task(self, task_name: str, fn: Callable[..., Any]) -> Callable[..., Any]:
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            self.client.record_event(
                self.task_id,
                "plan_prepared",
                {"framework": "crewai", "crew": self.crew_name, "task": task_name},
            )
            result = fn(*args, **kwargs)
            self.client.save_checkpoint(
                self.task_id,
                checkpoint_name=f"{self.crew_name}.{task_name}.complete",
                state={"task": task_name, "result": result if isinstance(result, dict) else {"value": str(result)}},
                resume_state={"current_step": f"after:{task_name}", "pending_actions": []},
                metadata={"framework": "crewai", "crew": self.crew_name, "task": task_name},
            )
            return result

        return wrapped

    def wrap_tool(self, tool_name: str, fn: Callable[..., Any], tool_type: str = "read") -> Callable[..., Any]:
        return trace_tool(
            self.client,
            self.task_id,
            ToolWrapperConfig(tool_name=tool_name, tool_type=tool_type, checkpoint_after=False),
        )(fn)

    def record_handoff(self, from_agent: str, to_agent: str, context: Dict[str, Any]) -> Dict[str, Any]:
        return self.client.record_event(
            self.task_id,
            "task_modified",
            {
                "framework": "crewai",
                "crew": self.crew_name,
                "handoff": {"from": from_agent, "to": to_agent},
                "context": context,
            },
        )
