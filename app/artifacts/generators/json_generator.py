"""JSON export of a §24 delivery payload.

The bytes come from :func:`app.core.hashing.canonical_json`: sorted keys,
compact separators, ``ensure_ascii=False``. A canonical document is what makes
the delivery *verifiable*: a client that recomputes the SHA-256 of the file it
received gets exactly the ``sha256`` the §24.2 record announces, which a
pretty-printed JSON would not guarantee. Accented text is kept as UTF-8 rather
than escaped, so the delivered file is readable by a human too.
"""

from __future__ import annotations

from typing import Any

from app.core.errors import ValidationError
from app.core.hashing import canonical_json

__all__ = ["generate_json"]


def generate_json(payload: Any) -> bytes:
    """Return the canonical JSON bytes of *payload* (§24.2).

    Args:
        payload: The §24.1 delivery payload (or any JSON-serialisable value).

    Returns:
        The UTF-8 encoded canonical JSON document: keys sorted, no padding.

    Raises:
        ValidationError: When *payload* is ``None`` — an empty document is not a
            delivery, and writing ``null`` would look like one.
    """
    if payload is None:
        raise ValidationError(
            "generate_json refuses a null payload (§24.2): an empty JSON file is "
            "not a deliverable."
        )
    return canonical_json(payload).encode("utf-8")
