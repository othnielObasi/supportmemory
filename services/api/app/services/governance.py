from __future__ import annotations

import copy
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.config import Settings
from app.models.schemas import Decision, GovernanceDecision, ToolType

PII_RULES: List[Tuple[str, re.Pattern[str], str]] = [
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED_SSN]"),
    ("card", re.compile(r"\b\d{4}-\d{4}-\d{4}-\d{4}\b"), "[REDACTED_CARD]"),
    ("email", re.compile(r"[\w\.-]+@[\w\.-]+\.\w+"), "[REDACTED_EMAIL]"),
    ("phone", re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"), "[REDACTED_PHONE]"),
]

# Back-compat alias used by older imports/tests
PII_PATTERNS: Iterable[re.Pattern[str]] = [pattern for _, pattern, _ in PII_RULES]


class GovernanceService:
    """Customizable Runtime Governor — policy gate before tool execution.

    Default hybrid PII policy (SupportMemory):
      - reads / internal tools → redact PII, then allow
      - external actions (send_*, refund_*, …) → block or require_approval

    Configure via env:
      RUNTIME_GOVERNOR_PII_MODE=hybrid|redact|block|require_approval
      RUNTIME_GOVERNOR_EXTERNAL_PII_MODE=block|require_approval
    """

    WRITE_PREFIXES = ("write_", "update_", "delete_", "approve_", "create_", "send_", "refund_", "payout_")
    EXTERNAL_PREFIXES = ("send_", "refund_", "approve_", "payout_", "wire_", "transfer_")

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or Settings()
        self.mode = (getattr(self.settings, "runtime_governor_mode", None) or "local").lower()
        # Product default: hybrid (redact internal, strict external)
        self.pii_mode = (getattr(self.settings, "runtime_governor_pii_mode", None) or "hybrid").lower()
        self.external_pii_mode = (
            getattr(self.settings, "runtime_governor_external_pii_mode", None) or "require_approval"
        ).lower()
        self.block_unknown_tools = bool(getattr(self.settings, "runtime_governor_block_unknown_tools", False))
        raw_allow = getattr(self.settings, "runtime_governor_tool_allowlist", "") or ""
        self.tool_allowlist = {t.strip() for t in raw_allow.split(",") if t.strip()}

    def policy_summary(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "pii_mode": self.pii_mode,
            "external_pii_mode": self.external_pii_mode,
            "block_unknown_tools": self.block_unknown_tools,
            "tool_allowlist": sorted(self.tool_allowlist),
            "pii_detectors": [name for name, _, _ in PII_RULES],
            "external_tool_prefixes": list(self.EXTERNAL_PREFIXES),
            "behaviors": {
                "hybrid": "Redact PII on reads/internal tools; block or require_approval on external actions",
                "redact": "Detect PII → replace with tokens → allow (all tool types)",
                "block": "Detect PII on non-read tools → block the call",
                "require_approval": "Detect PII → needs_approval + human review",
            },
        }

    def evaluate_tool_call(
        self,
        tool_name: str,
        args: Dict[str, Any],
        task_context: Dict[str, Any],
    ) -> GovernanceDecision:
        tool_type = self._tool_type(tool_name, task_context)
        is_external = self._is_external_action(tool_name, tool_type)
        pii_hits = self.detect_pii(args)
        redacted_args, redacted = self.redact_pii(args) if pii_hits else (args, False)

        if self.tool_allowlist and tool_name not in self.tool_allowlist:
            return GovernanceDecision(
                decision=Decision.blocked,
                risk_score=88,
                reason=f"Tool '{tool_name}' is outside the Runtime Governor allowlist.",
                policy_flags=["tool_not_allowlisted", "action_blocked"],
                tool_type=tool_type,
                requires_human_review=True,
                redacted_args=None,
                pii_mode_applied=self.pii_mode,
                pii_types_detected=pii_hits,
            )

        if pii_hits:
            pii_decision = self._apply_pii_policy(
                tool_name=tool_name,
                tool_type=tool_type,
                is_external=is_external,
                args=args,
                redacted_args=redacted_args if redacted else args,
                pii_hits=pii_hits,
            )
            if pii_decision is not None:
                return pii_decision

        if tool_type == ToolType.read:
            return GovernanceDecision(
                decision=Decision.allowed,
                risk_score=12,
                reason="Read-only retrieval is within task scope.",
                policy_flags=["read_only"],
                tool_type=tool_type,
                requires_human_review=False,
                pii_mode_applied=self.pii_mode,
                pii_types_detected=pii_hits,
            )

        if tool_type in {ToolType.write, ToolType.external_action} or is_external:
            if not task_context.get("idempotency_key"):
                return GovernanceDecision(
                    decision=Decision.needs_approval,
                    risk_score=72,
                    reason="Action-taking tools require an idempotency key and human/policy approval.",
                    policy_flags=["approval_required", "idempotency_required"],
                    tool_type=tool_type,
                    requires_human_review=True,
                    pii_mode_applied=self.pii_mode,
                    pii_types_detected=pii_hits,
                )
            return GovernanceDecision(
                decision=Decision.needs_approval,
                risk_score=65,
                reason="Action-taking tool requires approval before execution.",
                policy_flags=["approval_required"],
                tool_type=tool_type,
                requires_human_review=True,
                pii_mode_applied=self.pii_mode,
                pii_types_detected=pii_hits,
            )

        if self.block_unknown_tools:
            return GovernanceDecision(
                decision=Decision.blocked,
                risk_score=80,
                reason="Unknown tool blocked by Runtime Governor policy.",
                policy_flags=["unknown_tool", "action_blocked"],
                tool_type=tool_type,
                requires_human_review=True,
                pii_mode_applied=self.pii_mode,
                pii_types_detected=pii_hits,
            )

        return GovernanceDecision(
            decision=Decision.needs_approval,
            risk_score=70,
            reason="Unknown tool requires review.",
            policy_flags=["unknown_tool"],
            tool_type=tool_type,
            requires_human_review=True,
            pii_mode_applied=self.pii_mode,
            pii_types_detected=pii_hits,
        )

    def _apply_pii_policy(
        self,
        *,
        tool_name: str,
        tool_type: ToolType,
        is_external: bool,
        args: Dict[str, Any],
        redacted_args: Dict[str, Any],
        pii_hits: List[str],
    ) -> Optional[GovernanceDecision]:
        mode = self.pii_mode

        # Global override modes
        if mode == "block" and tool_type != ToolType.read:
            return self._block_pii(tool_type, redacted_args, pii_hits)
        if mode == "require_approval" and tool_type != ToolType.read:
            return self._approve_pii(tool_type, redacted_args, pii_hits)
        if mode == "redact":
            return self._redact_allow(tool_type, redacted_args, pii_hits, scope="all_tools")

        # Default / hybrid: redact reads + internal; strict on external
        if mode in {"hybrid", "redact_internal", "default"}:
            if is_external:
                if self.external_pii_mode == "block":
                    return self._block_pii(
                        tool_type,
                        redacted_args,
                        pii_hits,
                        extra_flags=["external_action", f"tool:{tool_name}"],
                        reason="PII detected on external action; Runtime Governor blocked the call.",
                    )
                return self._approve_pii(
                    tool_type,
                    redacted_args,
                    pii_hits,
                    extra_flags=["external_action", f"tool:{tool_name}"],
                    reason="PII detected on external action; Runtime Governor requires human approval.",
                )
            # reads + internal writes
            return self._redact_allow(
                tool_type,
                redacted_args,
                pii_hits,
                scope="read_or_internal",
            )

        # Fallback for unknown mode names: behave like hybrid
        if is_external:
            return self._approve_pii(tool_type, redacted_args, pii_hits, extra_flags=["external_action"])
        return self._redact_allow(tool_type, redacted_args, pii_hits, scope="read_or_internal")

    def _redact_allow(
        self,
        tool_type: ToolType,
        redacted_args: Dict[str, Any],
        pii_hits: List[str],
        *,
        scope: str,
    ) -> GovernanceDecision:
        return GovernanceDecision(
            decision=Decision.allowed,
            risk_score=42 if tool_type == ToolType.read else 48,
            reason="PII detected; Runtime Governor redacted sensitive fields and allowed the call.",
            policy_flags=["pii_detected", "pii_redacted", "action_allowed_after_redaction", f"scope:{scope}"],
            tool_type=tool_type,
            requires_human_review=False,
            redacted_args=redacted_args,
            pii_mode_applied="redact" if self.pii_mode == "redact" else "hybrid_redact_internal",
            pii_types_detected=pii_hits,
        )

    def _block_pii(
        self,
        tool_type: ToolType,
        redacted_args: Dict[str, Any],
        pii_hits: List[str],
        *,
        extra_flags: Optional[List[str]] = None,
        reason: str = "Sensitive data detected in an action-taking tool call.",
    ) -> GovernanceDecision:
        flags = ["pii_detected", "action_blocked", *(extra_flags or [])]
        return GovernanceDecision(
            decision=Decision.blocked,
            risk_score=92,
            reason=reason,
            policy_flags=flags,
            tool_type=tool_type,
            requires_human_review=True,
            redacted_args=redacted_args,
            pii_mode_applied="block" if self.pii_mode == "block" else f"hybrid_external_{self.external_pii_mode}",
            pii_types_detected=pii_hits,
        )

    def _approve_pii(
        self,
        tool_type: ToolType,
        redacted_args: Dict[str, Any],
        pii_hits: List[str],
        *,
        extra_flags: Optional[List[str]] = None,
        reason: str = "PII detected; Runtime Governor requires human approval before the action.",
    ) -> GovernanceDecision:
        flags = ["pii_detected", "approval_required", *(extra_flags or [])]
        return GovernanceDecision(
            decision=Decision.needs_approval,
            risk_score=85,
            reason=reason,
            policy_flags=flags,
            tool_type=tool_type,
            requires_human_review=True,
            redacted_args=redacted_args,
            pii_mode_applied="require_approval"
            if self.pii_mode == "require_approval"
            else f"hybrid_external_{self.external_pii_mode}",
            pii_types_detected=pii_hits,
        )

    def detect_pii(self, value: Any) -> List[str]:
        hits: list[str] = []
        body = self._flatten(value)
        for name, pattern, _ in PII_RULES:
            if pattern.search(body):
                hits.append(name)
        return hits

    def redact_pii(self, value: Any) -> tuple[Any, bool]:
        """Return (redacted_value, did_redact)."""
        changed = False

        def _walk(node: Any) -> Any:
            nonlocal changed
            if isinstance(node, str):
                out = node
                for _, pattern, token in PII_RULES:
                    new_out, n = pattern.subn(token, out)
                    if n:
                        changed = True
                        out = new_out
                return out
            if isinstance(node, list):
                return [_walk(item) for item in node]
            if isinstance(node, dict):
                return {key: _walk(val) for key, val in node.items()}
            return node

        return _walk(copy.deepcopy(value)), changed

    def _is_external_action(self, tool_name: str, tool_type: ToolType) -> bool:
        if tool_type == ToolType.external_action:
            return True
        return tool_name.startswith(self.EXTERNAL_PREFIXES)

    def _flatten(self, value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            return " ".join(self._flatten(v) for v in value.values())
        if isinstance(value, list):
            return " ".join(self._flatten(v) for v in value)
        return str(value)

    def _tool_type(self, tool_name: str, task_context: Dict[str, Any]) -> ToolType:
        if "tool_type" in task_context:
            try:
                return ToolType(task_context["tool_type"])
            except ValueError:
                return ToolType.unknown
        if tool_name.startswith(("fetch_", "search_", "read_", "list_", "get_")):
            return ToolType.read
        if tool_name.startswith(self.EXTERNAL_PREFIXES):
            return ToolType.external_action
        if tool_name.startswith(self.WRITE_PREFIXES):
            return ToolType.write
        return ToolType.unknown
