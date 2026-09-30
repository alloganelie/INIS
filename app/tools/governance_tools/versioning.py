"""``create_version`` and ``archive_record`` internal tools per §21 (§18).

Two stores implement §18.1:

* :class:`VersionStore` — the injectable in-process store, still the default for
  a single test or an ephemeral run;
* :class:`DurableVersionStore` — the same chain persisted in
  ``information_versions`` (revision 0007), so it *survives a restart*; it is
  the store to inject when the history of a governed resource must outlive the
  process (§18.1, L6.3).

Its methods are ``async``; :func:`create_version` / :func:`archive_record`
accept both stores and await whatever the store returns.
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from app.core.errors import ValidationError
from app.core.hashing import canonical_json, sha256_hex
from app.domain.value_objects.ulid import ULID

__all__ = [
    "DurableVersionStore",
    "VersionStore",
    "archive_record",
    "create_version",
    "default_store",
]


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class VersionStore:
    """In-process §18.1 version chains and archive marks per resource."""

    def __init__(self) -> None:
        self._chains: dict[str, list[dict[str, Any]]] = {}
        self._archived_at: dict[str, str] = {}

    def create_version(self, resource_id: str, change: Mapping[str, Any]) -> str:
        """Append a version to *resource_id*'s chain and return its id."""
        chain = self._chains.setdefault(resource_id, [])
        version_id = ULID.new("VER_")
        parent_version = chain[-1]["version_id"] if chain else None
        chain.append(
            {
                "version_id": version_id,
                "resource_id": resource_id,
                "parent_version": parent_version,
                "timestamp": _utc_timestamp(),
                "actor": str(change.get("actor") or "system"),
                "hash": sha256_hex(canonical_json(dict(change))),
                "justification": str(change.get("justification") or ""),
                "change": dict(change),
            }
        )
        return version_id

    def versions(self, resource_id: str) -> list[dict[str, Any]]:
        """Return the version chain recorded for *resource_id*."""
        return list(self._chains.get(resource_id, []))

    def archive(self, resource_id: str) -> str:
        """Mark *resource_id* archived (idempotent); return the archive time."""
        archived_at = self._archived_at.get(resource_id)
        if archived_at is None:
            archived_at = _utc_timestamp()
            self._archived_at[resource_id] = archived_at
        return archived_at

    def is_archived(self, resource_id: str) -> bool:
        """Return whether *resource_id* has been archived."""
        return resource_id in self._archived_at

    def archived_at(self, resource_id: str) -> str | None:
        """Return the archive timestamp for *resource_id*, if archived."""
        return self._archived_at.get(resource_id)


