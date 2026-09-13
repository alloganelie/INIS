"""Tests for in-memory resource lineage tracking."""

from app.provenance.lineage_tracker import LineageTracker


def test_lineage_tracker_records_direct_relationships() -> None:
    tracker = LineageTracker()
    tracker.record("TRF_01", ["INF_01"], ["INF_02"])

    assert tracker.get_lineage("INF_02")["ancestry"] == ["INF_01"]
    assert tracker.get_lineage("INF_01")["descendants"] == ["INF_02"]


def test_lineage_tracker_returns_transitive_relationships() -> None:
    tracker = LineageTracker()
    tracker.record("TRF_01", ["INF_01"], ["INF_02"])
    tracker.record("TRF_02", ["INF_02"], ["INF_03"])

    assert tracker.get_lineage("INF_03")["ancestry"] == ["INF_01", "INF_02"]
    assert tracker.get_lineage("INF_01")["descendants"] == ["INF_02", "INF_03"]


def test_lineage_tracker_returns_empty_lineage_for_unknown_resource() -> None:
    assert LineageTracker().get_lineage("INF_unknown") == {
        "ancestry": [],
        "descendants": [],
    }
