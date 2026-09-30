"""Upload size policy for the §36.6/§36.7 ingestion path (§41.2).

The ceiling itself lives in :mod:`app.core.size_limits`, because it is not
upload-specific: the same ``[limits].max_upload_bytes`` bounds what INIS accepts
to *read* from a source (a local file or an object in the §4.3 store). This
module keeps the historical import path (the documents router and the config test
use it) and the upload-specific message.
"""

from __future__ import annotations

from app.core.size_limits import (
    DEFAULT_MAX_UPLOAD_BYTES,
    MAX_UPLOAD_BYTES_ENV,
    effective_max_upload_bytes,
    size_overflow_message,
)

__all__ = [
    "DEFAULT_MAX_UPLOAD_BYTES",
    "MAX_UPLOAD_BYTES_ENV",
    "effective_max_upload_bytes",
    "overflow_message",
]


def overflow_message(limit: int, received: int | None = None) -> str:
    """Return the §25.2 message of a refused oversized upload."""
    return size_overflow_message(limit, received)
