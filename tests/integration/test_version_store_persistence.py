"""L6.3 — the §18.1 version chain must outlive the process.

``VersionStore`` kept version chains and archive marks in memory: a restart
erased the history of every governed resource, which is precisely what §18.1
asks to keep. ``DurableVersionStore`` writes the same chain to
``information_versions`` (revision 0007), under the same method names, and the
§21 tools accept both stores.

The "restart" here is a **new store over a new engine**: if the chain were still
held in memory, the fresh instance would return an empty list.
"""

from __future__ import annotations

import pytest

from app.storage.database.engine import create_engine
from app.tools.governance_tools.versioning import (
    DurableVersionStore,
    archive_record,
    create_version,
)

RESOURCE_ID = "INF_L6_VERSIONED"


@pytest.mark.asyncio
async def test_version_chain_survives_a_new_store(
    db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two versions and an archive mark are readable from a second store."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)

    engine = create_engine(db_url)
    store = DurableVersionStore(engine)
    try:
        first = await create_version(
            RESOURCE_ID,
            {"actor": "agent:codex", "justification": "correction §11"},
            store=store,
        )
        second = await create_version(
            RESOURCE_ID,
            {"actor": "agent:codex", "justification": "enrichissement"},
            store=store,
        )
        assert first.startswith("VER_")
        assert second != first

        archived_at = await store.archive(RESOURCE_ID)
        assert archived_at
        # Archiving is idempotent: the first timestamp is kept (§18.3).
        assert await store.archive(RESOURCE_ID) == archived_at
    finally:
        await engine.dispose()

    # A new engine and a new store: nothing of the previous process is reused.
    fresh_engine = create_engine(db_url)
    fresh = DurableVersionStore(fresh_engine)
    try:
        chain = await fresh.versions(RESOURCE_ID)
        ids = [entry.get("version_id") for entry in chain]
        assert first in ids
        assert second in ids
        # The chain is ordered and the parent link names the previous version.
        versions_only = [entry for entry in chain if entry.get("action") != "archive"]
        assert [entry["version_id"] for entry in versions_only] == [first, second]
        assert versions_only[0]["parent_version"] is None
        assert versions_only[1]["parent_version"] == first
        assert versions_only[0]["actor"] == "agent:codex"
        assert versions_only[0]["hash"]

        assert await fresh.is_archived(RESOURCE_ID) is True
        assert await fresh.archived_at(RESOURCE_ID) == archived_at
    finally:
        await fresh_engine.dispose()


@pytest.mark.asyncio
async def test_unknown_resource_has_no_chain(db_url: str) -> None:
    """A resource that was never versioned returns an empty chain, not a guess."""
    engine = create_engine(db_url)
    store = DurableVersionStore(engine)
    try:
        assert await store.versions("INF_L6_NEVER_SEEN") == []
        assert await store.is_archived("INF_L6_NEVER_SEEN") is False
        assert await store.archived_at("INF_L6_NEVER_SEEN") is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_archive_record_tool_accepts_the_durable_store(db_url: str) -> None:
    """The §21 tool works with the durable store (awaitable result)."""
    engine = create_engine(db_url)
    store = DurableVersionStore(engine)
    try:
        version_id = await create_version(
            "INF_L6_TOOL", {"actor": "agent:test"}, store=store
        )
        assert version_id.startswith("VER_")
        await archive_record("INF_L6_TOOL", store=store)
        assert await store.is_archived("INF_L6_TOOL") is True
    finally:
        await engine.dispose()
