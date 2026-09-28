"""Credential vault for authenticated sources per §41.4.

The spec is explicit: credentials **must never** be stored in clear text in the
database nor appear in logs or ``audit_event``. This module provides the
abstraction the rest of the code depends on:

* :class:`CredentialVault` — the ``get`` / ``set`` / ``delete`` / ``rotate``
  protocol implemented by :class:`EnvVault` and :class:`FileVault`.
* :class:`SourceCredential` — the ``[CONFIG]`` block describing how one source
  authenticates (``auth_type``, ``credential_ref``, ``token_expiry``,
  ``auto_refresh``).
* :func:`redact` — the single helper used by loggers and the audit writer so a
  secret can never leak.

Encryption uses authenticated Fernet when ``cryptography`` is installed, and
falls back to a clearly-labelled obfuscation otherwise. The fallback is *not*
claimed to be secure: :class:`FileVault` exposes ``is_encrypted`` so callers
can refuse to use it in production.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from typing import Literal
from typing import Protocol

#: The authentication mechanisms of §41.4.
AuthType = Literal["oauth2", "api_key", "basic", "certificate", "none"]

AUTH_TYPES: tuple[str, ...] = ("oauth2", "api_key", "basic", "certificate", "none")

#: Secret key names that must never be logged or audited (§41.4).
SECRET_KEYS: frozenset[str] = frozenset(
    {
        "password",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "id_token",
        "api_key",
        "apikey",
        "client_secret",
        "private_key",
        "authorization",
        "passphrase",
    }
)

#: Replacement used by :func:`redact`.
REDACTED = "***REDACTED***"

#: Default skew applied when checking a token expiry (§41.4 auto_refresh).
DEFAULT_REFRESH_SKEW_SECONDS = 60


class CredentialNotFound(KeyError):
    """Raised when a ``credential_ref`` is absent from the vault."""


class VaultError(RuntimeError):
    """Raised when the vault cannot fulfil a request."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso_z(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


def redact(payload: Any) -> Any:
    """Return *payload* with every secret value replaced by ``***REDACTED***``.

    Recurses through dicts, lists and tuples so nested credentials cannot leak
    into a log line or an ``audit_event`` (§41.4).
    """
    if isinstance(payload, dict):
        cleaned: dict[Any, Any] = {}
        for key, value in payload.items():
            if isinstance(key, str) and key.lower() in SECRET_KEYS:
                cleaned[key] = REDACTED
            else:
                cleaned[key] = redact(value)
        return cleaned
    if isinstance(payload, list):
        return [redact(item) for item in payload]
    if isinstance(payload, tuple):
        return tuple(redact(item) for item in payload)
    return payload


def _fernet(master_key: bytes) -> Any | None:
    """Return a Fernet instance when ``cryptography`` is available."""
    try:
        from cryptography.fernet import Fernet
    except ImportError:  # pragma: no cover - exercised only without the extra
        return None
    digest = hashlib.sha256(master_key).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _derive_key(master_key: str, salt: bytes) -> bytes:
    """Derive a 32-byte key from *master_key* and *salt* (PBKDF2, stdlib)."""
    return hashlib.pbkdf2_hmac("sha256", master_key.encode("utf-8"), salt, 100_000, dklen=32)


def _xor_obfuscate(data: bytes, key: bytes) -> bytes:
    """Stream XOR fallback used only when ``cryptography`` is unavailable."""
    stream = bytearray()
    counter = 0
    while len(stream) < len(data):
        stream += hmac.new(key, counter.to_bytes(8, "big"), hashlib.sha256).digest()
        counter += 1
    return bytes(a ^ b for a, b in zip(data, bytes(stream)))


class CredentialVault(Protocol):
    """The §41.4 vault contract implemented by every backend."""

    def get(self, ref: str) -> dict[str, Any]:
        """Return the secret material stored under *ref*.

        Raises:
            CredentialNotFound: when *ref* is unknown.
        """
        ...

    def set(self, ref: str, secret: dict[str, Any]) -> None:
        """Store (or replace) the secret material under *ref*."""
        ...

    def delete(self, ref: str) -> bool:
        """Remove *ref*; return whether something was removed."""
        ...

    def rotate(self, ref: str, secret: dict[str, Any]) -> None:
        """Atomically replace the material of *ref*, keeping the same path."""
        ...

    def list_refs(self) -> list[str]:
        """Return every known ``credential_ref`` (never the secrets)."""
        ...


