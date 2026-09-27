"""Unit tests for the §41.5 L1/L2 cache and its invalidation policy."""

from datetime import UTC, datetime, timedelta

import pytest

from app.storage.cache.cache_store import (
    INVALIDATION_TRIGGERS,
    L1,
    L2,
    CacheEntry,
    CacheInvalidationPolicy,
    CacheStore,
    InMemoryBackend,
    make_cache_key,
)

SRC_A = "SRC_01ARZ3NDEKTSV4RRFFQ69G5F01"
SRC_B = "SRC_01ARZ3NDEKTSV4RRFFQ69G5F02"


def fresh(hours_ago: float = 0.0) -> datetime:
    return datetime.now(UTC) - timedelta(hours=hours_ago)


def test_invalidation_triggers_match_the_spec() -> None:
    assert INVALIDATION_TRIGGERS == (
        "on_source_update",
        "on_conflict_detected",
        "on_quality_failure",
    )


def test_cache_key_is_deterministic_and_namespaced() -> None:
    assert make_cache_key("web", "a", 1) == make_cache_key("web", "a", 1)
    assert make_cache_key("web", "a", 1) != make_cache_key("web", "a", 2)
    assert make_cache_key("web", "a").startswith("web:")


def test_policy_rejects_invalid_configuration() -> None:
    with pytest.raises(ValueError, match="max_ttl_seconds"):
        CacheInvalidationPolicy(max_ttl_seconds=0)
    with pytest.raises(ValueError, match="freshness_threshold_hours"):
        CacheInvalidationPolicy(freshness_threshold_hours=-1)


def test_policy_to_dict_exposes_the_config_block() -> None:
    assert set(CacheInvalidationPolicy().to_dict()) == set(INVALIDATION_TRIGGERS) | {
        "max_ttl_seconds",
        "freshness_threshold_hours",
    }


def test_policy_should_invalidate_rejects_unknown_trigger() -> None:
    with pytest.raises(KeyError, match="unknown trigger"):
        CacheInvalidationPolicy().should_invalidate("on_full_moon")


def test_policy_clamps_ttl_to_max() -> None:
    policy = CacheInvalidationPolicy(max_ttl_seconds=100)
    assert policy.clamp_ttl(None) == 100
    assert policy.clamp_ttl(50) == 50
    assert policy.clamp_ttl(500) == 100
    assert policy.clamp_ttl(-5) == 0


def test_store_roundtrips_a_fresh_value() -> None:
    store = CacheStore()
    store.set("web", "climate", value=["r"], source_freshness=fresh(), source_id=SRC_A)
    assert store.get("web", "climate") == ["r"]
    assert store.stats()["hits"] == 1


def test_store_returns_none_for_unknown_key() -> None:
    store = CacheStore()
    assert store.get("web", "unknown") is None
    assert store.stats()["misses"] == 1


def test_stale_entry_is_never_reused() -> None:
    """§41.5 hard rule: source_freshness below the threshold must not be reused."""
    store = CacheStore(CacheInvalidationPolicy(freshness_threshold_hours=24))
    store.set("web", "old", value=["stale"], source_freshness=fresh(48), source_id=SRC_A)
    assert store.get("web", "old") is None
    assert store.stats()["stale_rejections"] == 1


def test_entry_without_freshness_is_rejected_by_a_positive_threshold() -> None:
    store = CacheStore(CacheInvalidationPolicy(freshness_threshold_hours=1))
    store.set("web", "x", value=1)
    assert store.get("web", "x") is None


def test_zero_threshold_allows_entries_without_freshness() -> None:
    store = CacheStore(CacheInvalidationPolicy(freshness_threshold_hours=0))
    store.set("web", "x", value=1)
    assert store.get("web", "x") == 1


def test_expired_entry_is_dropped() -> None:
    store = CacheStore(CacheInvalidationPolicy(max_ttl_seconds=1))
    entry = store.set("web", "x", value=1, ttl_seconds=1, source_freshness=fresh())
    expired = CacheEntry(
        key=entry.key,
        value=entry.value,
        level=entry.level,
        created_at=entry.created_at,
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    assert expired.is_expired() is True


def test_levels_are_isolated_when_backends_differ() -> None:
    l1, l2 = InMemoryBackend(), InMemoryBackend()
    store = CacheStore(l1_backend=l1, l2_backend=l2)
    store.set("unit", "k", value="l1", level=L1, source_freshness=fresh())
    store.set("unit", "k", value="l2", level=L2, source_freshness=fresh())
    assert store.get("unit", "k", level=L1) == "l1"
    assert store.get("unit", "k", level=L2) == "l2"


def test_unknown_level_is_rejected() -> None:
    store = CacheStore()
    with pytest.raises(ValueError, match="unknown cache level"):
        store.get("unit", "k", level="L9")


def test_invalidate_on_source_update_drops_matching_entries() -> None:
    store = CacheStore()
    store.set("web", "a", value=1, source_freshness=fresh(), source_id=SRC_A)
    store.set("web", "b", value=2, source_freshness=fresh(), source_id=SRC_B)
    assert store.invalidate_source(SRC_A) == 1
    assert store.get("web", "a") is None
    assert store.get("web", "b") == 2


def test_invalidate_conflict_and_quality_triggers() -> None:
    store = CacheStore()
    store.set("web", "a", value=1, source_freshness=fresh(), source_id=SRC_A)
    assert store.invalidate("on_conflict_detected") == 1

    store.set("web", "b", value=1, source_freshness=fresh(), source_id=SRC_A)
    assert store.invalidate("on_quality_failure") == 1


def test_disabled_trigger_is_a_noop() -> None:
    store = CacheStore(CacheInvalidationPolicy(on_source_update=False))
    store.set("web", "a", value=1, source_freshness=fresh(), source_id=SRC_A)
    assert store.invalidate("on_source_update") == 0
    assert store.get("web", "a") == 1


def test_delete_removes_an_entry() -> None:
    store = CacheStore()
    store.set("web", "a", value=1, source_freshness=fresh())
    store.delete("web", "a")
    assert store.get("web", "a") is None


def test_stats_report_hit_rate() -> None:
    store = CacheStore()
    store.set("web", "a", value=1, source_freshness=fresh())
    store.get("web", "a")
    store.get("web", "missing")
    stats = store.stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["hit_rate"] == pytest.approx(0.5)


def test_clear_empties_the_store() -> None:
    store = CacheStore()
    store.set("web", "a", value=1, source_freshness=fresh())
    store.clear()
    assert store.get("web", "a") is None


def test_entry_to_dict_is_iso_utc() -> None:
    store = CacheStore()
    entry = store.set("web", "a", value=1, source_freshness=fresh(), source_id=SRC_A)
    payload = entry.to_dict()
    assert payload["created_at"].endswith("Z")
    assert payload["source_id"] == SRC_A
    assert payload["level"] == L1
