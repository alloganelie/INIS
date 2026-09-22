"""Password hashing and verification using standard library hashlib and secrets."""

from __future__ import annotations

import hashlib
import hmac
import secrets


class PasswordHasher:
    """Secure password hasher using PBKDF2-HMAC-SHA256 with 100,000 iterations and 16-byte salt."""

    ALGORITHM = "pbkdf2_sha256"
    ITERATIONS = 100_000
    SALT_BYTES = 16

    @classmethod
    def hash(cls, password: str) -> str:
        """Hash a password with PBKDF2-HMAC-SHA256 and a random 16-byte salt.

        Returns string in format: pbkdf2_sha256$<iterations>$<salt_hex>$<key_hex>
        """
        salt = secrets.token_bytes(cls.SALT_BYTES)
        derived_key = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            cls.ITERATIONS,
        )
        return f"{cls.ALGORITHM}${cls.ITERATIONS}${salt.hex()}${derived_key.hex()}"

    @classmethod
    def verify(cls, password: str, hashed: str) -> bool:
        """Verify password against hashed string timing-safely via hmac.compare_digest."""
        if not hashed or not isinstance(hashed, str):
            return False

        try:
            parts = hashed.split("$")
            if len(parts) != 4:
                return False

            algorithm, iterations_str, salt_hex, expected_key_hex = parts
            if algorithm != cls.ALGORITHM:
                return False

            iterations = int(iterations_str)
            salt = bytes.fromhex(salt_hex)
            expected_key = bytes.fromhex(expected_key_hex)

            actual_key = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                salt,
                iterations,
            )
            return hmac.compare_digest(actual_key, expected_key)
        except Exception:
            return False


__all__ = ["PasswordHasher"]
