"""Lifecycle states for INIS accounts."""

from enum import Enum


class AccountStatus(str, Enum):
    """Allowed account states."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    LOCKED = "locked"
    DELETED = "deleted"
