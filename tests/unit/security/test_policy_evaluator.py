"""Unit tests for §19.3 policy evaluation (RBAC × ABAC).

``PolicyEvaluator`` is deny-by-default: a restricted classification, a missing
role permission or an unsatisfied ABAC condition all end in ``"deny"``.
"""

from __future__ import annotations

import pytest

from app.security.authz.abac_engine import ABACEngine
from app.security.authz.policy_evaluator import PolicyEvaluator
from app.security.authz.rbac_engine import RBACEngine

ROLE_PERMISSIONS = {
    "analyst": {"read:information", "search:source"},
    "agent": {"read:information", "write:evidence"},
}


@pytest.fixture
def evaluator() -> PolicyEvaluator:
    """Return an evaluator wired with the test RBAC/ABAC engines."""
    return PolicyEvaluator(RBACEngine(ROLE_PERMISSIONS), ABACEngine())


class TestAllow:
    """§19.3 — allow requires BOTH the role permission and the attributes."""

    def test_role_permission_and_empty_conditions_allow(
        self, evaluator: PolicyEvaluator
    ) -> None:
        """A permitted role with no attribute condition is allowed."""
        decision = evaluator.evaluate(
            {"agent_id": "AGT_1"},
            {"type": "information", "classification": "public"},
            "read",
            "analyst",
        )
        assert decision == "allow"

    def test_satisfied_abac_condition_allows(self, evaluator: PolicyEvaluator) -> None:
        """A matching attribute condition keeps the access allowed."""
        decision = evaluator.evaluate(
            {"agent_id": "AGT_1"},
            {
                "type": "information",
                "classification": "public",
                "owner": "AGT_1",
                "conditions": {"owner": {"operator": "equals", "value": "AGT_1"}},
            },
            "read",
            "analyst",
        )
        assert decision == "allow"

    def test_missing_role_skips_rbac_but_keeps_abac(
        self, evaluator: PolicyEvaluator
    ) -> None:
        """Without a role there is no RBAC check, only the attribute rules."""
        decision = evaluator.evaluate(
            {}, {"type": "information", "classification": "public"}, "read"
        )
        assert decision == "allow"


class TestDeny:
    """§19.3 — every failure mode denies."""

    def test_restricted_classification_denies_even_for_a_permitted_role(
        self, evaluator: PolicyEvaluator
    ) -> None:
        """``restricted`` is an absolute veto regardless of RBAC."""
        decision = evaluator.evaluate(
            {"agent_id": "AGT_1"},
            {"type": "information", "classification": "restricted"},
            "read",
            "analyst",
        )
        assert decision == "deny"

    def test_role_without_permission_denies(self, evaluator: PolicyEvaluator) -> None:
        """``analyst`` may not delete information."""
        decision = evaluator.evaluate(
            {"agent_id": "AGT_1"},
            {"type": "information", "classification": "public"},
            "delete",
            "analyst",
        )
        assert decision == "deny"

    def test_unknown_role_denies(self, evaluator: PolicyEvaluator) -> None:
        """An unregistered role has no permission at all."""
        decision = evaluator.evaluate(
            {},
            {"type": "information", "classification": "public"},
            "read",
            "ghost",
        )
        assert decision == "deny"

    def test_unsatisfied_abac_condition_denies(
        self, evaluator: PolicyEvaluator
    ) -> None:
        """A non-matching attribute condition denies an otherwise allowed read."""
        decision = evaluator.evaluate(
            {"agent_id": "AGT_1"},
            {
                "type": "information",
                "classification": "public",
                "owner": "AGT_2",
                "conditions": {"owner": {"operator": "equals", "value": "AGT_1"}},
            },
            "read",
            "analyst",
        )
        assert decision == "deny"

    def test_missing_attribute_denies(self, evaluator: PolicyEvaluator) -> None:
        """An ABAC condition on an absent field cannot be satisfied."""
        decision = evaluator.evaluate(
            {},
            {
                "type": "information",
                "classification": "public",
                "conditions": {"owner": {"operator": "equals", "value": "AGT_1"}},
            },
            "read",
            "analyst",
        )
        assert decision == "deny"


class TestDecisionContract:
    """§19.3 — the decision is one of two literal strings."""

    @pytest.mark.parametrize("classification", ["public", "internal", "private"])
    def test_decision_vocabulary(
        self, evaluator: PolicyEvaluator, classification: str
    ) -> None:
        """Non-restricted classifications with a permitted role are allowed."""
        decision = evaluator.evaluate(
            {},
            {"type": "information", "classification": classification},
            "read",
            "analyst",
        )
        assert decision in {"allow", "deny"}
        assert decision == "allow"

    def test_rbac_engine_is_reused_not_copied(self, evaluator: PolicyEvaluator) -> None:
        """The evaluator exposes its engines (used by ``_get_deny_reason``)."""
        assert isinstance(evaluator.rbac_engine, RBACEngine)
        assert isinstance(evaluator.abac_engine, ABACEngine)

