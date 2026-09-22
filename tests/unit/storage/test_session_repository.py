"""Tests for SessionRepository per §19.2 (authentication)."""

from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.storage.models.account import Account, Session
from app.storage.models.base import Base
from app.storage.repositories.account_repository import AccountRepository
from app.storage.repositories.session_repository import SessionRepository


@pytest.fixture
async def engine():
    """Create an in-memory SQLite engine for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(engine):
    """Create a test session."""
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        yield session


@pytest.fixture
async def account(session):
    """Create a test account."""
    repo = AccountRepository(session)
    return await repo.create(
        account_id="ACC_test123",
        username="testuser",
        email="test@example.com",
        password_hash="hashed_password",
    )


@pytest.mark.asyncio
async def test_session_repository_create(session, account):
    """Test creating a session."""
    repo = SessionRepository(session)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    session_obj = await repo.create(
        session_id="SES_test123",
        account_id=account.account_id,
        token_hash="token_hash",
        expires_at=expires_at,
    )
    assert session_obj.session_id == "SES_test123"
    assert session_obj.account_id == account.account_id
    assert session_obj.token_hash == "token_hash"
    # SQLite doesn't preserve timezone, compare without it
    assert session_obj.expires_at.replace(tzinfo=None) == expires_at.replace(tzinfo=None)


@pytest.mark.asyncio
async def test_session_repository_get(session, account):
    """Test getting a session by ID."""
    repo = SessionRepository(session)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    await repo.create(
        session_id="SES_test123",
        account_id=account.account_id,
        token_hash="token_hash",
        expires_at=expires_at,
    )
    session_obj = await repo.get("SES_test123")
    assert session_obj is not None
    assert session_obj.session_id == "SES_test123"


@pytest.mark.asyncio
async def test_session_repository_revoke(session, account):
    """Test revoking a session."""
    repo = SessionRepository(session)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    await repo.create(
        session_id="SES_test123",
        account_id=account.account_id,
        token_hash="token_hash",
        expires_at=expires_at,
    )
    session_obj = await repo.revoke("SES_test123")
    assert session_obj is not None
    assert session_obj.revoked_at is not None


@pytest.mark.asyncio
async def test_session_repository_delete_expired(session, account):
    """Test deleting expired sessions."""
    repo = SessionRepository(session)
    expired_at = datetime.now(timezone.utc) - timedelta(hours=1)
    await repo.create(
        session_id="SES_expired",
        account_id=account.account_id,
        token_hash="expired_token",
        expires_at=expired_at,
    )
    deleted_count = await repo.delete_expired()
    assert deleted_count == 1


@pytest.mark.asyncio
async def test_session_repository_list_active_by_account(session, account):
    """Test listing active sessions for an account."""
    repo = SessionRepository(session)
    future_expires = datetime.now(timezone.utc) + timedelta(hours=1)
    past_expires = datetime.now(timezone.utc) - timedelta(hours=1)

    await repo.create(
        session_id="SES_active1",
        account_id=account.account_id,
        token_hash="token1",
        expires_at=future_expires,
    )
    await repo.create(
        session_id="SES_expired",
        account_id=account.account_id,
        token_hash="token2",
        expires_at=past_expires,
    )

    active_sessions = await repo.list_active_by_account(account.account_id)
    assert len(active_sessions) == 1
    assert active_sessions[0].session_id == "SES_active1"
