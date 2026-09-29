"""§1/§24.1 — a persisted delivery is re-assemblable into an InformationPackage.

The pipeline builds the delivery in memory and persists its material as
``information_units`` and ``evidence`` rows. This test proves the reverse
direction works on the real migrated schema: what was persisted can be read back
and assembled into a valid §1 package, with the provenance §0.2 requires.

Runs against the pgvector container (skip when Docker is unavailable).
"""

from __future__ import annotations

from typing import Any, AsyncIterator

import pytest

from app.core.errors import ValidationError
from app.domain.value_objects.ulid import ULID
from app.storage.database.engine import create_engine
from app.storage.repositories.evidence_repository import EvidenceRepository
from app.storage.repositories.information_package_repository import (
    InformationPackageRepository,
)
from app.storage.repositories.information_unit_repository import InformationUnitRepository
from app.storage.repositories.source_repository import SourceRepository
from tests.factories import make_evidence, make_information_unit, make_source_create_payload

pytestmark = pytest.mark.asyncio

#: The §24.1 keys a delivered package must expose.
PACKAGE_KEYS = {
    "package_id",
    "request_id",
    "units",
    "evidence",
    "confidence",
    "provenance",
    "data_stage",
    "created_at",
}


@pytest.fixture
async def engine(db_url: str) -> AsyncIterator[Any]:
    """Yield an engine bound to the migrated PostgreSQL test database."""
    created = create_engine(db_url)
    try:
        yield created
    finally:
        await created.dispose()


async def _seed_delivery(engine: Any) -> dict[str, str]:
    """Persist one source, one unit and one evidence record; return their ids."""
    source = await SourceRepository.create(
        engine, make_source_create_payload(name="Wikipedia — Paris")
    )
    source_id = source["source_id"]

    unit = make_information_unit(source_id=source_id)
    stored_unit = await InformationUnitRepository.create(engine, unit)

    evidence = make_evidence(
        information_id=stored_unit["information_id"], source_id=source_id
    )
    stored_evidence = await EvidenceRepository.create(engine, evidence)

    return {
        "source_id": source_id,
        "information_id": stored_unit["information_id"],
        "evidence_id": stored_evidence["evidence_id"],
    }


class TestPackageAssembly:
    """§24.1 — the persisted rows are the package the client must be able to read."""

    async def test_persisted_material_is_reassembled(self, engine: Any) -> None:
        """Units and evidence survive the round-trip through PostgreSQL."""
        seeded = await _seed_delivery(engine)
        request_id = ULID.new("REQ_")

        package = await InformationPackageRepository.assemble(
            engine,
            request_id=request_id,
            information_ids=[seeded["information_id"]],
            evidence_ids=[seeded["evidence_id"]],
        )

        assert set(package) == PACKAGE_KEYS
        assert package["request_id"] == request_id
        assert [unit["information_id"] for unit in package["units"]] == [
            seeded["information_id"]
        ]
        assert [item["evidence_id"] for item in package["evidence"]] == [
            seeded["evidence_id"]
        ]

    async def test_package_provenance_names_the_source(self, engine: Any) -> None:
        """§0.2 — the reassembled package can still explain where it came from."""
        seeded = await _seed_delivery(engine)

        package = await InformationPackageRepository.assemble(
            engine,
            request_id=ULID.new("REQ_"),
            information_ids=[seeded["information_id"]],
        )

        assert package["provenance"]["source_ids"] == [seeded["source_id"]]
        assert package["provenance"]["information_ids"] == [seeded["information_id"]]
        assert package["units"][0]["provenance"], "the unit lost its provenance"

    async def test_confidence_block_is_passed_through(self, engine: Any) -> None:
        """§15 — the package carries the confidence computed for the run."""
        seeded = await _seed_delivery(engine)
        confidence = {"score": 0.42, "dimensions": {"source_reliability": 0.4}}

        package = await InformationPackageRepository.assemble(
            engine,
            request_id=ULID.new("REQ_"),
            information_ids=[seeded["information_id"]],
            confidence=confidence,
        )

        assert package["confidence"] == confidence

    async def test_unknown_information_id_yields_no_package(self, engine: Any) -> None:
        """§1 — a package with no provenance is refused, never delivered empty."""
        with pytest.raises(ValidationError):
            await InformationPackageRepository.assemble(
                engine,
                request_id=ULID.new("REQ_"),
                information_ids=[ULID.new("INF_")],
            )

    async def test_partial_ids_only_include_what_was_persisted(self, engine: Any) -> None:
        """An unknown id is skipped rather than fabricating a phantom unit."""
        seeded = await _seed_delivery(engine)

        package = await InformationPackageRepository.assemble(
            engine,
            request_id=ULID.new("REQ_"),
            information_ids=[seeded["information_id"], ULID.new("INF_")],
            evidence_ids=[ULID.new("EVID_")],
        )

        assert len(package["units"]) == 1
        assert package["evidence"] == []