class EnvVault:
    """Vault backed by environment variables (12-factor, no persistence).

    Each ``credential_ref`` maps to ``INIS_CRED_<REF>`` holding a JSON object.
    Secrets live in the process environment, so they are never written to the
    database nor to an ``audit_event`` (§41.4).
    """

    prefix = "INIS_CRED_"

    def __init__(self, environ: dict[str, str] | None = None) -> None:
        self._environ = environ if environ is not None else os.environ

    def _var_name(self, ref: str) -> str:
        return f"{self.prefix}{ref.replace('.', '_').replace('/', '_').upper()}"

    def get(self, ref: str) -> dict[str, Any]:
        """Return the secret stored in the environment for *ref*."""
        import json

        raw = self._environ.get(self._var_name(ref))
        if raw is None:
            raise CredentialNotFound(f"no environment credential for ref '{ref}'")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise VaultError(f"credential '{ref}' is not valid JSON") from exc
        return value

    def set(self, ref: str, secret: dict[str, Any]) -> None:
        """Store *secret* as JSON in the environment (process scope only)."""
        import json

        self._environ[self._var_name(ref)] = json.dumps(secret)

    def delete(self, ref: str) -> bool:
        """Remove the environment variable backing *ref*."""
        return self._environ.pop(self._var_name(ref), None) is not None

    def rotate(self, ref: str, secret: dict[str, Any]) -> None:
        """Replace the material of *ref* in place."""
        self.set(ref, secret)

    def list_refs(self) -> list[str]:
        """Return every known ref in *sanitized* form (usable with :meth:`get`).

        Environment variable names cannot contain ``/``, so a ref is mapped to
        ``INIS_CRED_SRC_ALPHA`` for ``src/alpha``. The returned strings are the
        sanitized identifiers, and every accessor re-applies the same
        sanitization, so they round-trip through :meth:`get` / :meth:`delete`.
        """
        marker = self.prefix
        return sorted(key[len(marker) :].lower() for key in self._environ if key.startswith(marker))


class FileVault:
    """Encrypted file-backed vault (§41.4).

    Material is encrypted with authenticated Fernet when ``cryptography`` is
    available. Without it the vault falls back to a keystream XOR so the
    feature remains usable in a minimal deployment, but :attr:`is_encrypted`
    reports ``False`` and a production deployment must refuse it.
    """

    #: Bumped whenever the on-disk format changes.
    FORMAT_VERSION = 1

    def __init__(
        self,
        path: str | Path,
        master_key: str | None = None,
    ) -> None:
        self._path = Path(path)
        self._master_key = master_key or os.environ.get("INIS_VAULT_KEY", "")
        if not self._master_key:
            raise VaultError(
                "FileVault requires a master key (INIS_VAULT_KEY or master_key=)"
            )
        self._fernet = _fernet(self._master_key.encode("utf-8"))
        self._salt = hashlib.sha256(self._master_key.encode("utf-8")).digest()[:16]
        self._data: dict[str, dict[str, Any]] = {}
        self._load()

    @property
    def is_encrypted(self) -> bool:
        """Return whether authenticated encryption is active."""
        return self._fernet is not None

    def _xor_key(self) -> bytes:
        return _derive_key(self._master_key, self._salt)

    def _encode(self, secret: dict[str, Any]) -> str:
        import json

        raw = json.dumps(secret, sort_keys=True).encode("utf-8")
        if self._fernet is not None:
            return "fernet:" + self._fernet.encrypt(raw).decode("ascii")
        return "xor:" + base64.urlsafe_b64encode(_xor_obfuscate(raw, self._xor_key())).decode("ascii")

    def _decode(self, blob: str) -> dict[str, Any]:
        import json

        scheme, _, payload = blob.partition(":")
        if scheme == "fernet":
            if self._fernet is None:
                raise VaultError("vault file is Fernet-encrypted but cryptography is missing")
            raw = self._fernet.decrypt(payload.encode("ascii"))
        elif scheme == "xor":
            raw = _xor_obfuscate(base64.urlsafe_b64decode(payload), self._xor_key())
        else:
            raise VaultError(f"unknown vault encryption scheme '{scheme}'")
        return json.loads(raw.decode("utf-8"))

    def _load(self) -> None:
        """Load the vault file, tolerating a missing file."""
        if not self._path.exists():
            return
        import json

        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise VaultError(f"vault file '{self._path}' is unreadable") from exc
        self._data = {
            ref: self._decode(blob) for ref, blob in payload.get("entries", {}).items()
        }

    def _flush(self) -> None:
        """Persist the encrypted vault file with owner-only permissions."""
        import json

        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": self.FORMAT_VERSION,
            "encrypted": self.is_encrypted,
            "entries": {ref: self._encode(secret) for ref, secret in self._data.items()},
        }
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        if os.name == "posix":
            self._path.chmod(0o600)

    def get(self, ref: str) -> dict[str, Any]:
        """Return the decrypted secret stored under *ref*."""
        try:
            return dict(self._data[ref])
        except KeyError as exc:
            raise CredentialNotFound(f"no credential for ref '{ref}'") from exc

    def set(self, ref: str, secret: dict[str, Any]) -> None:
        """Encrypt and store *secret* under *ref*."""
        self._data[ref] = dict(secret)
        self._flush()

    def delete(self, ref: str) -> bool:
        """Remove *ref* from the vault and return whether it existed."""
        if ref not in self._data:
            return False
        del self._data[ref]
        self._flush()
        return True

    def rotate(self, ref: str, secret: dict[str, Any]) -> None:
        """Replace the material of *ref* while keeping the same path."""
        self.set(ref, secret)

    def list_refs(self) -> list[str]:
        """Return every known ref (never the secret values)."""
        return sorted(self._data)


