"""§12.1 — seule une transformation **réellement exécutée** entre dans le colis.

L'audit (C10/C11) a trouvé deux mensonges opposés dans le même champ : une liste
``[]`` livrée quoi qu'il arrive, et une ligne générique ``PipelineRunner`` écrite
pour *chaque* run, quel que soit ce qu'il avait fait. Ce fichier verrouille la
borne dans l'autre sens : tout ce qui est livré s'est produit, et tout ce qui
s'est produit d'important est livré.

Ce que ces tests refusent :

* une ligne dont l'``operator`` est le fourre-tout ``PipelineRunner`` (l'ancien
  défaut) ;
* une ligne dont les ``output_ids`` ne sont **nulle part** dans le colis : un
  output qui n'existe pas est un output inventé ;
* une liste non vide pour un run qui n'a rien produit, et une ligne pour un
  stade qui n'a pas tourné ;
* deux lignes pour le même producteur au même stade (le doublon venu de la
  double écriture ``persist_transformations``).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.api.v1.requests import pipeline_runner as runner_module
from app.api.v1.requests.pipeline_runner import PipelineRunner
from app.core.constants import DATA_STAGES
from app.domain.entities.transformation import Transformation
from app.domain.value_objects.ulid import ULID
from app.knowledge.ingestion.request_material import RequestMaterial, to_delivery_unit

OBJECTIVE = "Analyse la population des villes du fichier fourni"
DOCUMENT_ID = "DOC_01M3Q0000000000000000000AA"
DATASET_ID = "DATA_01M3Q0000000000000000000AA"
SOURCE_ID = "SRC_01M3Q0000000000000000000AA"
STORAGE_REF = "s3://inis-artifacts/documents/REQ_1/villes.csv"
UNIT_ID = "INF_01M3Q0000000000000000000BB"
UNIT_ALT = "INF_01M3Q0000000000000000000BC"


@pytest.fixture
def web_doubles(monkeypatch: pytest.MonkeyPatch) -> dict[str, AsyncMock]:
    """Silence the §9/§10 providers: any web call is observable, and returns nothing."""
    search = AsyncMock(return_value=[])
    extract = AsyncMock(return_value={})
    monkeypatch.setattr(
        "app.connectors.web.provider_router.ProviderRouter.search", search
    )
    monkeypatch.setattr(
        "app.connectors.web.extractors.wikipedia_extractor.WikipediaExtractor.extract",
        extract,
    )
    return {"search": search, "extract": extract}


def _ingest_material(monkeypatch: pytest.MonkeyPatch) -> None:
    """Double the §9.1 material read back for the request: one CSV, two rows."""

    async def _load(request_id: str, **kwargs: Any) -> RequestMaterial:
        document = {
            "document_id": DOCUMENT_ID,
            "source_id": SOURCE_ID,
            "request_id": request_id,
            "file_name": "villes.csv",
            "mime_type": "text/csv",
            "storage_ref": STORAGE_REF,
        }
        dataset = {
            "dataset_id": DATASET_ID,
            "request_id": request_id,
            "name": "villes.csv",
            "row_count": 2,
            "storage_ref": STORAGE_REF,
            "dataset_schema": {"city": "string"},
        }
        units = [
            to_delivery_unit(
                {
                    "information_id": unit_id,
                    "type": "record",
                    "content": {"values": {"city": city}},
                    "raw_reference": {"document_id": DOCUMENT_ID},
                    "source_id": SOURCE_ID,
                    "document_id": DOCUMENT_ID,
                    "dataset_id": DATASET_ID,
                    "location": {"kind": "row", "row": row},
                    "context": {"origin": "uploaded_document"},
                    "provenance": {"extracted_from": STORAGE_REF, "method": "read_csv"},
                    "data_stage": "normalized",
                    "epistemic_status": "factual",
                },
                request_id,
            )
            for row, (unit_id, city) in enumerate(
                ((UNIT_ID, "Paris"), (UNIT_ALT, "Berlin")), start=1
            )
        ]
        return RequestMaterial(
            request_id=request_id,
            documents=[document],
            datasets=[dataset],
            units=units,
        )

    monkeypatch.setattr(runner_module, "load_request_material", _load)


async def _run() -> dict[str, Any]:
    """Run one ``data`` request over the ingested CSV and return the delivery."""
    return await PipelineRunner().run(
        ULID.new("REQ_"),
        {"objective": OBJECTIVE, "request_type": "data"},
    )


def _rows(delivery: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the delivered §12.1 transformations."""
    return list(delivery["transformations"])


def _known_ids(delivery: dict[str, Any]) -> set[str]:
    """Return every identifier the colis itself holds.

    A ``raw``/``normalized`` row of the ingestion produces ``DOC_``/``DATA_``
    ids that live in the material rather than in ``sources``: they are collected
    from the units (``document_id``/``dataset_id``) so the check stays exact.
    """
    known = {str(source.get("source_id")) for source in delivery["sources"]}
    known |= {str(dataset.get("dataset_id")) for dataset in delivery["datasets"]}
    for unit in delivery["information_units"]:
        for key in ("information_id", "document_id", "dataset_id"):
            if unit.get(key):
                known.add(str(unit[key]))
    known |= {str(item.get("evidence_id")) for item in delivery["evidence"]}
    known |= {str(item.get("artifact_id")) for item in delivery["artifacts"]}
    known.discard("None")
    return known


