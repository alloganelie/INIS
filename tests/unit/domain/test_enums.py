"""Unit tests for the §19/§41 domain enumerations.

Every enum is a ``str`` subclass so its value can be serialized verbatim into
API payloads, audit events and inter-agent envelopes (§5.1, §20).
"""

from __future__ import annotations

import json

import pytest

from app.domain.enums import (
    AccountStatus,
    CircuitBreakerState,
    DelegationEffect,
    SessionStatus,
    TrustLevel,
)
from app.domain.enums.account_status import AccountStatus as AccountStatusModule
from app.domain.enums.delegation_effect import DelegationEffect as DelegationEffectModule
from app.domain.enums.trust_level import TrustLevel as TrustLevelModule


class TestAccountStatus:
    """§19.1 — account lifecycle states."""

    def test_members(self) -> None:
        """The four documented states are the only ones defined."""
        assert [status.value for status in AccountStatus] == [
            "active",
            "suspended",
            "locked",
            "deleted",
        ]

    def test_str_subclass_serializes_verbatim(self) -> None:
        """``json.dumps`` writes the bare value, not ``AccountStatus.ACTIVE``."""
        assert json.dumps({"status": AccountStatus.ACTIVE}) == '{"status": "active"}'

    def test_lookup_by_value(self) -> None:
        """Wire values map back to the enum member (schema round-trip)."""
        assert AccountStatus("locked") is AccountStatus.LOCKED

    def test_module_and_package_agree(self) -> None:
        """The package ``__init__`` re-exports the very same class."""
        assert AccountStatus is AccountStatusModule


class TestSessionStatus:
    """§19.1 — session lifecycle states."""

    def test_members(self) -> None:
        """Active / expired / revoked per §19."""
        assert {status.value for status in SessionStatus} == {
            "active",
            "expired",
            "revoked",
        }

    def test_unknown_value_is_rejected(self) -> None:
        """An unknown wire value raises instead of silently degrading."""
        with pytest.raises(ValueError):
            SessionStatus("pending")


class TestCircuitBreakerState:
    """§41.8 — the three states exposed by ``/v1/health``."""

    def test_members(self) -> None:
        """``closed | open | half_open``."""
        assert [state.value for state in CircuitBreakerState] == [
            "closed",
            "open",
            "half_open",
        ]

    def test_snake_case_value_is_preserved(self) -> None:
        """``half_open`` keeps its underscore on the wire."""
        assert CircuitBreakerState.HALF_OPEN == "half_open"


class TestDelegationEffect:
    """§41.10 — allow / deny delegation outcome."""

    def test_members(self) -> None:
        """Only two effects are defined."""
        assert [effect.value for effect in DelegationEffect] == ["allow", "deny"]
        assert DelegationEffect is DelegationEffectModule

    def test_equality_with_string(self) -> None:
        """Decisions returned as strings compare equal to the enum value."""
        assert DelegationEffect.DENY == "deny"


class TestTrustLevel:
    """§41.10 — inter-agent trust levels."""

    def test_members(self) -> None:
        """``full | partial | minimal``."""
        assert [level.value for level in TrustLevel] == ["full", "partial", "minimal"]
        assert TrustLevel is TrustLevelModule

    def test_round_trip_through_wire_value(self) -> None:
        """A stored trust level parses back to its member."""
        assert TrustLevel("partial") is TrustLevel.PARTIAL

