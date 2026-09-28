"""Unit tests for §19.3 permission checking with an auditable reason.

``PermissionChecker`` wraps ``PolicyEvaluator`` and returns ``(decision,
reason)`` so every denial can be written to the §20 audit trail with a
human-readable justification.
"""

from __future__ import annotations

import pytest

from app.security.authz.abac_engine import ABACEngine
from app.security.authz.permission_checker import PermissionChecker
from app.security.authz.policy_evaluator import PolicyEvaluator
from app.security.authz.rbac_engine import RBACEngine


@pytest.fixture
def checker() -> PermissionChecker:
    """Return a checker over the test RBAC/ABAC engines."""
    evaluator = PolicyEvaluator(
        RBACEngine({"analyst": {"read:information", "search:source"}}), ABACEngine()
    )
    return PermissionChecker(evaluator)


PUBLIC_INFORMATION = {"type": "information", "classification": "public"}


class TestAllow:
    """§19.3 — a granted access carries an explicit reason."""

    def test_allow_returns_the_grant_reason(self, checker: PermissionChecker) -> None:
        """Allowed access is reported as ``Access granted``."""
        decision, reason = checker.check(
            {"agent_id": "AGT_1"}, PUBLIC_INFORMATION, "read", "analyst"
        )
        assert decision == "allow"
        assert reason == "Access granted"

    def test_allow_with_satisfied_conditions(self, checker: PermissionChecker) -> None:
        """Attribute conditions do not change the reported reason on success."""
        resource = {
            **PUBLIC_INFORMATION,
            "owner": "AGT_1",
            "conditions": {"owner": {"operator": "equals", "value": "AGT_1"}},
        }
        decision, reason = checker.check(
            {"agent_id": "AGT_1"}, resource, "read", "analyst"
        )
        assert (decision, reason) == ("allow", "Access granted")


class TestDenyReasons:
    """§19.3 — every denial explains itself (audit requirement §20)."""

    def test_restricted_classification_reason(
        self, checker: PermissionChecker
    ) -> None:
        """The classification veto is named explicitly."""
        decision, reason = checker.check(
            {},
            {"type": "information", "classification": "restricted"},
            "read",
            "analyst",
        )
        assert decision == "deny"
        assert reason == "Resource classification is restricted"

    def test_missing_role_permission_reason(self, checker: PermissionChecker) -> None:
        """The reason names the role, the action and the resource type."""
        decision, reason = checker.check(
            {}, PUBLIC_INFORMATION, "delete", "analyst"
        )
        assert decision == "deny"
        assert "analyst" in reason
        assert "delete" in reason
        assert "information" in reason

    def test_unsatisfied_conditions_reason(self, checker: PermissionChecker) -> None:
        """An ABAC failure reports the attribute-based cause."""
        resource = {
            **PUBLIC_INFORMATION,
            "owner": "AGT_2",
            "conditions": {"owner": {"operator": "equals", "value": "AGT_1"}},
        }
        decision, reason = checker.check(
            {"agent_id": "AGT_1"}, resource, "read", "analyst"
        )
        assert decision == "deny"
        assert reason == "Attribute-based conditions not satisfied"

    def test_unknown_role_reason(self, checker: PermissionChecker) -> None:
        """An unregistered role is denied with its name in the reason."""
        decision, reason = checker.check({}, PUBLIC_INFORMATION, "read", "ghost")
        assert decision == "deny"
        assert "ghost" in reason


class TestResultShape:
    """§19.3 — the two-tuple contract used by the tool layer."""

    def test_decision_is_a_literal_and_reason_a_string(
        self, checker: PermissionChecker
    ) -> None:
        """Callers can unpack ``decision, reason`` without further checks."""
        decision, reason = checker.check(
            {}, PUBLIC_INFORMATION, "read", "analyst"
        )
        assert decision in {"allow", "deny"}
        assert isinstance(reason, str)
        assert reason

    def test_deny_without_role_still_returns_a_reason(
        self, checker: PermissionChecker
    ) -> None:
        """A denial with no role falls back to the generic policy message."""
        resource = {
            **PUBLIC_INFORMATION,
            "owner": "AGT_2",
            "conditions": {"owner": {"operator": "equals", "value": "AGT_1"}},
        }
        decision, reason = checker.check({}, resource, "read")
        assert decision == "deny"
        assert reason

