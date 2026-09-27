"""Mirror / copied-content detection (§41.7).

Two sources are considered mirrors when their normalized fingerprints are
equal or when the word-shingle Jaccard similarity of their contents reaches
the configured threshold. The detector answers ``mirror_of`` with the
``SRC_{ULID}`` identifier of the source being mirrored, or ``None``.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from collections.abc import Sequence

#: Jaccard similarity at or above which two contents are considered copies.
DEFAULT_MIRROR_THRESHOLD = 0.9

_NON_WORD = re.compile(r"[^\w\s]", re.UNICODE)
_SPACES = re.compile(r"\s+", re.UNICODE)


def normalize_text(text: str) -> str:
    """Lowercase, strip punctuation and collapse whitespace."""
    lowered = _NON_WORD.sub(" ", text.casefold())
    return _SPACES.sub(" ", lowered).strip()


def content_fingerprint(text: str) -> str:
    """Return the SHA-256 fingerprint of the normalized text."""
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def _shingles(text: str, size: int = 3) -> frozenset[str]:
    words = normalize_text(text).split()
    if not words:
        return frozenset()
    if len(words) < size:
        return frozenset(" ".join(words) for _ in (0,))
    return frozenset(" ".join(words[i : i + size]) for i in range(len(words) - size + 1))


def similarity(a: str, b: str) -> float:
    """Word-shingle Jaccard similarity of two texts, in ``[0, 1]``."""
    if content_fingerprint(a) == content_fingerprint(b):
        return 1.0
    left, right = _shingles(a), _shingles(b)
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def detect_mirror(
    text: str,
    candidates: Sequence[tuple[str, str]],
    *,
    threshold: float = DEFAULT_MIRROR_THRESHOLD,
) -> str | None:
    """Return the ``SRC_{ULID}`` of the first candidate mirroring *text*.

    Args:
        text: content attributed to the source under examination.
        candidates: ``(source_id, text)`` pairs of the *other* sources
            already known to the system.
        threshold: minimum shingle similarity to declare a mirror.
    """
    own = content_fingerprint(text)
    fingerprinted: Iterable[tuple[str, str]] = candidates
    for source_id, other in fingerprinted:
        if content_fingerprint(other) == own:
            return source_id
    for source_id, other in candidates:
        if similarity(text, other) >= threshold:
            return source_id
    return None
