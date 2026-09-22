"""Tests for AccountRepository per §19.2 (authentication)."""

from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.storage.models.account import Account
from app.storage.models.base import Base
from app.storage.repositories.account_repository import AccountRepository


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


@pytest.mark.asyncio
async def test_account_repository_create(session):
    """Test creating an account."""
    repo = AccountRepository(session)
    account = await repo.create(
        account_id="ACC_test123",
        username="testuser",
        email="test@example.com",
        password_hash="hashed_password",
    )
    assert account.account_id == "ACC_test123"
    assert account.username == "testuser"
    assert account.email == "test@example.com"
    assert account.password_hash == "hashed_password"
    assert account.status == "active"


@pytest.mark.asyncio
async def test_account_repository_get_by_username(session):
    """Test getting an account by username."""
    repo = AccountRepository(session)
    await repo.create(
        account_id="ACC_test123",
        username="testuser",
        email="test@example.com",
        password_hash="hashed_password",
    )
    account = await repo.get_by_username("testuser")
    assert account is not None
    assert account.username == "testuser"
    assert account.email == "test@example.com"


@pytest.mark.asyncio
async def test_account_repository_get_by_email(session):
    """Test getting an account by email."""
    repo = AccountRepository(session)
    await repo.create(
        account_id="ACC_test123",
        username="testuser",
        email="test@example.com",
        password_hash="hashed_password",
    )
    account = await repo.get_by_email("test@example.com")
    assert account is not None
    assert account.email == "test@example.com"
    assert account.username == "testuser"


@pytest.mark.asyncio
async def test_account_repository_update_status(session):
    """Test updating account status."""
    repo = AccountRepository(session)
    await repo.create(
        account_id="ACC_test123",
        username="testuser",
        email="test@example.com",
        password_hash="hashed_password",
    )
    account = await repo.update_status("ACC_test123", "archived")
    assert account is not None
    assert account.status == "archived"


@pytest.mark.asyncio
async def test_account_repository_update_password_hash(session):
    """Test updating account password hash."""
    repo = AccountRepository(session)
    await repo.create(
        account_id="ACC_test123",
        username="testuser",
        email="test@example.com",
        password_hash="hashed_password",
    )
    account = await repo.update_password_hash("ACC_test123", "new_hashed_password")
    assert account is not None
    assert account.password_hash == "new_hashed_password"


@pytest.mark.asyncio
async def test_account_repository_delete_soft(session):
    """Test soft deleting an account."""
    repo = AccountRepository(session)
    await repo.create(
        account_id="ACC_test123",
        username="testuser",
        email="test@example.com",
        password_hash="hashed_password",
    )
    account = await repo.delete("ACC_test123")
    assert account is not None
    assert account.status == "deleted"
    assert account.deleted_at is not None
