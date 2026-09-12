"""Tests for SQLAlchemy base models and mixins."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.storage.models.base import Base, SoftDeleteMixin, TimestampMixin


class TimestampTestModel(Base, TimestampMixin):
    """Test model using TimestampMixin."""

    __tablename__ = "timestamp_test_model"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50))


class SoftDeleteTestModel(Base, SoftDeleteMixin):
    """Test model using SoftDeleteMixin."""

    __tablename__ = "soft_delete_test_model"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50))


def test_base_has_timestamps() -> None:
    """Test that TimestampMixin adds created_at and updated_at fields."""
    model = TimestampTestModel(name="test")

    assert hasattr(model, "created_at")
    assert hasattr(model, "updated_at")

    # Check that timestamps can be set to datetime objects
    now = datetime.now(timezone.utc)
    model.created_at = now
    model.updated_at = now

    assert isinstance(model.created_at, datetime)
    assert isinstance(model.updated_at, datetime)

    # Check that timestamps are in UTC
    assert model.created_at.tzinfo == timezone.utc
    assert model.updated_at.tzinfo == timezone.utc


def test_soft_delete_mixin() -> None:
    """Test that SoftDeleteMixin adds deleted_at and status fields."""
    model = SoftDeleteTestModel(name="test")

    assert hasattr(model, "deleted_at")
    assert hasattr(model, "status")

    # Check that deleted_at is None by default
    assert model.deleted_at is None

    # Check that status can be set
    model.status = "active"
    assert model.status == "active"

    # Check that status can be changed
    model.status = "archived"
    assert model.status == "archived"
