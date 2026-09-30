"""ADR 007 — the threshold beyond which extraction works by chunks (§41.6).

``docs/adr/007_chunked_processing_threshold.md`` fixes a strict ceiling:
``max_information_units_per_request`` (default **50**). Beyond it, chunking
becomes mandatory *before* any extraction, and every fragment keeps its
lineage. Until now that ceiling existed only in the ADR text: nothing read it,
so the §41.6 processor was never reached by the real ingestion path.

The threshold is resolved the same way ``app/planning/limits.py`` resolves
``max_plan_steps``:

1. ``MAX_INFORMATION_UNITS_PER_REQUEST`` — the deployment's value;
2. ``DEFAULT_MAX_INFORMATION_UNITS_PER_REQUEST`` — the ADR default, mirrored by
   ``[limits].max_information_units_per_request`` in every ``configs/*.toml``
   (the mirror is asserted by ``tests/unit/core/test_config.py``).

A value that cannot be read (unset, non-integer, zero) falls back to the ADR
default rather than silently becoming "no limit": a threshold nobody can state
is a threshold nobody enforces.

:func:`chunked_processing_config` turns the threshold into the §41.6
``[CONFIG]`` block, so the two never drift: ``max_in_memory_rows`` (when
streaming starts) and ``chunk_size_rows`` (how large a chunk is) are the same
number, which is exactly what the ADR mandates.
"""

from __future__ import annotations

import os
from typing import Final

from app.knowledge.normalization.chunked_dataset import (
    DEFAULT_MAX_IN_MEMORY_BYTES,
    DEFAULT_PARALLEL_CHUNKS,
    ChunkedProcessingConfig,
)

__all__ = [
    "DEFAULT_MAX_INFORMATION_UNITS_PER_REQUEST",
    "MAX_INFORMATION_UNITS_PER_REQUEST_ENV",
    "chunked_processing_config",
    "max_information_units_per_request",
]

#: ADR 007 — default ceiling of information units for one request.
DEFAULT_MAX_INFORMATION_UNITS_PER_REQUEST: Final[int] = 50

#: Environment variable overriding the ADR default.
MAX_INFORMATION_UNITS_PER_REQUEST_ENV: Final[str] = "MAX_INFORMATION_UNITS_PER_REQUEST"


def max_information_units_per_request() -> int:
    """Return the active ADR 007 threshold (always ``>= 1``).

    Returns:
        The configured ceiling of information units per request, or the ADR
        default when the environment holds no usable value.
    """
    raw = os.getenv(MAX_INFORMATION_UNITS_PER_REQUEST_ENV)
    if raw is None or not str(raw).strip():
        return DEFAULT_MAX_INFORMATION_UNITS_PER_REQUEST
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return DEFAULT_MAX_INFORMATION_UNITS_PER_REQUEST
    return value if value > 0 else DEFAULT_MAX_INFORMATION_UNITS_PER_REQUEST


def chunked_processing_config(
    threshold: int | None = None,
    *,
    parallel_chunks: int | None = None,
) -> ChunkedProcessingConfig:
    """Return the §41.6 ``[CONFIG]`` block of the ADR 007 threshold.

    Args:
        threshold: Explicit ceiling; :func:`max_information_units_per_request`
            when omitted.
        parallel_chunks: Cap on chunks in flight; the §41.6 default when
            omitted.

    Returns:
        A config whose ``should_stream(row_count)`` is true exactly **beyond**
        the ADR threshold (``row_count > threshold``) and whose chunks hold at
        most ``threshold`` items. ``max_in_memory_bytes`` keeps its §41.6
        default: an ingested payload is already bounded by the §41.2/§36.6
        upload ceiling, so the row threshold is the one that can be crossed.
    """
    limit = threshold if threshold is not None else max_information_units_per_request()
    if limit < 1:
        raise ValueError("threshold must be >= 1")
    return ChunkedProcessingConfig(
        max_in_memory_rows=limit,
        max_in_memory_bytes=DEFAULT_MAX_IN_MEMORY_BYTES,
        chunk_size_rows=limit,
        parallel_chunks=parallel_chunks or DEFAULT_PARALLEL_CHUNKS,
    )
