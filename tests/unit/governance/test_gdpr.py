"""Tests for GDPRHandler erasure per §41.9 (pure logic, no I/O)."""

from app.governance.lifecycle.pseudonymizer import Pseudonymizer
from app.governance.retention.gdpr_handler import GDPRHandler


def _records() -> tuple[list[dict], list[dict]]:
    events = [
        {"audit_id": "a1", "actor_id": "actor-1", "action": "read"},
        {"audit_id": "a2", "actor_id": "actor-2", "action": "write"},
    ]
    units = [{"information_id": "i1", "actor_id": "actor-1", "content": "x"}]
    return events, units


class TestGdpr:
    """3 tests covering erasure, provenance preservation and report."""

    def test_erase_actor_pseudonymizes_both_lists(self) -> None:
        """Matching actor_ids are replaced by a stable pseudonym."""
        handler = GDPRHandler(Pseudonymizer(salt="test-salt"))
        events, units = _records()

        result = handler.erase_actor("actor-1", events, units)
        expected = Pseudonymizer(salt="test-salt").pseudonymize("actor-1")

        assert result["pseudonym"] == expected
        assert result["audit_events"][0]["actor_id"] == expected
        assert result["audit_events"][1]["actor_id"] == "actor-2"
        assert result["information_units"][0]["actor_id"] == expected

    def test_provenance_structure_preserved(self) -> None:
        """Records keep ids and inputs are never mutated."""
        handler = GDPRHandler(Pseudonymizer(salt="test-salt"))
        events, units = _records()

        result = handler.erase_actor("actor-1", events, units)

        assert result["audit_events"][0]["audit_id"] == "a1"
        assert result["information_units"][0]["information_id"] == "i1"
        assert events[0]["actor_id"] == "actor-1"
        assert units[0]["actor_id"] == "actor-1"

    def test_report_counts_updates(self) -> None:
        """The report counts updated records per list."""
        handler = GDPRHandler(Pseudonymizer(salt="test-salt"))
        events, units = _records()

        result = handler.erase_actor("actor-1", events, units)

        assert result["audit_events_updated"] == 1
        assert result["information_units_updated"] == 1
