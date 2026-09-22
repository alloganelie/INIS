"""Tests for the Account entity and Email value object."""

from datetime import UTC
from ulid import ULID as PythonUlid

import pytest
from pydantic import ValidationError

from app.domain.entities import Account
from app.domain.enums import AccountStatus, SessionStatus


def account_id() -> str:
    """Create a valid locally-owned account ID."""
    return f"ACC_{PythonUlid()}"


def make_account(**overrides: object) -> Account:
    """Create a valid account with individually overridable fields."""
    values: dict[str, object] = {
        "account_id": account_id(),
        "username": "alice",
        "email": "alice@example.com",
        "password_hash": "a" * 64,
    }
    values.update(overrides)
    return Account(**values)


def test_account_valid_creation() -> None:
    """Accounts default to active with no scopes and UTC timestamps."""
    account = make_account()

    assert account.status is AccountStatus.ACTIVE
    assert account.scopes == []
    assert account.created_at.tzinfo is UTC
    assert account.updated_at.tzinfo is UTC


def test_account_rejects_invalid_email() -> None:
    """The account email must match the simplified RFC 5322 pattern."""
    with pytest.raises(ValidationError, match="email"):
        make_account(email="not-an-email")


def test_account_validate_rejects_weak_password_hash() -> None:
    """Persistence validation rejects weak or password-containing hashes."""
    account = make_account(password_hash="password-hash-that-is-definitely-long-enough")

    with pytest.raises(ValueError, match="password_hash"):
        account.validate()


def test_account_serializes_to_json() -> None:
    """Account data has a stable JSON representation for API boundaries."""
    account = make_account(status=AccountStatus.SUSPENDED, scopes=["read"])

    json_payload = account.model_dump_json()

    assert '"status":"suspended"' in json_payload
    assert '"email":"alice@example.com"' in json_payload


def test_account_and_session_status_values() -> None:
    """Account and session status enum values are stable public values."""
    assert [status.value for status in AccountStatus] == [
        "active",
        "suspended",
        "locked",
        "deleted",
    ]
    assert [status.value for status in SessionStatus] == ["active", "expired", "revoked"]
