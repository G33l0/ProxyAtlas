"""Credential protection using Fernet symmetric encryption.

Proxy credentials and provider API keys are encrypted at rest with a key
derived per-install (or supplied via ``PROXYATLAS_SECRET_KEY``). The key file
is written with restrictive permissions. Credentials are never logged.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import stat
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from app.core.exceptions import SecurityError

logger = logging.getLogger(__name__)


def _derive_key_from_secret(secret: str) -> bytes:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


class CredentialCipher:
    """Encrypt/decrypt short secrets. Empty values pass through as empty."""

    def __init__(self, key: bytes) -> None:
        self._fernet = Fernet(key)

    @classmethod
    def from_key_file(cls, key_path: Path) -> "CredentialCipher":
        """Load or create a key. Env override takes precedence."""
        env_secret = os.environ.get("PROXYATLAS_SECRET_KEY")
        if env_secret:
            return cls(_derive_key_from_secret(env_secret))

        if key_path.exists():
            key = key_path.read_bytes().strip()
        else:
            key = Fernet.generate_key()
            key_path.parent.mkdir(parents=True, exist_ok=True)
            key_path.write_bytes(key)
            try:
                key_path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600
            except OSError:  # pragma: no cover - windows/permission quirks
                logger.debug("Could not chmod key file")
        try:
            return cls(key)
        except (ValueError, TypeError) as exc:
            raise SecurityError("Invalid encryption key") from exc

    def encrypt(self, plaintext: str | None) -> str | None:
        if plaintext is None or plaintext == "":
            return plaintext
        token = self._fernet.encrypt(plaintext.encode("utf-8"))
        return token.decode("ascii")

    def decrypt(self, token: str | None) -> str | None:
        if token is None or token == "":
            return token
        try:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError) as exc:
            raise SecurityError("Failed to decrypt credential") from exc