class DurableVersionStore:
    """The §18.1 chain of :class:`VersionStore`, persisted in PostgreSQL.

    Same method names, ``async``: the tools await the result, so a caller
    injects this store instead of the in-process one and the history outlives
    the process. An archive mark is a version of the resource that says so
    (``action = "archive"``), which keeps one table and one read path.
    """

    def __init__(self, engine: Any) -> None:
        self._engine = engine

    @staticmethod
    def _record(resource_id: str, change: Mapping[str, Any], *, parent: str | None) -> dict[str, Any]:
        """Build the stored payload of one version (same shape as in-process)."""
        return {
            "version_id": ULID.new("VER_"),
            "resource_id": resource_id,
            "parent_version": parent,
            "timestamp": _utc_timestamp(),
            "actor": str(change.get("actor") or "system"),
            "hash": sha256_hex(canonical_json(dict(change))),
            "justification": str(change.get("justification") or ""),
            "change": dict(change),
        }

    async def create_version(self, resource_id: str, change: Mapping[str, Any]) -> str:
        """Append a version to *resource_id*'s chain and return its id."""
        from app.storage.repositories.version_repository import (
            InformationVersionRepository,
        )

        latest = await InformationVersionRepository.latest(self._engine, resource_id)
        parent = latest["version_id"] if latest else None
        record = self._record(resource_id, change, parent=parent)
        await InformationVersionRepository.append(self._engine, resource_id, record)
        return str(record["version_id"])

    async def versions(self, resource_id: str) -> list[dict[str, Any]]:
        """Return the persisted chain of *resource_id*, oldest version first."""
        from app.storage.repositories.version_repository import (
            InformationVersionRepository,
        )

        chain = await InformationVersionRepository.list_for(self._engine, resource_id)
        return [version["content"] for version in chain]

    async def archive(self, resource_id: str) -> str:
        """Mark *resource_id* archived (idempotent); return the archive time."""
        from app.storage.repositories.version_repository import (
            ARCHIVE_ACTION,
            InformationVersionRepository,
        )

        mark = await InformationVersionRepository.archive_mark(self._engine, resource_id)
        if mark is not None:
            return str(mark["content"].get("archived_at") or "")
        archived_at = _utc_timestamp()
        await InformationVersionRepository.append(
            self._engine,
            resource_id,
            {
                # An archive mark is a version of the resource that says so:
                # it carries an identifier like every other entry of the chain.
                "version_id": ULID.new("VER_"),
                "action": ARCHIVE_ACTION,
                "archived_at": archived_at,
                "actor": "system",
                "justification": "archive_record (§18.3)",
            },
        )
        return archived_at

    async def is_archived(self, resource_id: str) -> bool:
        """Return whether *resource_id* has a persisted archive mark."""
        from app.storage.repositories.version_repository import (
            InformationVersionRepository,
        )

        return await InformationVersionRepository.archive_mark(self._engine, resource_id) is not None

    async def archived_at(self, resource_id: str) -> str | None:
        """Return the persisted archive timestamp for *resource_id*, if any."""
        from app.storage.repositories.version_repository import (
            InformationVersionRepository,
        )

        mark = await InformationVersionRepository.archive_mark(self._engine, resource_id)
        if mark is None:
            return None
        return str(mark["content"].get("archived_at") or "") or None


_STORE: VersionStore | None = None


async def _maybe_await(value: Any) -> Any:
    """Return *value*, awaiting it when the store is asynchronous.

    :class:`VersionStore` is synchronous (in-process) and
    :class:`DurableVersionStore` is asynchronous (PostgreSQL): the two tools
    below accept both, so a caller never has to know which one it injected.
    """
    if inspect.isawaitable(value):
        return await value
    return value


def default_store() -> VersionStore:
    """Return the process-wide default version store."""
    global _STORE
    if _STORE is None:
        _STORE = VersionStore()
    return _STORE


async def create_version(
    resource_id: str,
    change: Mapping[str, Any],
    *,
    store: VersionStore | None = None,
) -> str:
    """Create a new version of *resource_id* and return the version id (§21).

    Args:
        resource_id: Identifier of the versioned resource (§18.1).
        change: Change description; ``actor`` and ``justification`` are stored
            as required by §18.1.
        store: Injected store; defaults to :func:`default_store`.

    Returns:
        The new ``VER_`` version identifier.

    Raises:
        ValidationError: If *resource_id* is empty or *change* is not a
            non-empty mapping.
    """
    if not resource_id or not str(resource_id).strip():
        raise ValidationError("resource_id is required to version a record (§18.1)")
    if not isinstance(change, Mapping) or not change:
        raise ValidationError("change must be a non-empty mapping (§18.1)")
    active = store if store is not None else default_store()
    return await _maybe_await(active.create_version(resource_id, change))


async def archive_record(
    resource_id: str,
    *,
    store: VersionStore | None = None,
) -> None:
    """Archive *resource_id* (§18.3, §21 signature).

    Archiving is idempotent: repeating it keeps the original archive
    timestamp. The caller is expected to pair the mark with
    ``write_audit_event`` for the durable §20 trail.

    Args:
        resource_id: Identifier of the record to archive.
        store: Injected store; defaults to :func:`default_store`.

    Raises:
        ValidationError: If *resource_id* is empty.
    """
    if not resource_id or not str(resource_id).strip():
        raise ValidationError("resource_id is required to archive a record (§18.3)")
    active = store if store is not None else default_store()
    await _maybe_await(active.archive(resource_id))
