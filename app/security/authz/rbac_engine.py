"""RBAC engine per INIS §19.3."""

from typing import Set


class RBACEngine:
    """Role-Based Access Control engine."""

    def __init__(self, role_permissions: dict[str, Set[str]]):
        """Initialize RBAC engine with role-to-permissions mapping.

        Args:
            role_permissions: Dictionary mapping roles to their permissions
        """
        self.role_permissions = role_permissions

    def check_permission(self, role: str, action: str, resource_type: str) -> bool:
        """Check if a role has permission for an action on a resource type.

        Args:
            role: User/agent role
            action: Action to perform (read, write, update, delete, transmit, search)
            resource_type: Type of resource (information, source, dataset, document)

        Returns:
            True if permission is granted, False otherwise
        """
        if role not in self.role_permissions:
            return False

        permissions = self.role_permissions[role]
        required_permission = f"{action}:{resource_type}"

        return required_permission in permissions

    def get_permissions(self, role: str) -> Set[str]:
        """Get all permissions for a given role.

        Args:
            role: User/agent role

        Returns:
            Set of permissions for the role
        """
        return self.role_permissions.get(role, set())

    def add_role(self, role: str, permissions: Set[str]) -> None:
        """Add a new role with permissions.

        Args:
            role: Role name
            permissions: Set of permissions for the role
        """
        self.role_permissions[role] = permissions

    def remove_role(self, role: str) -> None:
        """Remove a role from the engine.

        Args:
            role: Role name to remove
        """
        self.role_permissions.pop(role, None)
