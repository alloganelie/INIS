"""§27/§0.2 — the platform clock has exactly one reader: ``app.core.time``.

``utc_now()`` replaced a scattered ``datetime.now(UTC)`` (and five local
``_utc_now`` copies spread over the code base). The guard at the end of this file
keeps the debt closed: a new direct clock read in ``app/`` is a regression, not a
style choice.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.core.time import utc_now

REPO_ROOT = Path(__file__).resolve().parents[3]
APP = REPO_ROOT / "app"

#: The only file allowed to read the clock: the helper itself.
ALLOWED = {APP / "core" / "time.py"}


class TestUtcNow:
    """The helper's contract is minimal and exact."""

    def test_returns_a_datetime(self) -> None:
        assert isinstance(utc_now(), datetime)

    def test_is_timezone_aware_and_utc(self) -> None:
        moment = utc_now()

        assert moment.tzinfo is not None, "un timestamp naïf est une régression"
        assert moment.utcoffset() == timedelta(0)
        assert moment.tzinfo is UTC

    def test_tracks_the_wall_clock(self) -> None:
        before = datetime.now(UTC)
        moment = utc_now()
        after = datetime.now(UTC)

        assert before <= moment <= after

    def test_successive_calls_never_go_backwards(self) -> None:
        assert utc_now() <= utc_now()

    def test_keeps_the_microsecond_precision_it_replaced(self) -> None:
        moment = utc_now()

        fraction = moment.isoformat().split(".")[-1].split("+")[0]
        assert len(fraction) == 6, "la précision ne change pas (microseconde)"

    def test_compares_with_an_aware_datetime(self) -> None:
        # A naive datetime comparison would raise: this proves awareness holds.
        assert utc_now() >= datetime(2020, 1, 1, tzinfo=UTC)


def test_no_direct_clock_read_remains_in_application_code() -> None:
    """A direct ``datetime.now(...)`` in ``app/`` reopens the closed debt."""
    patterns = ("datetime.now(", "datetime.utcnow(", "datetime.today(")
    offenders: list[str] = []
    for path in sorted(APP.rglob("*.py")):
        if path in ALLOWED:
            continue
        for number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if any(pattern in line for pattern in patterns):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{number}")

    assert offenders == [], f"lecture directe de l'horloge : {offenders}"
