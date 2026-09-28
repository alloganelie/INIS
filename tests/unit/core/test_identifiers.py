"""Unit tests for the §0.3 identifier contract.

The §0.3 registry lives in :mod:`app.core.constants` and is enforced by
:class:`app.domain.value_objects.ulid.ULID`; this module pins the invariants
every other zone relies on (prefix completeness, suffix validity, lexicographic
sortability, uniqueness).
"""

from __future__ import annotations

import time

import pytest

from app.core.constants import DATA_STAGES
from app.core.constants import ULID_PREFIXES
from app.domain.value_objects.ulid import ULID
from app.domain.value_objects.ulid import ULID_PREFIXES as IDENTIFIER_PREFIXES

#: Every prefix quoted by the §0.3 identifier table.
SPEC_PREFIXES = (
    "REQ_",
    "MSG_",
    "CORR_",
    "INF_",
    "SRC_",
    "DOC_",
    "DATA_",
    "EVID_",
    "CLM_",
    "CONFLICT_",
    "TRF_",
    "AUD_",
)


class TestPrefixRegistry:
    """§0.3 — the prefix registry is the allow-list of identifier families."""

    def test_core_registry_matches_the_spec(self) -> None:
        """Every §0.3 prefix is registered in ``app.core.constants``."""
        for prefix in SPEC_PREFIXES:
            assert prefix in ULID_PREFIXES

    def test_identifier_registry_adds_the_planning_and_version_extensions(self) -> None:
        """``ULID_PREFIXES`` is the core registry plus the documented extras."""
        assert ULID_PREFIXES <= IDENTIFIER_PREFIXES
        extras = IDENTIFIER_PREFIXES - ULID_PREFIXES
        assert {"PLAN_", "STEP_", "ITER_", "VER_"} <= extras

    def test_every_registered_prefix_produces_a_valid_identifier(self) -> None:
        """No registered prefix can yield an identifier rejected by ``is_valid``."""
        for prefix in sorted(IDENTIFIER_PREFIXES):
            identifier = ULID.new(prefix)
            assert identifier.startswith(prefix)
            assert ULID.is_valid(identifier) is True

    def test_prefixes_are_machine_parseable(self) -> None:
        """Prefixes are uppercase and underscore-terminated."""
        for prefix in IDENTIFIER_PREFIXES:
            assert prefix.isupper()
            assert prefix.endswith("_")


class TestIdentifierProperties:
    """§0.3 — the three observable properties of an INIS identifier."""

    def test_uniqueness(self) -> None:
        """1000 ids generated back to back are all distinct."""
        assert len({ULID.new("INF_") for _ in range(1000)}) == 1000

    def test_sortability(self) -> None:
        """Ordering by string is ordering by creation time."""
        first = ULID.new("AUD_")
        time.sleep(0.003)
        second = ULID.new("AUD_")
        time.sleep(0.003)
        third = ULID.new("AUD_")
        assert sorted([third, first, second]) == [first, second, third]

    def test_suffix_is_opaque_and_fixed_width(self) -> None:
        """The suffix exposes no business content and is always 26 characters."""
        identifier = ULID.new("SRC_")
        assert identifier.removeprefix("SRC_").isdigit() is False
        assert len(identifier) == len("SRC_") + 26

    @pytest.mark.parametrize("prefix", ["", "REQ", "REQ__", "req_"])
    def test_unregistered_prefixes_are_refused(self, prefix: str) -> None:
        """Only registry entries may mint identifiers."""
        with pytest.raises(ValueError):
            ULID.new(prefix)


class TestDataStages:
    """§12 — DATA_* identifiers carry an explicit lifecycle stage."""

    def test_lifecycle_order_is_raw_to_derived(self) -> None:
        """The four documented stages appear in lifecycle order."""
        assert DATA_STAGES == ("raw", "normalized", "enriched", "derived")

