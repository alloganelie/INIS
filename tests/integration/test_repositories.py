"""Integration tests for the §19.2/§27 repositories on real PostgreSQL.

The account and session repositories are the ORM-backed repositories of V1 and
the ones the ``/v1/accounts`` and ``/v1/auth`` routers use. They are exercised
here against the pgvector container (not SQLite) so the JSONB ``scopes`` column,
the timestamp columns and the foreign key behave as in production.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.domain.value_objects.ulid import ULID
from app.storage.database.engine import create_engine
from app.storage.database.session import init_session_maker, reset_session_maker
from app.storage.database.session import session_scope
from app.storage.repositories.account_repository import AccountRepository
from app.storage.repositories.session_repository import SessionRepository


def _account_id() -> str:
    """Return a fresh account identifier (``ACC_`` + ULID suffix)."""
    return "ACC_" + ULID.new("REQ_").removeprefix("REQ_")


def _session_id() -> str:
    """Return a fresh session identifier."""
    return "SESSION_" + ULID.new("REQ_").removeprefix("REQ_")


@pytest.fixture
async def db(db_url: str):
    """Yield a session bound to the migrated PostgreSQL test database."""
    engine = create_engine(db_url)
    init_session_maker(engine)
    try:
        async with session_scope() as session:
            yield session
            await session.rollback()
    finally:
        reset_session_maker()
        await engine.dispose()


class TestAccountRepository:
    """§19.2 — accounts are persisted with their authorization attributes."""

    async def test_create_and_read_back(self, db) -> None:
        """A created account is retrievable by id, username and email."""
        repo = AccountRepository(db)
        account_id = _account_id()
        username = f"repo-{account_id[-12:]}"
        created = await repo.create(
            account_id=account_id,
            username=username,
            email=f"{username}@example.com",
            password_hash="argon2-hash",
            role="admin",
            scopes=["read", "write", "admin"],
        )
        assert created.account_id == account_id
        assert created.role == "admin"
        assert created.scopes == ["read", "write", "admin"]
        assert created.status == "active"
        assert created.deleted_at is None

        assert (await repo.get_by_id(account_id)).username == username
        assert (await repo.get_by_username(username)).account_id == account_id
        assert (await repo.get_by_email(f"{username}@example.com")).account_id == account_id

    async def test_jsonb_scopes_round_trip(self, db) -> None:
        """The JSONB column keeps the exact scope list (§19.2)."""
        repo = AccountRepository(db)
        account_id = _account_id()
        scopes = ["read", "search", "transmit"]
        await repo.create(
            account_id=account_id,
            username=f"scopes-{account_id[-12:]}",
            email=f"scopes-{account_id[-12:]}@example.com",
            password_hash="hash",
            scopes=scopes,
        )
        assert (await repo.get_by_id(account_id)).scopes == scopes

    async def test_authorization_can_be_updated(self, db) -> None:
        """Role and scopes are updatable independently."""
        repo = AccountRepository(db)
        account_id = _account_id()
        await repo.create(
            account_id=account_id,
            username=f"authz-{account_id[-12:]}",
            email=f"authz-{account_id[-12:]}@example.com",
            password_hash="hash",
        )
        updated = await repo.update_authorization(account_id, role="reader")
        assert updated.role == "reader"
        assert updated.scopes == ["read", "write"]  # untouched

        rescoped = await repo.update_authorization(account_id, scopes=["read"])
        assert rescoped.scopes == ["read"]
        assert rescoped.role == "reader"  # untouched

    async def test_password_hash_is_replaced(self, db) -> None:
        """A rotation replaces the stored hash, never a plaintext password."""
        repo = AccountRepository(db)
        account_id = _account_id()
        await repo.create(
            account_id=account_id,
            username=f"pwd-{account_id[-12:]}",
            email=f"pwd-{account_id[-12:]}@example.com",
            password_hash="old-hash",
        )
        updated = await repo.update_password_hash(account_id, "new-hash")
        assert updated.password_hash == "new-hash"

    async def test_soft_delete_keeps_the_row(self, db) -> None:
        """§18.2 — deletion stamps ``deleted_at`` and keeps the account."""
        repo = AccountRepository(db)
        account_id = _account_id()
        await repo.create(
            account_id=account_id,
            username=f"del-{account_id[-12:]}",
            email=f"del-{account_id[-12:]}@example.com",
            password_hash="hash",
        )
        deleted = await repo.delete(account_id)
        assert deleted.status == "deleted"
        assert deleted.deleted_at is not None
        assert (await repo.get_by_id(account_id)) is not None

    async def test_unknown_account_returns_none(self, db) -> None:
        """Reading an unknown id is not an error."""
        repo = AccountRepository(db)
        assert await repo.get_by_id(_account_id()) is None
        assert await repo.update_status(_account_id(), "archived") is None


class TestSessionRepository:
    """§19.2 — sessions are persisted, revocable and expirable."""

    async def _account(self, repo: AccountRepository) -> str:
        """Create one account and return its id."""
        account_id = _account_id()
        await repo.create(
            account_id=account_id,
            username=f"sess-{account_id[-12:]}",
            email=f"sess-{account_id[-12:]}@example.com",
            password_hash="hash",
        )
        return account_id

    async def test_create_and_lookup(self, db) -> None:
        """A session is retrievable by id and by token hash (no plaintext)."""
        accounts = AccountRepository(db)
        sessions = SessionRepository(db)
        account_id = await self._account(accounts)
        session_id = _session_id()
        token_hash = f"hash-{session_id[-12:]}"
        created = await sessions.create(
            session_id=session_id,
            account_id=account_id,
            token_hash=token_hash,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            session_metadata={"user_agent": "pytest"},
        )
        assert created.session_id == session_id
        assert created.session_metadata == {"user_agent": "pytest"}
        assert (await sessions.get(session_id)) is not None
        assert (await sessions.get_by_token_hash(token_hash)).session_id == session_id

    async def test_fresh_session_is_valid(self, db) -> None:
        """A brand-new session is valid, not revoked and not expired."""
        accounts = AccountRepository(db)
        sessions = SessionRepository(db)
        account_id = await self._account(accounts)
        created = await sessions.create(
            session_id=_session_id(),
            account_id=account_id,
            token_hash=f"t-{_session_id()[-12:]}",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        assert created.is_valid() is True
        assert created.is_revoked() is False
        assert created.is_expired() is False

    async def test_revoke_invalidates_the_session(self, db) -> None:
        """Revocation timestamps the session and clears the active list."""
        accounts = AccountRepository(db)
        sessions = SessionRepository(db)
        account_id = await self._account(accounts)
        session_id = _session_id()
        await sessions.create(
            session_id=session_id,
            account_id=account_id,
            token_hash=f"r-{session_id[-12:]}",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        revoked = await sessions.revoke(session_id)
        assert revoked.revoked_at is not None
        assert revoked.is_valid() is False
        assert await sessions.list_active_by_account(account_id) == []

    async def test_expired_sessions_are_purged(self, db) -> None:
        """``delete_expired`` removes only the expired sessions."""
        accounts = AccountRepository(db)
        sessions = SessionRepository(db)
        account_id = await self._account(accounts)
        expired_id = _session_id()
        live_id = _session_id()
        await sessions.create(
            session_id=expired_id,
            account_id=account_id,
            token_hash=f"e-{expired_id[-12:]}",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        await sessions.create(
            session_id=live_id,
            account_id=account_id,
            token_hash=f"l-{live_id[-12:]}",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        assert await sessions.delete_expired() >= 1
        assert await sessions.get(expired_id) is None
        assert await sessions.get(live_id) is not None

    async def test_active_listing_contains_live_sessions_only(self, db) -> None:
        """Only non-expired, non-revoked sessions are listed."""
        accounts = AccountRepository(db)
        sessions = SessionRepository(db)
        account_id = await self._account(accounts)
        session_id = _session_id()
        await sessions.create(
            session_id=session_id,
            account_id=account_id,
            token_hash=f"a-{session_id[-12:]}",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        active = await sessions.list_active_by_account(account_id)
        assert [item.session_id for item in active] == [session_id]

    async def test_delete_removes_the_session(self, db) -> None:
        """Sessions are physically deleted (they are not versioned records)."""
        accounts = AccountRepository(db)
        sessions = SessionRepository(db)
        account_id = await self._account(accounts)
        session_id = _session_id()
        await sessions.create(
            session_id=session_id,
            account_id=account_id,
            token_hash=f"d-{session_id[-12:]}",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        assert await sessions.delete(session_id) is True
        assert await sessions.get(session_id) is None
        assert await sessions.delete(session_id) is False

