"""Permission checker per INIS §19.3."""

from typing import Any

from app.security.authz.policy_evaluator import PolicyEvaluator


class PermissionChecker:
    """Check permissions using combined RBAC and ABAC evaluation."""

    def __init__(self, policy_evaluator: PolicyEvaluator):
        """Initialize permission checker.

        Args:
            policy_evaluator: Policy evaluator for access decisions
        """
        self.policy_evaluator = policy_evaluator

    def check(self, subject: dict[str, Any], resource: dict[str, Any],
              action: str, role: str | None = None) -> tuple[str, str]:
        """Check permission and return decision with reason.

        Args:
            subject: Subject attributes (agent_id, roles, etc.)
            resource: Resource attributes (type, classification, owner, etc.)
            action: Action being performed (read, write, update, delete, transmit, search)
            role: Optional role for RBAC check

        Returns:
            Tuple of (decision, reason) where decision is "allow" or "deny"
        """
        decision = self.policy_evaluator.evaluate(subject, resource, action, role)

        if decision == "deny":
            reason = self._get_deny_reason(subject, resource, action, role)
        else:
            reason = "Access granted"

        return decision, reason

    def _get_deny_reason(self, subject: dict[str, Any], resource: dict[str, Any],
                        action: str, role: str | None = None) -> str:
        """Generate reason for denial.

        Args:
            subject: Subject attributes
            resource: Resource attributes
            action: Action being performed
            role: Optional role for RBAC check

        Returns:
            Reason string for denial
        """
        """Generate reason for denial."""
        classification = resource.get("classification", "public")

        if classification == "restricted":
            return "Resource classification is restricted"

        if role:
            resource_type = resource.get("type", "unknown")
            if not self.policy_evaluator.rbac_engine.check_permission(role, action, resource_type):
                return f"Role '{role}' lacks permission for '{action}' on '{resource_type}'"

        conditions = resource.get("conditions", {})
        if conditions and not self.policy_evaluator.abac_engine.evaluate(
            subject, resource, action, conditions
        ):
            return "Attribute-based conditions not satisfied"

        return "Access denied by policy"
