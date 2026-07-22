from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any, Optional

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization

from app.db.postgres import PostgresStore, DESCENDING


RECEIPT_VERSION = "tracememory.receipt/v1"


def _canonical(obj: Any) -> bytes:
    """Deterministic JSON encoding: sorted keys, no whitespace, UTF-8.
    Verifiers must reproduce this exactly to recompute the hash."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


class ReceiptService:
    """Assembles a portable, signed Execution Receipt for a run.

    A receipt is a self-contained, independently verifiable record:
      task contract + execution trace + tool evidence + checkpoints +
      drift verdict + recovery event + memory applied.
    It is hashed (SHA-256) over a canonical encoding and signed with Ed25519.
    Anyone holding the public key can verify it offline, without trusting the server.
    """

    def __init__(self, store: PostgresStore, key_path: str = "/tmp/tracememory_ed25519.key", settings: Any = None):
        self.store = store
        self.settings = settings
        self._key_path = Path(key_path)
        self._private_key = self._load_or_create_key()

    def _load_or_create_key(self) -> Ed25519PrivateKey:
        # Prefer an env-provided key; otherwise persist one to disk for demo stability.
        env_key = None
        if self.settings is not None:
            env_key = getattr(self.settings, "receipt_signing_key_b64", None)
        if env_key:
            raw = base64.b64decode(env_key)
            return Ed25519PrivateKey.from_private_bytes(raw)
        if self._key_path.exists():
            raw = self._key_path.read_bytes()
            return Ed25519PrivateKey.from_private_bytes(raw)
        key = Ed25519PrivateKey.generate()
        raw = key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
        try:
            self._key_path.write_bytes(raw)
        except OSError:
            pass
        return key

    def public_key_b64(self) -> str:
        pub = self._private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
        )
        return base64.b64encode(pub).decode("ascii")

    async def build(self, trace_id: str) -> Optional[dict]:
        trace = await self.store.find_one("execution_traces", trace_id)
        if not trace:
            return None
        task_id = trace.get("task_id")

        contracts = await self.store.find_many("task_contracts", {"task_id": task_id}, limit=1)
        checkpoints = await self.store.find_many("task_checkpoints", {"task_id": task_id}, limit=25, sort=[("created_at", DESCENDING)])
        reflections = await self.store.find_many("reflection_insights", {"source_trace_id": trace_id}, limit=10, sort=[("created_at", DESCENDING)])
        retrievals = await self.store.find_many("retrieval_events", {"trace_id": trace_id}, limit=10, sort=[("created_at", DESCENDING)])
        context_receipts = await self.store.find_many(
            "context_receipts",
            {
                "task": trace.get("task_description"),
                "organisation_id": trace.get("organisation_id", "org_default"),
                "workspace_id": trace.get("workspace_id", "wrk_default"),
            },
            limit=5,
            sort=[("created_at", DESCENDING)],
        )

        contract = contracts[0] if contracts else None

        # Assemble the receipt body (the signed-over content).
        body = {
            "receipt_version": RECEIPT_VERSION,
            "task_id": task_id,
            "trace_id": trace_id,
            "agent_id": trace.get("agent_id"),
            "task_contract": None if not contract else {
                "original_goal": contract.get("original_goal"),
                "approved_scope": contract.get("approved_scope"),
                "forbidden_actions": contract.get("forbidden_actions", []),
                "task_version": contract.get("task_version", 1),
            },
            "execution": {
                "status": trace.get("status"),
                "failure_type": trace.get("failure_type"),
                "tool_calls": [
                    {"tool": getattr2(tc, "tool", "name"), "status": getattr2(tc, "status")}
                    for tc in trace.get("tool_calls", [])
                ],
                "final_output_sha256": hashlib.sha256(str(trace.get("final_output", "")).encode("utf-8")).hexdigest(),
            },
            "checkpoints": [{"id": c.get("_id") or c.get("id"), "created_at": _iso(c.get("created_at"))} for c in checkpoints],
            "recovery": {
                "recovered": str(trace.get("status", "")).lower().find("recover") >= 0,
            },
            "memory": [
                {"candidate_rule": r.get("candidate_rule"), "confidence": r.get("confidence"), "derivation": r.get("derivation")}
                for r in reflections
            ],
            "retrieval": [
                {
                    "rules": [rule.get("rule_id") for rule in event.get("retrieved_rules", [])],
                    "kb_chunks": [hit.get("chunk_id") for hit in event.get("kb_hits", [])],
                    "graph_path_hashes": [hashlib.sha256(_canonical(path)).hexdigest() for path in event.get("graph_paths", [])],
                    "embedding_provider": event.get("embedding_provider"),
                }
                for event in retrievals
            ],
            "context_health_receipts": [r.get("receipt_id") or r.get("_id") for r in context_receipts],
        }

        canonical = _canonical(body)
        content_hash = hashlib.sha256(canonical).hexdigest()
        signature = self._private_key.sign(canonical)

        return {
            "receipt": body,
            "content_sha256": content_hash,
            "signature_ed25519_b64": base64.b64encode(signature).decode("ascii"),
            "public_key_ed25519_b64": self.public_key_b64(),
            "verification": {
                "algorithm": "Ed25519",
                "canonicalization": "JSON sort_keys=true, separators=(',',':'), UTF-8",
                "instructions": "Recompute SHA-256 over the canonical encoding of the 'receipt' object; verify 'signature_ed25519_b64' against it using 'public_key_ed25519_b64'.",
            },
        }


def getattr2(obj: Any, *names):
    for n in names:
        if not isinstance(n, str):
            continue
        if isinstance(obj, dict) and n in obj:
            return obj[n]
        if hasattr(obj, n):
            return getattr(obj, n)
    return None


def _iso(v):
    try:
        return v.isoformat()
    except AttributeError:
        return str(v) if v is not None else None
