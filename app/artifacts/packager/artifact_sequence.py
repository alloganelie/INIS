"""Allocation of the §24.2 ``ART_{YYYY}_{SEQ6}`` artifact identifier.

``artifact_id`` is *not* a ULID (§0.3 does not cover it), so it is built and
validated here:

* the *authoritative* allocator is the database —
  ``ArtifactRepository.allocate_artifact_id`` reads and increments
  ``artifact_id_sequences`` (revision 0013) inside a transaction, which is what
  makes the sequence survive a restart and stay unique across the API workers;
* :class:`InProcessArtifactSequence` is the last resort for the no-database
  mode. It cannot guarantee uniqueness across processes, so a caller that uses
  it must say so in the delivery ``limitations`` (§25.2) — never pretend the
  identifier is authoritative.
"""

from __future__ import annotations

import re
import threading
from datetime import UTC, datetime

from app.core.errors import ValidationError
from app.core.time import utc_now

__all__ = [
    "ANNUAL_CAPACITY",
    "ARTIFACT_ID_PATTERN",
    "InProcessArtifactSequence",
    "artifact_year",
    "format_artifact_id",
    "parse_artifact_id",
]

#: ``ART_{YYYY}_{SEQ6}`` — the §24.2 identifier format.
ARTIFACT_ID_PATTERN = re.compile(r"^ART_(\d{4})_(\d{6})$")

#: Width of the zero-padded sequence, fixed by §24.2 (``SEQ6``).
SEQUENCE_WIDTH = 6

#: Exhaustion point of one year: the 1 000 000th artifact cannot be numbered.
ANNUAL_CAPACITY = 10**SEQUENCE_WIDTH


def artifact_year(moment: datetime | None = None) -> int:
    """Return the UTC calendar year a new artifact belongs to (§24.2)."""
    current = moment or utc_now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return current.astimezone(UTC).year


def format_artifact_id(year: int, sequence: int) -> str:
    """Return the §24.2 identifier of the *sequence*-th artifact of *year* (1-based).

    Raises:
        ValidationError: When the sequence is already exhausted — silently
            wrapping to ``000001`` would hand two artifacts the same identifier.
    """
    if not 1 <= sequence < ANNUAL_CAPACITY:
        raise ValidationError(
            f"artifact sequence {sequence} is outside 1..{ANNUAL_CAPACITY - 1} for "
            f"year {year} (§24.2 SEQ6): the yearly identifier space is exhausted."
        )
    return f"ART_{year:04d}_{sequence:0{SEQUENCE_WIDTH}d}"


def parse_artifact_id(artifact_id: str) -> tuple[int, int] | None:
    """Return ``(year, sequence)`` of *artifact_id*, or ``None`` when malformed."""
    match = ARTIFACT_ID_PATTERN.match(str(artifact_id or ""))
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


class InProcessArtifactSequence:
    """Process-local §24.2 sequence, used only when no database is configured.

    Thread-safe (the API runs the pipeline in worker threads), but not
    cross-process: two workers would both start at ``000001``. Callers therefore
    report the degradation in the delivery ``limitations``.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[int, int] = {}

    def next(self, year: int | None = None) -> str:
        """Return the next identifier of *year* (defaults to the current year)."""
        target = year if year is not None else artifact_year()
        with self._lock:
            value = self._counters.get(target, 0) + 1
            self._counters[target] = value
        return format_artifact_id(target, value)

    def reset(self) -> None:
        """Forget the counters (test isolation)."""
        with self._lock:
            self._counters.clear()
