"""``create_version`` and ``archive_record`` internal tools per §21 (§18).

V1 keeps version chains and archive marks in an injectable in-process store
(:class:`VersionStore`) because no version table exists yet (§18.1, §27).
Durable history is obtained by pairing these tools with
``write_audit_event`` (§20) when an audit engine is configured.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping

from app.core.errors import ValidationError
from app.core.hashing import canonical_json, sha256_hex
from app.domain.value_objects.ulid import ULID

__all__ = ["VersionStore", "archive_record", "create_version", "default_store"]


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


_STORE: VersionStore | None = None


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
    return active.create_version(resource_id, change)


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
    active.archive(resource_id)
