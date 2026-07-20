"""Framework-neutral tool wrappers for TraceMemory.

These helpers are intentionally dependency-free. They let developers wrap any
Python function used as an agent tool and automatically persist tool traces,
validation signals, checkpoints, and optional idempotent action execution.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, TypeVar, cast

from ..client import TraceMemoryClient

F = TypeVar("F", bound=Callable[..., Any])


@dataclass
class ToolWrapperConfig:
    """Configuration for wrapping an agent tool.

    Args:
        tool_name: Stable tool name to show in TraceMemory.
        tool_type: "read", "write", "external_action", or "unknown".
        checkpoint_after: Save a checkpoint after successful execution.
        checkpoint_name: Optional custom checkpoint name.
        validation: Static validation metadata or a callable returning validation.
        observed_signals: Static observed signals or a callable returning signals.
        idempotency_key: Optional static key or callable for action tools.
    """

    tool_name: str
    tool_type: str = "read"
    checkpoint_after: bool = False
    checkpoint_name: Optional[str] = None
    validation: Any = field(default_factory=dict)
    observed_signals: Any = field(default_factory=dict)
    idempotency_key: Any = None


def _to_dict(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    return {"value": value}


def _resolve(value: Any, *, args: tuple[Any, ...], kwargs: Dict[str, Any], result: Any = None) -> Any:
    if callable(value):
        return value(args=args, kwargs=kwargs, result=result)
    return value


def trace_tool(client: TraceMemoryClient, task_id: str, config: ToolWrapperConfig) -> Callable[[F], F]:
    """Wrap a function and record its execution as a TraceMemory tool trace.

    This is the lowest-friction adapter for custom agents. It works with any
    framework because it wraps a normal Python callable.
    """

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            input_payload = {"args": list(args), "kwargs": kwargs}
            idempotency_key = _resolve(config.idempotency_key, args=args, kwargs=kwargs)

            if config.tool_type in {"write", "external_action"} and idempotency_key:
                action = client.execute_action(
                    task_id=task_id,
                    tool_name=config.tool_name,
                    tool_type=config.tool_type,
                    idempotency_key=str(idempotency_key),
                    input=input_payload,
                )
                if action.get("replayed") or action.get("duplicate"):
                    return action.get("result", action)

            result = fn(*args, **kwargs)
            validation = _to_dict(_resolve(config.validation, args=args, kwargs=kwargs, result=result))
            observed_signals = _to_dict(_resolve(config.observed_signals, args=args, kwargs=kwargs, result=result))

            client.record_tool_trace(
                task_id=task_id,
                tool=config.tool_name,
                tool_type=config.tool_type,
                input=input_payload,
                output=_to_dict(result),
                validation=validation,
                observed_signals=observed_signals,
                idempotency_key=str(idempotency_key) if idempotency_key else None,
            )

            if config.checkpoint_after:
                client.save_checkpoint(
                    task_id=task_id,
                    checkpoint_name=config.checkpoint_name or f"{config.tool_name}_complete",
                    state={"tool": config.tool_name, "result": _to_dict(result)},
                    resume_state={"current_step": f"after_{config.tool_name}", "pending_actions": []},
                    metadata={"source": "trace_tool", "tool_type": config.tool_type},
                )

            return result

        return cast(F, wrapped)

    return decorator
