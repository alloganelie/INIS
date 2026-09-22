"""Repository for Account entity per §19.2 (authentication)."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Result, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.models.account import Account


class AccountRepository:
    """Repository for Account CRUD operations."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the repository with a database session.

        Args:
            session: SQLAlchemy async session.
        """
        self._session = session

    async def create(
        self,
        account_id: str,
        username: str,
        email: str,
        password_hash: str,
        status: str = "active",
    ) -> Account:
        """Create a new account.

        Args:
            account_id: Unique identifier for the account.
            username: Unique username.
            email: Unique email address.
            password_hash: Hashed password.
            status: Account status (default: active).

        Returns:
            The created Account instance.
        """
        account = Account(
            account_id=account_id,
            username=username,
            email=email,
            password_hash=password_hash,
            status=status,
        )
        self._session.add(account)
        await self._session.flush()
        await self._session.refresh(account)
        return account

    async def get_by_username(self, username: str) -> Optional[Account]:
        """Get an account by username.

        Args:
            username: The username to search for.

        Returns:
            The Account if found, None otherwise.
        """
        result: Result = await self._session.execute(
            select(Account).where(Account.username == username)
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[Account]:
        """Get an account by email.

        Args:
            email: The email to search for.

        Returns:
            The Account if found, None otherwise.
        """
        result: Result = await self._session.execute(
            select(Account).where(Account.email == email)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, account_id: str) -> Optional[Account]:
        """Get an account by ID.

        Args:
            account_id: The account ID to search for.

        Returns:
            The Account if found, None otherwise.
        """
        result: Result = await self._session.execute(
            select(Account).where(Account.account_id == account_id)
        )
        return result.scalar_one_or_none()

    async def update_status(self, account_id: str, status: str) -> Optional[Account]:
        """Update the status of an account.

        Args:
            account_id: The account ID to update.
            status: The new status.

        Returns:
            The updated Account if found, None otherwise.
        """
        await self._session.execute(
            update(Account)
            .where(Account.account_id == account_id)
            .values(status=status, updated_at=datetime.now(timezone.utc))
        )
        await self._session.flush()
        return await self.get_by_id(account_id)

    async def update_password_hash(self, account_id: str, password_hash: str) -> Optional[Account]:
        """Update the password hash of an account.

        Args:
            account_id: The account ID to update.
            password_hash: The new password hash.

        Returns:
            The updated Account if found, None otherwise.
        """
        await self._session.execute(
            update(Account)
            .where(Account.account_id == account_id)
            .values(password_hash=password_hash, updated_at=datetime.now(timezone.utc))
        )
        await self._session.flush()
        return await self.get_by_id(account_id)

    async def delete(self, account_id: str) -> Optional[Account]:
        """Soft delete an account by setting deleted_at and status.

        Args:
            account_id: The account ID to delete.

        Returns:
            The deleted Account if found, None otherwise.
        """
        await self._session.execute(
            update(Account)
            .where(Account.account_id == account_id)
            .values(
                deleted_at=datetime.now(timezone.utc),
                status="deleted",
                updated_at=datetime.now(timezone.utc),
            )
        )
        await self._session.flush()
        return await self.get_by_id(account_id)
