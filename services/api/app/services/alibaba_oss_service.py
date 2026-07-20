from __future__ import annotations

"""Alibaba Cloud Object Storage Service (OSS) integration.

TraceMemory's Execution Receipts (Ed25519-signed, hash-chained proofs of what
an agent run actually did) are the artifact most worth keeping durable and
tamper-evident beyond the lifetime of any single container. This service
archives finalised receipts to an Alibaba Cloud OSS bucket using Alibaba's
official `oss2` SDK, giving the receipt a second, independently-verifiable
home outside the application database.

This is a real, functional integration (not a deployment-only gesture): if
ALIBABA_ACCESS_KEY_ID / ALIBABA_ACCESS_KEY_SECRET / ALIBABA_OSS_BUCKET are
configured, every finalised receipt is written to OSS as
`receipts/{task_id}/{receipt_hash}.json` and the resulting OSS object URL is
attached to the receipt response. If not configured, archival is skipped
cleanly and the rest of the system is unaffected — mirroring the
provider-agnostic, keyless-demo-friendly pattern used by the model gateways.
"""

import json
from typing import Any

from app.config import Settings

try:
    import oss2  # type: ignore
except ImportError:  # pragma: no cover - oss2 is an optional dependency
    oss2 = None  # type: ignore


class AlibabaOSSService:
    """Archives signed Execution Receipts to Alibaba Cloud OSS."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._bucket = None
        if self.enabled and oss2 is not None:
            auth = oss2.Auth(
                self.settings.alibaba_access_key_id,
                self.settings.alibaba_access_key_secret,
            )
            self._bucket = oss2.Bucket(
                auth,
                self.settings.alibaba_oss_endpoint,
                self.settings.alibaba_oss_bucket,
            )

    @property
    def enabled(self) -> bool:
        return bool(
            self.settings.alibaba_access_key_id
            and self.settings.alibaba_access_key_secret
            and self.settings.alibaba_oss_bucket
        )

    @property
    def operational(self) -> bool:
        return self.enabled and oss2 is not None and self._bucket is not None

    def archive_receipt(self, task_id: str, receipt_hash: str, receipt: dict[str, Any]) -> str | None:
        """Uploads a finalised receipt to OSS. Returns the object URL, or None if not configured."""
        if not self.operational:
            return None
        key = f"receipts/{task_id}/{receipt_hash}.json"
        body = json.dumps(receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self._bucket.put_object(key, body, headers={"Content-Type": "application/json"})
        return f"https://{self.settings.alibaba_oss_bucket}.{self.settings.alibaba_oss_endpoint.split('://')[-1]}/{key}"

    def fetch_receipt(self, task_id: str, receipt_hash: str) -> dict[str, Any] | None:
        """Reads a previously archived receipt back from OSS, for offline/third-party verification."""
        if not self.operational:
            return None
        key = f"receipts/{task_id}/{receipt_hash}.json"
        result = self._bucket.get_object(key)
        return json.loads(result.read())
