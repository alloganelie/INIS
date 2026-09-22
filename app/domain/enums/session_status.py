"""Lifecycle states for INIS sessions."""

from enum import Enum


class SessionStatus(str, Enum):
    """Allowed session states."""

    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
