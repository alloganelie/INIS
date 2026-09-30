"""§9.1/§11 — la matière déjà ingérée d'une requête est relue, jamais réinventée.

Le pipeline doit pouvoir répondre à « qu'a ingéré cette requête ? » sans relire le
fichier : les documents, leur `Dataset` et les unités §11 sont en base depuis le
téléversement. Ce module ne relit que ça — une base illisible produit une matière
vide **et** une limitation nommant la cause (§25.2), jamais un colis muet.
"""

from __future__ import annotations

import pytest

from app.knowledge.ingestion import request_material as module
from app.knowledge.ingestion.request_material import (
    RequestMaterial,
    load_request_material,
    to_delivery_unit,
)

REQUEST_ID = "REQ_01M3Q0000000000000000000AA"
DOCUMENT_ID = "DOC_01M3Q0000000000000000000AA"
DATASET_ID = "DATA_01M3Q0000000000000000000AA"
UNIT_ID = "INF_01M3Q0000000000000000000AA"

DOCUMENT = {
    "document_id": DOCUMENT_ID,
    "source_id": "SRC_01M3Q0000000000000000000AA",
    "request_id": REQUEST_ID,
    "file_name": "villes.csv",
    "mime_type": "text/csv",
    "storage_ref": "s3://inis-artifacts/documents/REQ_1/abc.csv",
}
DATASET = {"dataset_id": DATASET_ID, "request_id": REQUEST_ID, "row_count": 2}
UNIT = {
    "information_id": UNIT_ID,
    "type": "record",
    "content": {"values": {"city": "Paris"}, "text": "city=Paris"},
    "source_id": DOCUMENT["source_id"],
    "document_id": DOCUMENT_ID,
    "dataset_id": DATASET_ID,
    "location": {"kind": "row", "row": 1},
    "context": {"origin": "uploaded_document"},
    "data_stage": "raw",
}


class _FakeEngine:
    """An engine marker: the repositories are doubled, nothing connects."""


@pytest.fixture
def repositories(monkeypatch: pytest.MonkeyPatch) -> dict[str, list]:
    """Replace the three repositories the loader reads."""
    calls: dict[str, list] = {"documents": [], "datasets": [], "units": []}

    async def _documents(engine, request_id, *args, **kwargs):
        calls["documents"].append((engine, request_id))
        return [dict(DOCUMENT)]

    async def _datasets(engine, request_id, *args, **kwargs):
        calls["datasets"].append((engine, request_id))
        return [dict(DATASET)]

    async def _units(engine, request_id, *args, **kwargs):
        calls["units"].append((engine, request_id))
        return [dict(UNIT)]

    monkeypatch.setattr(module.DocumentRepository, "list_for_request", _documents)
    monkeypatch.setattr(module.DatasetRepository, "list_for_request", _datasets)
    monkeypatch.setattr(module.InformationUnitRepository, "list_for_request", _units)
    return calls


