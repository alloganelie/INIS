"""Tests for RetentionEnforcer per §41.9 (pure logic, no I/O)."""

from datetime import datetime
from datetime import timezone

import pytest

from app.governance.retention.retention_enforcer import RetentionEnforcer

NOW = datetime(2025, 1, 1, tzinfo=timezone.utc)


class TestRetention:
    """4 tests covering expiry, filtering, config and unknown types."""

    def test_expired_and_fresh_records(self) -> None:
        """Records past their duration are expired, recent ones are not."""
        enforcer = RetentionEnforcer({"pii_data": 90})

        assert enforcer.is_expired("pii_data", "2024-01-01T00:00:00Z", now=NOW) is True
        assert enforcer.is_expired("pii_data", "2024-12-01T00:00:00Z", now=NOW) is False

    def test_select_expired_filters_only_expired(self) -> None:
        """select_expired returns expired records without deleting."""
        enforcer = RetentionEnforcer({"embeddings": 365})
        records = [
            {"id": "old", "created_at": "2023-01-01T00:00:00Z"},
            {"id": "new", "created_at": "2024-06-01T00:00:00Z"},
        ]

        expired = enforcer.select_expired("embeddings", records, now=NOW)

        assert [r["id"] for r in expired] == ["old"]
        assert len(records) == 2

    def test_custom_policies_override_defaults(self) -> None:
        """Injected policies replace defaults per resource type."""
        enforcer = RetentionEnforcer({"artifacts": 7})

        assert enforcer.policies["artifacts"] == 7
        assert enforcer.policies["audit_events"] == 2555

    def test_unknown_resource_type_raises(self) -> None:
        """Unknown types fail explicitly instead of silently passing."""
        enforcer = RetentionEnforcer()

        with pytest.raises(ValueError, match="Unknown resource_type"):
            enforcer.is_expired("nosuch", "2024-01-01T00:00:00Z", now=NOW)
