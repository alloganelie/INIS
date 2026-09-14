"""Stable actor pseudonymization (GDPR Art. 17 support, §41.9).

One-way SHA-256 over ``salt + actor_id``: deterministic (the same
actor always maps to the same pseudonym, preserving joinability of
provenance chains) and irreversible. The salt MUST come from
``[CONFIG]``/secret store in production; the built-in default is for
development and tests only.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

DEV_SALT = "inis-dev-salt"
PSEUDONYM_PREFIX = "PSN_"


class Pseudonymizer:
    """Hash-based pseudonymizer with a configured salt."""

    def __init__(self, salt: str = DEV_SALT) -> None:
        if not salt or not isinstance(salt, str):
            raise ValueError("salt must be a non-empty string")
        self._salt = salt

    @classmethod
    def with_random_salt(cls) -> "Pseudonymizer":
        """Build an instance with a fresh random salt."""
        return cls(salt=secrets.token_hex(16))

    def pseudonymize(self, actor_id: str) -> str:
        """Return the stable pseudonym for ``actor_id``."""
        if not actor_id or not isinstance(actor_id, str):
            raise ValueError("actor_id must be a non-empty string")
        digest = hashlib.sha256(f"{self._salt}:{actor_id}".encode("utf-8")).hexdigest()
        return f"{PSEUDONYM_PREFIX}{digest[:32]}"

    def verify(self, actor_id: str, pseudonym: str) -> bool:
        """Return True when ``pseudonym`` matches ``actor_id``."""
        if not actor_id or not pseudonym:
            return False
        return hmac.compare_digest(self.pseudonymize(actor_id), pseudonym)
