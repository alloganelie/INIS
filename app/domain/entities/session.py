"""Domain entity for a revocable INIS account session."""

from datetime import UTC, datetime

from pydantic import BaseModel, field_validator
from ulid import ULID as PythonUlid


class Session(BaseModel):
    """A refresh-token session belonging to an account."""

    session_id: str
    account_id: str
    refresh_token_hash: str
    expires_at: datetime
    revoked: bool = False

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, value: str) -> str:
        """Require a SESS-prefixed ULID without changing shared prefixes."""
        return cls._validate_prefixed_ulid(value, "SESS_", "session_id")

    @field_validator("account_id")
    @classmethod
    def validate_account_id(cls, value: str) -> str:
        """Require an ACC-prefixed account ULID."""
        return cls._validate_prefixed_ulid(value, "ACC_", "account_id")

    @field_validator("expires_at")
    @classmethod
    def normalize_expiry(cls, value: datetime) -> datetime:
        """Require a timezone-aware expiry and normalize it to UTC."""
        if value.tzinfo is None:
            raise ValueError("expires_at must be timezone-aware")
        return value.astimezone(UTC)

    @staticmethod
    def _validate_prefixed_ulid(value: str, prefix: str, field_name: str) -> str:
        """Validate one locally-owned prefixed ULID."""
        if not isinstance(value, str) or not value.startswith(prefix):
            raise ValueError(f"{field_name} must be a valid {prefix} ULID")
        try:
            PythonUlid.from_str(value.removeprefix(prefix))
        except ValueError as exc:
            raise ValueError(f"{field_name} must be a valid {prefix} ULID") from exc
        return value

    def is_expired(self) -> bool:
        """Return whether this session has reached its UTC expiry time."""
        return datetime.now(UTC) >= self.expires_at

    def revoke(self) -> None:
        """Revoke this session so its refresh token can no longer be used."""
        self.revoked = True
