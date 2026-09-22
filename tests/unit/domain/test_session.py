"""Tests for the Session entity."""

from datetime import UTC, datetime, timedelta

from ulid import ULID as PythonUlid

from app.domain.entities import Session


def account_id() -> str:
    """Create a valid locally-owned account ID."""
    return f"ACC_{PythonUlid()}"


def session_id() -> str:
    """Create a valid locally-owned session ID."""
    return f"SESS_{PythonUlid()}"


def make_session(**overrides: object) -> Session:
    """Create an active unexpired session with overridable fields."""
    values: dict[str, object] = {
        "session_id": session_id(),
        "account_id": account_id(),
        "refresh_token_hash": "b" * 64,
        "expires_at": datetime.now(UTC) + timedelta(hours=1),
    }
    values.update(overrides)
    return Session(**values)


def test_session_is_expired_after_expiry_time() -> None:
    """Sessions at a past expiry time are expired."""
    session = make_session(expires_at=datetime.now(UTC) - timedelta(seconds=1))

    assert session.is_expired() is True


def test_session_revoke_marks_session_revoked() -> None:
    """Revocation is explicit and idempotently marks the session."""
    session = make_session()

    session.revoke()

    assert session.revoked is True


def test_session_ids_use_required_ulid_format() -> None:
    """Account and session identifiers retain their local ULID prefixes."""
    session = make_session()

    assert session.account_id.startswith("ACC_")
    assert len(session.account_id.removeprefix("ACC_")) == 26
    assert session.session_id.startswith("SESS_")
    assert len(session.session_id.removeprefix("SESS_")) == 26