class TestLoadRequestMaterial:
    """La lecture est en lecture seule et ne lève jamais."""

    async def test_the_documents_datasets_and_units_are_read_back(
        self, repositories: dict[str, list]
    ) -> None:
        material = await load_request_material(REQUEST_ID, engine=_FakeEngine())

        assert [d["document_id"] for d in material.documents] == [DOCUMENT_ID]
        assert [dataset["dataset_id"] for dataset in material.datasets] == [DATASET_ID]
        assert [unit["information_id"] for unit in material.units] == [UNIT_ID]
        assert material.limitations == []
        assert material.has_documents is True
        assert material.has_material is True

    async def test_the_readers_come_from_the_detected_mime_types(
        self, repositories: dict[str, list]
    ) -> None:
        material = await load_request_material(REQUEST_ID, engine=_FakeEngine())

        assert material.readers == ["read_csv"]

    async def test_a_request_without_ingestion_is_empty_not_stated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _none(engine, request_id, *args, **kwargs):
            return []

        monkeypatch.setattr(module.DocumentRepository, "list_for_request", _none)
        monkeypatch.setattr(module.DatasetRepository, "list_for_request", _none)
        monkeypatch.setattr(module.InformationUnitRepository, "list_for_request", _none)

        material = await load_request_material(REQUEST_ID, engine=_FakeEngine())

        assert material.has_documents is False
        assert material.has_material is False
        assert material.limitations == []

    async def test_no_database_is_a_named_limitation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """§25.2 — pas de base, pas de matière, et la raison est dite."""
        monkeypatch.delenv("INIS_DATABASE_URL", raising=False)

        material = await load_request_material(REQUEST_ID)

        assert material.has_material is False
        assert any("INIS_DATABASE_URL" in text for text in material.limitations)

    async def test_an_unreadable_document_table_names_its_cause(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _boom(engine, request_id, *args, **kwargs):
            raise RuntimeError("relation documents does not exist")

        monkeypatch.setattr(module.DocumentRepository, "list_for_request", _boom)

        material = await load_request_material(REQUEST_ID, engine=_FakeEngine())

        assert material.has_material is False
        assert any("illisibles" in text for text in material.limitations)
        assert any("RuntimeError" in text for text in material.limitations)

    async def test_unreadable_units_keep_the_documents(
        self, repositories: dict[str, list], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _boom(engine, request_id, *args, **kwargs):
            raise RuntimeError("join impossible")

        monkeypatch.setattr(module.InformationUnitRepository, "list_for_request", _boom)

        material = await load_request_material(REQUEST_ID, engine=_FakeEngine())

        assert material.has_documents is True
        assert material.units == []
        assert any("Unités §11" in text for text in material.limitations)

    async def test_the_unit_bound_is_stated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """§41.13 — une borne atteinte n'est pas un silence."""

        async def _documents(engine, request_id, *args, **kwargs):
            return [dict(DOCUMENT)]

        async def _many(engine, request_id, *args, **kwargs):
            return [dict(UNIT) for _ in range(5)]

        monkeypatch.setattr(module.DocumentRepository, "list_for_request", _documents)
        monkeypatch.setattr(module.InformationUnitRepository, "list_for_request", _many)

        material = await load_request_material(
            REQUEST_ID, engine=_FakeEngine(), max_units=5
        )

        assert len(material.units) == 5
        assert any("borne §41.13" in text for text in material.limitations)

    async def test_the_summary_counts_only(self, repositories: dict[str, list]) -> None:
        material = await load_request_material(REQUEST_ID, engine=_FakeEngine())

        summary = material.summary()

        assert "1 document" in summary
        assert "1 dataset" in summary
        assert "1 unité" in summary
        assert "Paris" not in summary, "un compte rendu d'étape ne recopie pas la donnée"


class TestToDeliveryUnit:
    """Les champs absents de la table sont complétés à vide, jamais inventés."""

    def test_the_missing_spec11_fields_are_completed_empty(self) -> None:
        delivered = to_delivery_unit(UNIT, REQUEST_ID)

        assert delivered["unit"] is None
        assert delivered["time"] == {}
        assert delivered["classification"] == {}
        assert delivered["quality"] == {}
        assert delivered["confidence"] == {"not_a_probability": True}

    def test_the_stored_values_are_never_overwritten(self) -> None:
        stored = {**UNIT, "quality": {"quality_score": 0.9}}

        delivered = to_delivery_unit(stored, REQUEST_ID)

        assert delivered["quality"] == {"quality_score": 0.9}
        assert delivered["location"] == {"kind": "row", "row": 1}
        assert delivered["dataset_id"] == DATASET_ID

    def test_the_request_is_named_in_the_context(self) -> None:
        delivered = to_delivery_unit(UNIT, REQUEST_ID)

        assert delivered["context"]["request_id"] == REQUEST_ID
        assert delivered["context"]["origin"] == "uploaded_document"

    def test_the_source_mapping_is_not_mutated(self) -> None:
        to_delivery_unit(UNIT, REQUEST_ID)

        assert "request_id" not in UNIT["context"]


class TestRequestMaterialValueObject:
    """L'objet ne prétend jamais avoir de la matière qu'il n'a pas."""

    def test_an_empty_material_is_not_a_material(self) -> None:
        material = RequestMaterial(request_id=REQUEST_ID)

        assert material.has_documents is False
        assert material.has_material is False
        assert material.readers == []
        assert material.summary().endswith("(§9.1).")
