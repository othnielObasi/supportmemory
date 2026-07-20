from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class GatewayAttempt:
    model: str
    role: str
    status: str
    latency_ms: int
    error: Optional[str] = None


@dataclass
class GatewayResult:
    content: str
    provider: str
    model: str
    used_fallback: bool
    attempts: list[GatewayAttempt]
