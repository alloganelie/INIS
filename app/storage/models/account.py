"""SQLAlchemy models for accounts and sessions per §19.2 (authentication)."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.storage.models.base import Base, SoftDeleteMixin, TimestampMixin


class Account(Base, TimestampMixin, SoftDeleteMixin):
    """Account model for user authentication and authorization.

    Attributes:
        account_id: Unique identifier for the account (ULID).
        username: Unique username for login.
        email: Unique email address.
        password_hash: Hashed password (never store plaintext).
        status: Account status (active, archived, deleted, superseded).
        created_at: Timestamp when account was created.
        updated_at: Timestamp when account was last updated.
        deleted_at: Timestamp when account was soft deleted (null if active).
        sessions: List of sessions associated with this account.
    """

    __tablename__ = "accounts"
    __table_args__ = {"extend_existing": True}

    account_id: Mapped[str] = mapped_column(Text, primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    sessions: Mapped[list["Session"]] = relationship(
        "Session", back_populates="account", cascade="all, delete-orphan"
    )


class Session(Base, TimestampMixin):
    """Session model for authentication tokens.

    Attributes:
        session_id: Unique identifier for the session (ULID).
        account_id: Foreign key to the associated account.
        token_hash: Hashed session token (never store plaintext).
        expires_at: Timestamp when the session expires.
        created_at: Timestamp when the session was created.
        revoked_at: Timestamp when the session was revoked (null if active).
        session_metadata: Additional session metadata (IP, user agent, etc.).
        account: The associated account.
    """

    __tablename__ = "sessions"
    __table_args__ = {"extend_existing": True}

    session_id: Mapped[str] = mapped_column(Text, primary_key=True)
    account_id: Mapped[str] = mapped_column(
        Text, ForeignKey("accounts.account_id"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    session_metadata: Mapped[dict] = mapped_column(JSON, default=lambda: {}, nullable=False)

    account: Mapped["Account"] = relationship("Account", back_populates="sessions")

    def is_expired(self) -> bool:
        """Check if the session is expired."""
        return datetime.now(timezone.utc) > self.expires_at

    def is_revoked(self) -> bool:
        """Check if the session is revoked."""
        return self.revoked_at is not None

    def is_valid(self) -> bool:
        """Check if the session is valid (not expired and not revoked)."""
        return not self.is_expired() and not self.is_revoked()
