"""``check_permission`` internal tool per §21 (§19.3 authorisation).

The tool never invents an authorisation policy: with no injected checker it
falls back to an RBAC engine with an **empty** role map, so role-based access
is denied unless the caller supplies real role mappings (§19.3).
"""

from __future__ import annotations

from typing import Any, Mapping

from app.core.errors import ValidationError
from app.security.authz.abac_engine import ABACEngine
from app.security.authz.permission_checker import PermissionChecker
from app.security.authz.policy_evaluator import PolicyEvaluator
from app.security.authz.rbac_engine import RBACEngine

__all__ = ["check_permission", "default_checker"]


def default_checker() -> PermissionChecker:
    """Build the default checker: empty RBAC map + attribute-based engine."""
    return PermissionChecker(PolicyEvaluator(RBACEngine({}), ABACEngine()))


async def check_permission(
    agent_id: str,
    resource: str | Mapping[str, Any],
    action: str,
    *,
    checker: PermissionChecker | None = None,
    role: str | None = None,
    subject: Mapping[str, Any] | None = None,
) -> bool:
    """Return whether *agent_id* may perform *action* on *resource* (§21).

    Args:
        agent_id: Agent asking for permission (§19.3 subject).
        resource: Resource type as a string, or a full attribute mapping
            (``type``, ``classification``, ``conditions``, ...).
        action: Action being checked (``read``, ``write``, ``search``, ...).
        checker: Injected permission checker; defaults to
            :func:`default_checker`.
        role: Optional role for the RBAC check; defaults to ``role`` found in
            *subject* when present.
        subject: Extra subject attributes merged over ``agent_id``.

    Returns:
        ``True`` when the combined RBAC+ABAC decision is ``allow``.

    Raises:
        ValidationError: If a required argument is missing or *resource* is
            neither a string nor a mapping.
    """
    if not agent_id or not str(agent_id).strip():
        raise ValidationError("agent_id is required for a permission check (§19.3)")
    if not action or not str(action).strip():
        raise ValidationError("action is required for a permission check (§19.3)")
    if isinstance(resource, str):
        if not resource.strip():
            raise ValidationError("resource is required for a permission check (§19.3)")
        resource_attributes: dict[str, Any] = {"type": resource}
    elif isinstance(resource, Mapping):
        resource_attributes = dict(resource)
    else:
        raise ValidationError("resource must be a string or a mapping (§19.3)")

    subject_attributes: dict[str, Any] = {"agent_id": agent_id}
    if subject:
        subject_attributes.update(subject)
    active_role = role if role is not None else subject_attributes.get("role")
    active_checker = checker if checker is not None else default_checker()

    decision, _reason = active_checker.check(
        subject_attributes, resource_attributes, action, active_role
    )
    return decision == "allow"
