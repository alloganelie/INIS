"""Upload size policy for the §36.6/§36.7 ingestion path (§41.2).

Three ceilings can apply to one upload, and the **strictest wins**:

1. ``budget.max_storage_bytes`` carried by the request (§41.2) — the requester
   bought a storage envelope, so it must be enforceable, not decorative;
2. ``INIS_MAX_UPLOAD_BYTES`` — the deployment's operational ceiling;
3. :data:`DEFAULT_MAX_UPLOAD_BYTES` — the platform default, mirrored by
   ``[limits].max_upload_bytes`` in every ``configs/*.toml`` (asserted by
   ``tests/unit/core/test_config.py``, the same convention as
   ``app/planning/limits.py`` for ``max_plan_steps``).

A limit that cannot be read (unset, or a value that is not a positive integer) is
ignored rather than silently turned into "zero" or "unlimited".
"""

from __future__ import annotations

import os
from typing import Any

__all__ = [
    "DEFAULT_MAX_UPLOAD_BYTES",
    "MAX_UPLOAD_BYTES_ENV",
    "effective_max_upload_bytes",
    "overflow_message",
]

#: 25 MiB: the platform default, mirrored by ``[limits].max_upload_bytes``.
DEFAULT_MAX_UPLOAD_BYTES = 25 * 1024 * 1024

#: Environment variable overriding the platform default.
MAX_UPLOAD_BYTES_ENV = "INIS_MAX_UPLOAD_BYTES"


def _as_positive_int(value: Any) -> int | None:
    """Return *value* as a positive ``int``, or ``None`` when unusable."""
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _budget_ceiling(budget: Any | None) -> int | None:
    """Return the storage ceiling of *budget* (dataclass, model or mapping)."""
    if budget is None:
        return None
    if isinstance(budget, dict):
        return _as_positive_int(budget.get("max_storage_bytes"))
    return _as_positive_int(getattr(budget, "max_storage_bytes", None))


def effective_max_upload_bytes(budget: Any | None = None) -> int:
    """Return the byte ceiling to apply to one upload.

    Args:
        budget: The request's §41.2 budget (``RequestBudget``, ``Budget`` or a
            mapping); ``None`` when the request carries none.

    Returns:
        The smallest of the applicable ceilings, never ``0``.
    """
    candidates = [
        ceiling
        for ceiling in (
            _budget_ceiling(budget),
            _as_positive_int(os.getenv(MAX_UPLOAD_BYTES_ENV)),
            DEFAULT_MAX_UPLOAD_BYTES,
        )
        if ceiling is not None
    ]
    return min(candidates) if candidates else DEFAULT_MAX_UPLOAD_BYTES


def overflow_message(limit: int, received: int | None = None) -> str:
    """Return the §25.2 message of a refused oversized upload."""
    detail = f" (reçu : {received} octets)" if received is not None else ""
    return (
        f"Document refusé : taille supérieure à la limite autorisée de {limit} octets"
        f"{detail} — §41.2 (budget.max_storage_bytes) et [limits].max_upload_bytes."
    )
