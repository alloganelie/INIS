"""Policy evaluation per INIS §19.3."""

from typing import Any

from app.security.authz.abac_engine import ABACEngine
from app.security.authz.rbac_engine import RBACEngine


class PolicyEvaluator:
    """Evaluate access policies combining RBAC and ABAC."""

    def __init__(self, rbac_engine: RBACEngine, abac_engine: ABACEngine):
        """Initialize policy evaluator.

        Args:
            rbac_engine: RBAC engine for role-based checks
            abac_engine: ABAC engine for attribute-based checks
        """
        self.rbac_engine = rbac_engine
        self.abac_engine = abac_engine

    def evaluate(self, subject: dict[str, Any], resource: dict[str, Any],
                 action: str, role: str | None = None) -> str:
        """Evaluate access policy and return allow/deny decision.

        Args:
            subject: Subject attributes (agent_id, roles, etc.)
            resource: Resource attributes (type, classification, owner, etc.)
            action: Action being performed (read, write, update, delete, transmit, search)
            role: Optional role for RBAC check

        Returns:
            "allow" if access is granted, "deny" otherwise
        """
        resource_type = resource.get("type", "unknown")
        classification = resource.get("classification", "public")

        if classification == "restricted":
            return "deny"

        if role and not self.rbac_engine.check_permission(role, action, resource_type):
            return "deny"

        conditions = resource.get("conditions", {})
        if not self.abac_engine.evaluate(subject, resource, action, conditions):
            return "deny"

        return "allow"
