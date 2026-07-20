"""LangGraph adapter for TraceMemory.

The adapter is dependency-light by design: it does not import LangGraph at module
load time, but exposes the methods needed to wrap graph nodes and persist
node-level checkpoints. Projects using LangGraph can use `wrap_node()` around
node functions or build a LangGraph checkpointer from this class.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, Optional

from ..client import TraceMemoryClient


class TraceMemoryLangGraphAdapter:
    """Records LangGraph-like node transitions into TraceMemory."""

    def __init__(self, client: TraceMemoryClient, task_id: str, graph_name: str = "langgraph"):
        self.client = client
        self.task_id = task_id
        self.graph_name = graph_name

    def wrap_node(self, node_name: str, fn: Callable[[Dict[str, Any]], Dict[str, Any]]):
        """Wrap a LangGraph node function.

        The wrapper records node start, runs the node, saves a checkpoint with
        input/output state, then records node completion.
        """

        def wrapped(state: Dict[str, Any]) -> Dict[str, Any]:
            self.client.record_event(
                self.task_id,
                "tool_execution_started",
                {"framework": "langgraph", "graph": self.graph_name, "node": node_name},
            )
            result = fn(state)
            checkpoint = self.client.save_checkpoint(
                self.task_id,
                checkpoint_name=f"{self.graph_name}.{node_name}.complete",
                state={"input_state": state, "output_state": result},
                resume_state={"current_step": f"after:{node_name}", "pending_actions": []},
                metadata={"framework": "langgraph", "graph": self.graph_name, "node": node_name},
            )
            self.client.record_event(
                self.task_id,
                "checkpoint_saved",
                {"framework": "langgraph", "node": node_name, "checkpoint": checkpoint},
            )
            return result

        return wrapped

    def restore_state(self, checkpoint_id: str) -> Dict[str, Any]:
        """Restore a checkpoint and return the resume state for graph execution."""

        restored = self.client.restore_checkpoint(checkpoint_id)
        resume_state = restored.get("resume_state") or restored.get("state", {}).get("resume_state") or {}
        self.client.record_event(
            self.task_id,
            "checkpoint_restored",
            {"framework": "langgraph", "checkpoint_id": checkpoint_id},
        )
        return resume_state

    def wrap_edges(self, edges: Iterable[str]) -> None:
        """Record graph topology hints without requiring LangGraph internals."""

        self.client.record_event(
            self.task_id,
            "plan_prepared",
            {"framework": "langgraph", "graph": self.graph_name, "edges": list(edges)},
        )


# Backwards-compatible name used by earlier repo revisions.
TraceMemoryCheckpointer = TraceMemoryLangGraphAdapter
