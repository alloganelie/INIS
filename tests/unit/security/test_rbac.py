"""Tests for RBAC engine per INIS §19.3."""

import pytest

from app.security.authz import RBACEngine


def test_rbac_check_permission_granted():
    """Test permission check when role has permission."""
    role_permissions = {
        "admin": {"read:information", "write:information", "delete:information"},
        "user": {"read:information"}
    }
    engine = RBACEngine(role_permissions)

    assert engine.check_permission("admin", "read", "information") is True
    assert engine.check_permission("user", "read", "information") is True


def test_rbac_check_permission_denied():
    """Test permission check when role lacks permission."""
    role_permissions = {
        "user": {"read:information"}
    }
    engine = RBACEngine(role_permissions)

    assert engine.check_permission("user", "write", "information") is False
    assert engine.check_permission("user", "delete", "information") is False


def test_rbac_check_permission_unknown_role():
    """Test permission check for unknown role."""
    role_permissions = {
        "admin": {"read:information"}
    }
    engine = RBACEngine(role_permissions)

    assert engine.check_permission("unknown", "read", "information") is False


def test_rbac_get_permissions():
    """Test getting permissions for a role."""
    role_permissions = {
        "admin": {"read:information", "write:information", "delete:information"},
        "user": {"read:information"}
    }
    engine = RBACEngine(role_permissions)

    admin_perms = engine.get_permissions("admin")
    user_perms = engine.get_permissions("user")

    assert len(admin_perms) == 3
    assert len(user_perms) == 1
    assert "read:information" in user_perms


def test_rbac_add_role():
    """Test adding a new role."""
    engine = RBACEngine({})

    engine.add_role("editor", {"read:information", "write:information"})

    assert engine.check_permission("editor", "read", "information") is True
    assert engine.check_permission("editor", "write", "information") is True


def test_rbac_remove_role():
    """Test removing a role."""
    role_permissions = {
        "admin": {"read:information"}
    }
    engine = RBACEngine(role_permissions)

    engine.remove_role("admin")

    assert engine.check_permission("admin", "read", "information") is False
