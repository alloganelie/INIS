"""Unit tests for the §18.1 versioning contract (§21 tools).

``create_version`` / ``archive_record`` are the V1 implementation of the
versioning rules: an append-only per-resource chain of ``VER_`` records (with
parent link, actor, justification and content hash) plus an idempotent archive
mark. Both are exercised through the tools and through the store they use.
"""

from __future__ import annotations

import pytest

from app.core.errors import ValidationError
from app.domain.value_objects.ulid import ULID
from app.tools.governance_tools.versioning import (
    VersionStore,
    archive_record,
    create_version,
    default_store,
)


@pytest.fixture
def store() -> VersionStore:
    """Return an isolated in-process version store."""
    return VersionStore()


class TestCreateVersion:
    """§18.1 — every change produces one immutable version record."""

    async def test_returns_a_ver_identifier(self, store: VersionStore) -> None:
        """The new version id uses the ``VER_`` prefix of §18.1."""
        version_id = await create_version("SRC_1", {"field": "title"}, store=store)
        assert version_id.startswith("VER_")
        assert ULID.is_valid(version_id)

    async def test_chain_is_append_only_with_parent_links(
        self, store: VersionStore
    ) -> None:
        """Each version points at the previous one (a chain, not a list)."""
        first = await create_version("SRC_1", {"field": "title"}, store=store)
        second = await create_version("SRC_1", {"field": "url"}, store=store)
        chain = store.versions("SRC_1")
        assert [entry["version_id"] for entry in chain] == [first, second]
        assert chain[0]["parent_version"] is None
        assert chain[1]["parent_version"] == first

    async def test_chains_are_per_resource(self, store: VersionStore) -> None:
        """Two resources do not share a version chain."""
        await create_version("SRC_1", {"field": "title"}, store=store)
        await create_version("SRC_2", {"field": "title"}, store=store)
        assert len(store.versions("SRC_1")) == 1
        assert len(store.versions("SRC_2")) == 1

    async def test_actor_and_justification_are_stored(
        self, store: VersionStore
    ) -> None:
        """§18.1 requires both the actor and the reason of the change."""
        await create_version(
            "SRC_1",
            {"actor": "AGT_1", "justification": "source URL corrected"},
            store=store,
        )
        entry = store.versions("SRC_1")[0]
        assert entry["actor"] == "AGT_1"
        assert entry["justification"] == "source URL corrected"

    async def test_actor_defaults_to_system(self, store: VersionStore) -> None:
        """A change without an actor is attributed to the system."""
        await create_version("SRC_1", {"field": "title"}, store=store)
        assert store.versions("SRC_1")[0]["actor"] == "system"

    async def test_change_is_hashed(self, store: VersionStore) -> None:
        """A stable sha256 hash makes the record tamper-evident."""
        await create_version("SRC_1", {"field": "title"}, store=store)
        await create_version("SRC_1", {"field": "url"}, store=store)
        chain = store.versions("SRC_1")
        assert all(len(entry["hash"]) == 64 for entry in chain)
        assert chain[0]["hash"] != chain[1]["hash"]

    async def test_identical_change_produces_an_identical_hash(
        self, store: VersionStore
    ) -> None:
        """Hashing is canonical: key order does not change the digest."""
        await create_version("SRC_1", {"a": 1, "b": 2}, store=store)
        await create_version("SRC_1", {"b": 2, "a": 1}, store=store)
        chain = store.versions("SRC_1")
        assert chain[0]["hash"] == chain[1]["hash"]
        assert chain[0]["version_id"] != chain[1]["version_id"]

    @pytest.mark.parametrize("resource_id", ["", "   "])
    async def test_empty_resource_id_is_refused(
        self, store: VersionStore, resource_id: str
    ) -> None:
        """A version without a subject is refused (§18.1)."""
        with pytest.raises(ValidationError, match="resource_id is required"):
            await create_version(resource_id, {"field": "title"}, store=store)

    @pytest.mark.parametrize("change", [{}, None, "text", 42])
    async def test_invalid_change_is_refused(
        self, store: VersionStore, change: object
    ) -> None:
        """A version without a non-empty change description is refused."""
        with pytest.raises(ValidationError, match="non-empty mapping"):
            await create_version("SRC_1", change, store=store)  # type: ignore[arg-type]

    async def test_versions_returns_a_copy(self, store: VersionStore) -> None:
        """Mutating the returned list does not corrupt the chain."""
        await create_version("SRC_1", {"field": "title"}, store=store)
        chain = store.versions("SRC_1")
        chain.clear()
        assert len(store.versions("SRC_1")) == 1

    async def test_unknown_resource_has_an_empty_chain(self, store: VersionStore) -> None:
        """An unversioned resource simply has no versions yet."""
        assert store.versions("SRC_unknown") == []


class TestArchiveRecord:
    """§18.3 — archiving is a mark, and it is idempotent."""

    async def test_archive_marks_the_record(self, store: VersionStore) -> None:
        """The record reports the archive state and timestamp."""
        assert store.is_archived("SRC_1") is False
        assert store.archived_at("SRC_1") is None
        await archive_record("SRC_1", store=store)
        assert store.is_archived("SRC_1") is True
        assert store.archived_at("SRC_1") is not None

    async def test_archive_is_idempotent(self, store: VersionStore) -> None:
        """Re-archiving keeps the first timestamp (no silent rewrite)."""
        await archive_record("SRC_1", store=store)
        first = store.archived_at("SRC_1")
        await archive_record("SRC_1", store=store)
        assert store.archived_at("SRC_1") == first

    async def test_archive_does_not_touch_other_records(self, store: VersionStore) -> None:
        """Archiving is per resource."""
        await archive_record("SRC_1", store=store)
        assert store.is_archived("SRC_2") is False

    @pytest.mark.parametrize("resource_id", ["", "   "])
    async def test_empty_resource_id_is_refused(
        self, store: VersionStore, resource_id: str
    ) -> None:
        """Archiving nothing is a validation error."""
        with pytest.raises(ValidationError, match="resource_id is required"):
            await archive_record(resource_id, store=store)


class TestDefaultStore:
    """§18.1 — the tools work without an injected store."""

    async def test_default_store_is_process_wide(self) -> None:
        """Two calls without an injected store share the same chain."""
        version_id = await create_version("SRC_default", {"field": "title"})
        assert version_id in [
            entry["version_id"] for entry in default_store().versions("SRC_default")
        ]

    def test_default_store_is_a_singleton(self) -> None:
        """``default_store`` always returns the same instance."""
        assert default_store() is default_store()

