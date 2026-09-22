"""Repository for Session entity per §19.2 (authentication)."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Result, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.models.account import Session


class SessionRepository:
    """Repository for Session CRUD operations."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the repository with a database session.

        Args:
            session: SQLAlchemy async session.
        """
        self._session = session

    async def create(
        self,
        session_id: str,
        account_id: str,
        token_hash: str,
        expires_at: datetime,
        session_metadata: Optional[dict] = None,
    ) -> Session:
        """Create a new session.

        Args:
            session_id: Unique identifier for the session.
            account_id: Foreign key to the associated account.
            token_hash: Hashed session token.
            expires_at: Timestamp when the session expires.
            session_metadata: Additional session metadata (default: empty dict).

        Returns:
            The created Session instance.
        """
        session = Session(
            session_id=session_id,
            account_id=account_id,
            token_hash=token_hash,
            expires_at=expires_at,
            session_metadata=session_metadata or {},
        )
        self._session.add(session)
        await self._session.flush()
        await self._session.refresh(session)
        return session

    async def get(self, session_id: str) -> Optional[Session]:
        """Get a session by ID.

        Args:
            session_id: The session ID to search for.

        Returns:
            The Session if found, None otherwise.
        """
        result: Result = await self._session.execute(
            select(Session).where(Session.session_id == session_id)
        )
        return result.scalar_one_or_none()

    async def get_by_token_hash(self, token_hash: str) -> Optional[Session]:
        """Get a session by token hash.

        Args:
            token_hash: The token hash to search for.

        Returns:
            The Session if found, None otherwise.
        """
        result: Result = await self._session.execute(
            select(Session).where(Session.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def revoke(self, session_id: str) -> Optional[Session]:
        """Revoke a session by setting revoked_at.

        Args:
            session_id: The session ID to revoke.

        Returns:
            The revoked Session if found, None otherwise.
        """
        await self._session.execute(
            update(Session)
            .where(Session.session_id == session_id)
            .values(revoked_at=datetime.now(timezone.utc))
        )
        await self._session.flush()
        return await self.get(session_id)

    async def delete_expired(self) -> int:
        """Delete all expired sessions.

        Returns:
            The number of sessions deleted.
        """
        now = datetime.now(timezone.utc)
        result = await self._session.execute(
            delete(Session).where(Session.expires_at < now)
        )
        await self._session.flush()
        return result.rowcount

    async def list_active_by_account(self, account_id: str) -> list[Session]:
        """List all active (non-expired, non-revoked) sessions for an account.

        Args:
            account_id: The account ID to list sessions for.

        Returns:
            List of active Session instances.
        """
        now = datetime.now(timezone.utc)
        result: Result = await self._session.execute(
            select(Session)
            .where(
                Session.account_id == account_id,
                Session.expires_at > now,
                Session.revoked_at.is_(None),
            )
            .order_by(Session.created_at.desc())
        )
        return list(result.scalars().all())

    async def delete(self, session_id: str) -> bool:
        """Delete a session by ID.

        Args:
            session_id: The session ID to delete.

        Returns:
            True if the session was deleted, False otherwise.
        """
        result = await self._session.execute(
            delete(Session).where(Session.session_id == session_id)
        )
        await self._session.flush()
        return result.rowcount > 0
