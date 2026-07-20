from __future__ import annotations

import json

from cryptography.fernet import Fernet, InvalidToken

from app.config import Settings


class IntegrationCredentialVault:
    """Encrypt connector credentials before they reach the document store."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._key = settings.integration_encryption_key

    def _fernet(self) -> Fernet:
        if not self._key:
            raise RuntimeError("INTEGRATION_ENCRYPTION_KEY is required to store connector credentials")
        try:
            return Fernet(self._key.encode("ascii"))
        except (ValueError, UnicodeError) as exc:
            raise RuntimeError("INTEGRATION_ENCRYPTION_KEY must be a valid Fernet key") from exc

    def encrypt(self, credentials: dict[str, str]) -> str:
        payload = json.dumps(credentials, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return self._fernet().encrypt(payload).decode("ascii")

    def decrypt(self, ciphertext: str) -> dict[str, str]:
        try:
            raw = self._fernet().decrypt(ciphertext.encode("ascii"))
            value = json.loads(raw)
        except (InvalidToken, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError("Connector credentials could not be decrypted") from exc
        if not isinstance(value, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
            raise RuntimeError("Stored connector credentials are invalid")
        return value
