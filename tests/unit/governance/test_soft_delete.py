"""Unit tests for the §18.2 soft-delete policy.

§18.2 forbids physical deletion: a record leaves the active set by setting
``deleted_at`` (and an authorized status), never by ``DELETE FROM``. The
repository unit tests already cover ``AccountRepository.delete``; the policy
itself is asserted here on the mixin and on the full lifecycle.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.domain.value_objects.ulid import ULID
from app.storage.models.account import Account
from app.storage.models.base import Base
from app.storage.repositories.account_repository import AccountRepository

#: Authorized statuses of the §18.2 lifecycle.
AUTHORIZED_STATUSES = ("active", "archived", "deleted", "superseded")


@pytest.fixture
async def session():
    """Yield an in-memory SQLite session with the real ORM metadata."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _create_account(repo: AccountRepository, username: str = "softee") -> Account:
    """Create one account through the repository."""
    account_id = "ACC_" + ULID.new("REQ_").removeprefix("REQ_")
    return await repo.create(
        account_id=account_id,
        username=username,
        email=f"{username}@example.com",
        password_hash="hashed",
    )


class TestSoftDeleteSemantics:
    """§18.2 — logical deletion only."""

    async def test_new_record_is_active_and_not_deleted(self, session: AsyncSession) -> None:
        """The mixin defaults are ``status='active'`` and ``deleted_at=None``."""
        account = await _create_account(AccountRepository(session))
        assert account.status == "active"
        assert account.deleted_at is None

    async def test_delete_sets_deleted_at_and_status(self, session: AsyncSession) -> None:
        """Deletion stamps the record instead of removing it."""
        repo = AccountRepository(session)
        account = await _create_account(repo, "softee-delete")
        deleted = await repo.delete(account.account_id)
        assert deleted is not None
        assert deleted.deleted_at is not None
        assert deleted.status == "deleted"

    async def test_row_survives_the_delete(self, session: AsyncSession) -> None:
        """The row is still in the table: no physical ``DELETE`` happened."""
        repo = AccountRepository(session)
        account = await _create_account(repo, "softee-row")
        await repo.delete(account.account_id)

        rows = (await session.execute(select(Account))).scalars().all()
        assert [row.account_id for row in rows] == [account.account_id]
        assert (await repo.get_by_id(account.account_id)) is not None

    async def test_deleted_record_stays_retrievable_by_username(
        self, session: AsyncSession
    ) -> None:
        """Retrieval keeps working after deletion (audit/history need it)."""
        repo = AccountRepository(session)
        account = await _create_account(repo, "softee-history")
        await repo.delete(account.account_id)
        found = await repo.get_by_username("softee-history")
        assert found is not None
        assert found.deleted_at is not None

    async def test_delete_is_idempotent(self, session: AsyncSession) -> None:
        """Deleting twice keeps the record deleted (and does not raise)."""
        repo = AccountRepository(session)
        account = await _create_account(repo, "softee-twice")
        await repo.delete(account.account_id)
        again = await repo.delete(account.account_id)
        assert again is not None
        assert again.status == "deleted"
        assert again.deleted_at is not None

    async def test_delete_unknown_record_returns_none(self, session: AsyncSession) -> None:
        """Deleting an unknown id is a no-op, not an error."""
        assert await AccountRepository(session).delete("REQ_missing") is None


class TestLifecycleStatuses:
    """§18.2 — the four authorized statuses are usable."""

    @pytest.mark.parametrize("status", AUTHORIZED_STATUSES)
    async def test_authorized_status_is_stored(
        self, session: AsyncSession, status: str
    ) -> None:
        """Every documented status can be persisted."""
        repo = AccountRepository(session)
        account = await _create_account(repo, f"status-{status}")
        updated = await repo.update_status(account.account_id, status)
        assert updated is not None
        assert updated.status == status

    async def test_archived_record_has_no_deletion_timestamp(
        self, session: AsyncSession
    ) -> None:
        """``archived`` is not a deletion: ``deleted_at`` stays NULL."""
        repo = AccountRepository(session)
        account = await _create_account(repo, "status-archived-only")
        archived = await repo.update_status(account.account_id, "archived")
        assert archived.status == "archived"
        assert archived.deleted_at is None

    async def test_updated_at_is_refreshed_on_status_change(
        self, session: AsyncSession
    ) -> None:
        """§18.3 — temporal fields are maintained by every write.

        SQLite hands back naive datetimes for ``DateTime(timezone=True)``, so
        the comparison normalizes the timezone before ordering.
        """
        repo = AccountRepository(session)
        account = await _create_account(repo, "status-timestamps")
        original = account.updated_at.replace(tzinfo=None)
        updated = await repo.update_status(account.account_id, "archived")
        assert updated.updated_at is not None
        assert updated.updated_at.replace(tzinfo=None) >= original

