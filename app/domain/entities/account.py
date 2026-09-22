"""Domain entity for an authenticated INIS account."""

from datetime import UTC, datetime

from pydantic import BaseModel, Field, field_validator
from ulid import ULID as PythonUlid

from app.domain.enums.account_status import AccountStatus
from app.domain.value_objects.email import Email


class Account(BaseModel):
    """An account that can authenticate to INIS."""

    account_id: str
    username: str
    email: str
    password_hash: str
    status: AccountStatus = AccountStatus.ACTIVE
    scopes: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("account_id")
    @classmethod
    def validate_account_id(cls, value: str) -> str:
        """Require an ACC-prefixed ULID without changing shared prefixes."""
        prefix = "ACC_"
        if not isinstance(value, str) or not value.startswith(prefix):
            raise ValueError("account_id must be a valid ACC_ ULID")
        try:
            PythonUlid.from_str(value.removeprefix(prefix))
        except ValueError as exc:
            raise ValueError("account_id must be a valid ACC_ ULID") from exc
        return value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        """Validate and retain the serializable Email value."""
        return str(Email(value))

    @field_validator("created_at", "updated_at")
    @classmethod
    def normalize_utc_timestamp(cls, value: datetime) -> datetime:
        """Require timezone-aware timestamps and normalize them to UTC."""
        if value.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        return value.astimezone(UTC)

    def validate(self) -> None:
        """Reject weak password hashes before the account is persisted."""
        if len(self.password_hash) < 32 or "password" in self.password_hash.lower():
            raise ValueError("password_hash must be at least 32 characters and not contain password")