class TestNothingIsInvented:
    """§0.2 — une ligne qui ne correspond à rien est pire qu'une ligne absente."""

    async def test_no_generic_operator_is_left(
        self, monkeypatch: pytest.MonkeyPatch, web_doubles: dict[str, AsyncMock], mock_llm: Any
    ) -> None:
        """C11 — la ligne fourre-tout ``PipelineRunner`` a disparu."""
        _ingest_material(monkeypatch)

        operators = {row["operator"] for row in _rows(await _run())}

        assert "PipelineRunner" not in operators
        assert operators, "un run qui a lu un fichier et écrit des unités produit des lignes"

    async def test_every_output_id_exists_in_the_colis(
        self, monkeypatch: pytest.MonkeyPatch, web_doubles: dict[str, AsyncMock], mock_llm: Any
    ) -> None:
        _ingest_material(monkeypatch)
        delivery = await _run()
        known = _known_ids(delivery)

        for row in _rows(delivery):
            assert row["output_ids"], row["tool"]
            unknown = [
                identifier
                for identifier in row["output_ids"]
                if identifier.startswith(("INF_", "SRC_", "DOC_", "DATA_", "EVID_", "ART_"))
                and identifier not in known
            ]
            assert not unknown, f"{row['tool']} déclare {unknown}, absent du colis"

    async def test_every_row_is_a_validated_success_with_an_output(
        self, monkeypatch: pytest.MonkeyPatch, web_doubles: dict[str, AsyncMock], mock_llm: Any
    ) -> None:
        _ingest_material(monkeypatch)

        for row in _rows(await _run()):
            assert row["result"] == "success"
            Transformation(**row).validate()

    async def test_one_row_per_producer_and_per_stage(
        self, monkeypatch: pytest.MonkeyPatch, web_doubles: dict[str, AsyncMock], mock_llm: Any
    ) -> None:
        """Deux écritures du même producteur au même stade seraient un doublon."""
        _ingest_material(monkeypatch)
        rows = _rows(await _run())

        pairs = [(row["parameters"]["stage"], row["operator"]) for row in rows]
        assert len(set(pairs)) == len(pairs)

    async def test_no_row_claims_a_stage_that_did_not_run(
        self, monkeypatch: pytest.MonkeyPatch, web_doubles: dict[str, AsyncMock], mock_llm: Any
    ) -> None:
        """Aucun fichier lu ⇒ aucun étage d'ingestion, aucune synchèse sans preuve."""
        delivery = await _run()
        stages = [row["parameters"]["stage"] for row in _rows(delivery)]

        assert set(stages) <= set(DATA_STAGES)
        for row in _rows(delivery):
            assert row["parameters"].get("origin") != "uploaded_document"

    async def test_a_run_without_material_records_only_what_it_produced(
        self, web_doubles: dict[str, AsyncMock], mock_llm: Any
    ) -> None:
        """§0.2 — pas de fichier, pas de source web : les seuls producteurs réels.

        Le run reste réellement producteur de deux choses : la source interne
        qui le porte (``ProviderRouter``) et la synthèse qu'il a écrite
        (``ModelRouter``). Aucun étage d'acquisition ni d'extraction ne doit
        apparaître, puisqu'aucun n'a tourné.
        """
        delivery = await _run()
        rows = _rows(delivery)
        known = _known_ids(delivery)

        operators = {row["operator"] for row in rows}
        assert operators == {"ProviderRouter", "ModelRouter"}
        for row in rows:
            assert set(row["output_ids"]) <= known
        assert delivery["information_units"], "l'unité de synthèse du run existe toujours"



class TestWhatReallyRanIsWhatIsDelivered:
    """§12.1 — le lignage nomme les producteurs qui ont travaillé."""

    async def test_the_ingestion_has_its_own_reader_and_its_own_units(
        self, monkeypatch: pytest.MonkeyPatch, web_doubles: dict[str, AsyncMock], mock_llm: Any
    ) -> None:
        _ingest_material(monkeypatch)
        rows = _rows(await _run())

        raw = next(row for row in rows if row["parameters"].get("origin") == "uploaded_document")
        normalized = next(
            row
            for row in rows
            if row["tool"] == "DocumentIngestor.ingest"
        )

        assert raw["operator"] == "DocumentIngestor"
        assert raw["output_ids"] == [DOCUMENT_ID]
        assert normalized["output_ids"] == [UNIT_ID, UNIT_ALT]

    async def test_the_synthesis_row_is_credited_to_the_model_that_answered(
        self, monkeypatch: pytest.MonkeyPatch, web_doubles: dict[str, AsyncMock], mock_llm: Any
    ) -> None:
        _ingest_material(monkeypatch)
        rows = _rows(await _run())

        synthesis = [row for row in rows if row["operator"] == "ModelRouter"]

        assert synthesis, "le run a synthétisé une livraison"
        for row in synthesis:
            assert row["tool"] == "synthesis"
            assert row["parameters"]["stage"] == "enriched"

