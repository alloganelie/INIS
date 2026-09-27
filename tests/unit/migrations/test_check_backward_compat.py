"""Tests for migration backward compatibility checker per §41.14."""

from __future__ import annotations

from pathlib import Path
import pytest
from scripts.migrations.check_backward_compat import BackwardCompatChecker


def test_checker_accepts_clean_migration(tmp_path: Path):
    code = """
from alembic import op
import sqlalchemy as sa

def upgrade():
    op.create_table("test_table", sa.Column("id", sa.Integer(), primary_key=True))
"""
    f = tmp_path / "0001_clean.py"
    f.write_text(code, encoding="utf-8")
    checker = BackwardCompatChecker()
    violations = checker.check_file(f)
    errors = [v for v in violations if v.severity == "error"]
    assert errors == []


def test_checker_refuses_drop_column(tmp_path: Path):
    code = """
from alembic import op

def upgrade():
    op.drop_column("users", "email")
"""
    f = tmp_path / "0002_drop.py"
    f.write_text(code, encoding="utf-8")
    violations = BackwardCompatChecker().check_file(f)
    errors = [v for v in violations if v.severity == "error"]
    assert any(e.rule_id == BackwardCompatChecker.ERROR_DROP_COLUMN for e in errors)


def test_checker_refuses_drop_table(tmp_path: Path):
    code = """
from alembic import op

def upgrade():
    op.drop_table("obsolete_data")
"""
    f = tmp_path / "0003_drop_tab.py"
    f.write_text(code, encoding="utf-8")
    violations = BackwardCompatChecker().check_file(f)
    errors = [v for v in violations if v.severity == "error"]
    assert any(e.rule_id == BackwardCompatChecker.ERROR_DROP_TABLE for e in errors)


def test_checker_refuses_alter_column_type(tmp_path: Path):
    code = """
from alembic import op
import sqlalchemy as sa

def upgrade():
    op.alter_column("users", "age", type_=sa.BigInteger())
"""
    f = tmp_path / "0004_alter.py"
    f.write_text(code, encoding="utf-8")
    violations = BackwardCompatChecker().check_file(f)
    errors = [v for v in violations if v.severity == "error"]
    assert any(e.rule_id == BackwardCompatChecker.ERROR_ALTER_COLUMN_TYPE for e in errors)


def test_checker_refuses_add_not_null_without_default(tmp_path: Path):
    code = """
from alembic import op
import sqlalchemy as sa

def upgrade():
    op.add_column("users", sa.Column("tenant_id", sa.String(64), nullable=False))
"""
    f = tmp_path / "0005_not_null.py"
    f.write_text(code, encoding="utf-8")
    violations = BackwardCompatChecker().check_file(f)
    errors = [v for v in violations if v.severity == "error"]
    assert any(e.rule_id == BackwardCompatChecker.ERROR_ADD_NOT_NULL_NO_DEFAULT for e in errors)


def test_checker_allows_add_not_null_with_server_default(tmp_path: Path):
    code = """
from alembic import op
import sqlalchemy as sa

def upgrade():
    op.add_column("users", sa.Column("role", sa.String(64), nullable=False, server_default="reader"))
"""
    f = tmp_path / "0006_valid_add.py"
    f.write_text(code, encoding="utf-8")
    violations = BackwardCompatChecker().check_file(f)
    errors = [v for v in violations if v.severity == "error"]
    assert errors == []


def test_checker_warns_on_non_concurrent_index(tmp_path: Path):
    code = """
from alembic import op

def upgrade():
    op.create_index("ix_users_name", "users", ["name"])
"""
    f = tmp_path / "0007_index.py"
    f.write_text(code, encoding="utf-8")
    violations = BackwardCompatChecker().check_file(f)
    warns = [v for v in violations if v.severity == "warning"]
    assert any(w.rule_id == BackwardCompatChecker.WARN_CREATE_INDEX_NO_CONCURRENT for w in warns)


def test_migrations_head_is_backward_compatible():
    """Guard test: all real production migration scripts must have 0 breaking errors."""
    checker = BackwardCompatChecker()
    violations = checker.check_directory("migrations/versions")
    errors = [v for v in violations if v.severity == "error"]
    assert errors == [], f"Breaking migration violations detected: {errors}"
