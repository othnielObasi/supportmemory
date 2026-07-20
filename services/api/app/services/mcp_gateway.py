from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from app.config import Settings
from app.models.schemas import stable_hash


@dataclass
class MCPToolAttempt:
    tool_name: str
    status: str
    latency_ms: int
    endpoint: str
    error: Optional[str] = None


@dataclass
class MCPToolResult:
    provider: str
    tool_name: str
    enabled: bool
    output: dict[str, Any]
    validation: dict[str, Any]
    observed_signals: dict[str, Any]
    attempts: list[MCPToolAttempt]


class MCPGatewayService:
    """Adapter for routing agent tool calls through MCP-compatible Tool Gateway.

    The hackathon product story is strongest when both model calls and tool calls
    are gateway-visible. This service gives TraceMemory a single tool-call path:

        TraceMemory Agent -> MCP-compatible Tool Gateway -> Tool/API

    If MCP credentials are not configured, it returns a deterministic local result
    with the same shape so the demo remains reproducible during development.
    """

    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return bool(self.settings.effective_mcp_gateway_url and self.settings.effective_mcp_gateway_api_key)

    def _endpoint(self, tool_name: str) -> str:
        base = (self.settings.effective_mcp_gateway_url or "").rstrip("/")
        path = self.settings.effective_mcp_tool_invoke_path.format(tool_name=tool_name).lstrip("/")
        return f"{base}/{path}"

    async def call_tool(
        self,
        *,
        tool_name: str,
        payload: dict[str, Any],
        force_fail: bool = False,
    ) -> MCPToolResult:
        if force_fail:
            return await self._simulated_failure(tool_name=tool_name, payload=payload)

        if not self.enabled:
            return self._local_tool_result(tool_name=tool_name, payload=payload)

        endpoint = self._endpoint(tool_name)
        started = time.perf_counter()
        headers = {
            "Authorization": f"Bearer {self.settings.effective_mcp_gateway_api_key}",
            "Content-Type": "application/json",
            "X-TraceMemory-Tool": tool_name,
        }
        body = {
            "tool": tool_name,
            "input": payload,
            "metadata": {
                "source": "tracememory",
                "idempotency_hash": stable_hash({"tool": tool_name, "input": payload}),
            },
        }
        try:
            async with httpx.AsyncClient(timeout=self.settings.gateway_timeout_seconds) as client:
                response = await client.post(endpoint, headers=headers, json=body)
                response.raise_for_status()
                data = response.json()
            latency_ms = int((time.perf_counter() - started) * 1000)
            output = data.get("output", data)
            return MCPToolResult(
                provider="MCP-compatible Tool Gateway",
                tool_name=tool_name,
                enabled=True,
                output=output,
                validation={"passed": True, "source": "mcp_gateway", "condition": "tool call returned successfully"},
                observed_signals={"endpoint": endpoint, "output_hash": stable_hash(output)},
                attempts=[MCPToolAttempt(tool_name=tool_name, status="success", latency_ms=latency_ms, endpoint=endpoint)],
            )
        except Exception as exc:  # noqa: BLE001 - surfaced in trace for auditability.
            latency_ms = int((time.perf_counter() - started) * 1000)
            local = self._local_tool_result(tool_name=tool_name, payload=payload)
            local.provider = "local-tool-fallback-after-mcp-error"
            local.attempts.insert(0, MCPToolAttempt(tool_name=tool_name, status="failed", latency_ms=latency_ms, endpoint=endpoint, error=str(exc)[:500]))
            local.validation["mcp_error_recovered"] = True
            return local

    async def _simulated_failure(self, *, tool_name: str, payload: dict[str, Any]) -> MCPToolResult:
        local = self._local_tool_result(tool_name=tool_name, payload=payload)
        local.provider = "local-tool-fallback-after-simulated-mcp-error"
        local.attempts.insert(0, MCPToolAttempt(tool_name=tool_name, status="simulated_failure", latency_ms=0, endpoint=self._endpoint(tool_name) if self.enabled else "mcp-not-configured", error="Intentional MCP tool failure for resilience demo."))
        local.validation["simulated_failure_recovered"] = True
        return local

    def _local_tool_result(self, *, tool_name: str, payload: dict[str, Any]) -> MCPToolResult:
        customer = payload.get("customer_id") or payload.get("ticket_id") or "ACME-1024"
        output = {
            "tool_name": tool_name,
            "customer_id": customer,
            "ticket_count": 3,
            "highest_severity": "high",
            "signals": [
                "deployment failed after config drift",
                "retry succeeded after rollback",
                "no customer PII included in demo payload",
            ],
            "next_page_token": None,
        }
        return MCPToolResult(
            provider="deterministic-local-tool" if not self.enabled else "deterministic-local-tool-fallback",
            tool_name=tool_name,
            enabled=self.enabled,
            output=output,
            validation={
                "passed": True,
                "condition": "tool output contains no next_page_token before final answer",
                "safe_for_model_context": True,
            },
            observed_signals={
                "items_count": output["ticket_count"],
                "next_page_token": output["next_page_token"],
                "output_hash": stable_hash(output),
            },
            attempts=[MCPToolAttempt(tool_name=tool_name, status="local_success", latency_ms=0, endpoint="local-demo-tool")],
        )

    def attempts_as_dicts(self, attempts: list[MCPToolAttempt]) -> list[dict[str, Any]]:
        return [attempt.__dict__ for attempt in attempts]
