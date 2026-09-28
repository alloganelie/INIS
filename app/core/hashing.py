"""Deterministic SHA-256 hashing helpers for INIS governance (§18.1, §20.1).

``before_hash`` and ``after_hash`` must be reproducible: the same logical
record always yields the same digest, whatever the insertion order of the
mapping keys. The canonical representation is therefore a compact, sorted-key
JSON document.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any
from typing import Mapping

__all__ = ["canonical_json", "sha256_hex", "record_hash", "before_hash", "after_hash"]


def sha256_hex(data: bytes | str) -> str:
    """Return the lowercase hexadecimal SHA-256 digest of *data*.

    Args:
        data: Raw bytes or UTF-8 text to hash.

    Returns:
        The 64-character hexadecimal digest.
    """
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def canonical_json(payload: Any) -> str:
    """Serialise *payload* to a deterministic JSON document.

    Keys are sorted, separators are compact and non-ASCII characters are kept
    as-is, so two equal mappings always produce the same string. Unknown types
    fall back to ``str()`` instead of raising.

    Args:
        payload: JSON-serialisable value to canonicalise.

    Returns:
        The canonical JSON document.
    """
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def record_hash(record: Mapping[str, Any] | list[Any] | None) -> str | None:
    """Return the deterministic SHA-256 digest of *record*.

    Args:
        record: Mapping or list describing the record. ``None`` means the
            record does not exist (creation, or absence before/after a
            deletion) and yields ``None`` rather than a digest of "null".

    Returns:
        The hexadecimal digest, or ``None`` when *record* is ``None``.
    """
    if record is None:
        return None
    return sha256_hex(canonical_json(record))


def before_hash(record: Mapping[str, Any] | list[Any] | None) -> str | None:
    """Return the digest of a record **before** modification (§20.1)."""
    return record_hash(record)


def after_hash(record: Mapping[str, Any] | list[Any] | None) -> str | None:
    """Return the digest of a record **after** modification (§20.1)."""
    return record_hash(record)