@dataclass
class SourceCredential:
    """How one source authenticates, per the §41.4 ``[CONFIG]`` block."""

    source_id: str
    auth_type: AuthType = "none"
    credential_ref: str | None = None
    token_expiry: str | None = None
    auto_refresh: bool = False
    #: Extra, non-secret metadata (scopes, token URL, header name…).
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not str(self.source_id).startswith("SRC_"):
            raise ValueError("source_id must be a SRC_{ULID} identifier (§0.3)")
        if self.auth_type not in AUTH_TYPES:
            raise ValueError(
                f"auth_type must be one of {AUTH_TYPES}, got '{self.auth_type}'"
            )
        if self.auth_type != "none" and not self.credential_ref:
            raise ValueError(
                f"auth_type '{self.auth_type}' requires a credential_ref (§41.4)"
            )
        if self.token_expiry is not None:
            # Fail fast on a malformed timestamp rather than at request time.
            datetime.fromisoformat(str(self.token_expiry).replace("Z", "+00:00"))

    def is_expired(self, now: datetime | None = None, skew_seconds: int = DEFAULT_REFRESH_SKEW_SECONDS) -> bool:
        """Return whether the token is expired (or about to be).

        A credential without ``token_expiry`` never expires, which is correct
        for API keys and certificates.
        """
        if not self.token_expiry:
            return False
        moment = now or _utc_now()
        expiry = datetime.fromisoformat(str(self.token_expiry).replace("Z", "+00:00"))
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        return moment >= expiry - timedelta(seconds=skew_seconds)

    def needs_refresh(self, now: datetime | None = None) -> bool:
        """Return whether ``auto_refresh`` should trigger a rotation (§41.4)."""
        return bool(self.auto_refresh and self.is_expired(now))

    def to_dict(self) -> dict[str, Any]:
        """Return the §41.4 block; contains no secret value, only the ref."""
        return {
            "source_id": self.source_id,
            "auth_type": self.auth_type,
            "credential_ref": self.credential_ref,
            "token_expiry": self.token_expiry,
            "auto_refresh": self.auto_refresh,
        }

    def safe_repr(self) -> dict[str, Any]:
        """Return the block with every secret-looking value redacted."""
        return redact(self.to_dict())


class CredentialResolver:
    """Resolve a :class:`SourceCredential` into usable request material.

    The resolver is the only component allowed to touch a secret value; every
    log or audit event it produces goes through :func:`redact`.
    """

    def __init__(self, vault: CredentialVault) -> None:
        self._vault = vault

    def resolve(self, credential: SourceCredential) -> dict[str, Any]:
        """Return the secret material for *credential*.

        Raises:
            CredentialNotFound: when the ``credential_ref`` is unknown.
            ValueError: when the credential declares ``auth_type="none"``.
        """
        if credential.auth_type == "none":
            return {}
        assert credential.credential_ref is not None  # guaranteed by __post_init__
        return self._vault.get(credential.credential_ref)

    def auth_headers(self, credential: SourceCredential) -> dict[str, str]:
        """Return the HTTP headers required to authenticate against the source."""
        secret = self.resolve(credential)
        if not secret:
            return {}
        if credential.auth_type == "api_key":
            header = str(secret.get("header", "X-API-Key"))
            return {header: str(secret.get("api_key", ""))}
        if credential.auth_type in ("oauth2", "basic", "certificate"):
            token = secret.get("access_token") or secret.get("token")
            if token:
                return {"Authorization": f"Bearer {token}"}
            if credential.auth_type == "basic":
                import base64 as _b64

                raw = f"{secret.get('username', '')}:{secret.get('password', '')}"
                return {"Authorization": "Basic " + _b64.b64encode(raw.encode()).decode()}
        return {}

    def rotate(self, credential: SourceCredential, secret: dict[str, Any]) -> None:
        """Rotate the material of *credential* in the vault (§41.4)."""
        if not credential.credential_ref:
            raise ValueError("cannot rotate a credential without a credential_ref")
        self._vault.rotate(credential.credential_ref, secret)
        if "token_expiry" in secret:
            credential.token_expiry = secret["token_expiry"]
