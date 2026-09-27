"""Outcome of a delegation evaluation (§41.10)."""

from enum import Enum


class DelegationEffect(str, Enum):
    """``allow | deny`` — whether a delegation step may proceed."""

    ALLOW = "allow"
    DENY = "deny"
