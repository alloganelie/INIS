"""§12.1/§24.1 — la forme exacte d'``transformations[]`` dans le colis.

L'audit (C10) a trouvé pire qu'un lignage incomplet : le champ était **codé en
dur à ``[]``**, donc un client ne pouvait pas savoir qui avait produit quoi. Ce
fichier verrouille la structure de remplacement : chaque entrée est la
projection exacte de l'entité §12.1 (:class:`Transformation`), avec ses dix clés
et aucune autre, et le colis HTTP l'expose telle quelle.

Ce que ces tests refusent :

* une clé en plus ou en moins dans une entrée (un client typé casse) ;
* un identifiant qui n'est pas un ``TRF_{ULID}`` (§0.3) ;
* un horodatage qui n'est pas ISO 8601 UTC, ou un ``result`` hors contrat ;
* un ``parameters`` qui ne dit pas de quel stade §12 la ligne parle.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.v1.requests import pipeline_runner as runner_module
from app.api.v1.requests.pipeline_runner import PipelineRunner, pipeline_runner
from app.core.constants import DATA_STAGES
from app.domain.entities.transformation import TRANSFORMATION_RESULTS, Transformation
from app.domain.value_objects.ulid import ULID
from app.main import app

client = TestClient(app)

#: Les dix clés de §12.1, exactement celles de ``Transformation.to_dict()``.
SPEC_12_1_KEYS = frozenset(
    {
        "transformation_id",
        "input_ids",
        "output_ids",
        "operator",
        "tool",
        "tool_version",
        "parameters",
        "timestamp",
        "result",
        "justification",
    }
)

OBJECTIVE = "Compare la population des villes européennes"
DOCUMENT_ID = "DOC_01M3Q0000000000000000000AA"
DATASET_ID = "DATA_01M3Q0000000000000000000AA"
SOURCE_ID = "SRC_01M3Q0000000000000000000AA"
STORAGE_REF = "s3://inis-artifacts/documents/REQ_1/villes.csv"
UNIT_ONE = "INF_01M3Q0000000000000000000BB"
UNIT_TWO = "INF_01M3Q0000000000000000000BC"


@pytest.fixture
def web_doubles(monkeypatch: pytest.MonkeyPatch) -> dict[str, AsyncMock]:
    """Silence the §9/§10 providers: the run acquires nothing from the web."""
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


@pytest.fixture
def ingested(monkeypatch: pytest.MonkeyPatch) -> None:
    """Double the §9.1 material: this request ingested one CSV with two rows."""

    async def _load(request_id: str, **kwargs: Any) -> Any:
        from app.knowledge.ingestion.request_material import RequestMaterial, to_delivery_unit

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
                ((UNIT_ONE, "Paris"), (UNIT_TWO, "Berlin")), start=1
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
    """Run the pipeline once and return its §24.1 delivery."""
    request_id = ULID.new("REQ_")
    return await PipelineRunner().run(
        request_id,
        {"objective": OBJECTIVE, "request_type": "research"},
    )


class TestEveryTransformationIsARealSpec121Row:
    """§12.1 — dix clés, un ``TRF_{ULID}``, un horodatage ISO 8601 UTC."""

    async def test_the_colis_exposes_transformations(
        self, ingested: None, web_doubles: dict[str, AsyncMock], mock_llm: Any
    ) -> None:
        delivery = await _run()

        assert delivery["transformations"], (
            "un run qui a lu un fichier et écrit des unités ne peut pas livrer "
            "un lignage vide (C10)"
        )

    async def test_every_entry_has_exactly_the_ten_keys_of_the_spec(
        self, ingested: None, web_doubles: dict[str, AsyncMock], mock_llm: Any
    ) -> None:
        delivery = await _run()

        for entry in delivery["transformations"]:
            assert set(entry) == SPEC_12_1_KEYS, entry["transformation_id"]

    async def test_every_entry_is_validated_by_the_domain_entity(
        self, ingested: None, web_doubles: dict[str, AsyncMock], mock_llm: Any
    ) -> None:
        delivery = await _run()

        for entry in delivery["transformations"]:
            Transformation(**entry).validate()

    async def test_every_identifier_is_a_trf_ulid(
        self, ingested: None, web_doubles: dict[str, AsyncMock], mock_llm: Any
    ) -> None:
        delivery = await _run()
        identifiers = [entry["transformation_id"] for entry in delivery["transformations"]]

        assert len(set(identifiers)) == len(identifiers)
        for identifier in identifiers:
            assert identifier.startswith("TRF_")
            assert ULID.is_valid(identifier)

    async def test_every_timestamp_is_iso_8601_utc(
        self, ingested: None, web_doubles: dict[str, AsyncMock], mock_llm: Any
    ) -> None:
        delivery = await _run()

        for entry in delivery["transformations"]:
            timestamp = entry["timestamp"]
            assert timestamp.endswith("Z"), timestamp
            assert datetime.fromisoformat(timestamp).tzinfo is not None

    async def test_every_result_is_one_of_the_two_of_the_spec(
        self, ingested: None, web_doubles: dict[str, AsyncMock], mock_llm: Any
    ) -> None:
        delivery = await _run()

        for entry in delivery["transformations"]:
            assert entry["result"] in TRANSFORMATION_RESULTS

    async def test_every_entry_names_its_stage_and_its_objective(
        self, ingested: None, web_doubles: dict[str, AsyncMock], mock_llm: Any
    ) -> None:
        delivery = await _run()

        for entry in delivery["transformations"]:
            assert entry["parameters"]["stage"] in DATA_STAGES
            assert entry["parameters"]["objective"] == OBJECTIVE
            assert entry["tool"]
            assert entry["tool_version"]

    async def test_every_entry_declares_the_ids_it_really_used(
        self, ingested: None, web_doubles: dict[str, AsyncMock], mock_llm: Any
    ) -> None:
        delivery = await _run()
        known = {
            str(unit.get("information_id")) for unit in delivery["information_units"]
        } | {str(source.get("source_id")) for source in delivery["sources"]}

        for entry in delivery["transformations"]:
            assert entry["input_ids"], entry["tool"]
            for identifier in entry["output_ids"]:
                if identifier.startswith(("INF_", "SRC_")):
                    assert identifier in known, f"{entry['tool']} → {identifier}"


class TestTheHttpColisCarriesTheSameShape:
    """§24.1 — ce que ``GET /v1/requests/{id}`` rend est ce que le run a écrit."""

    def test_the_request_payload_exposes_spec121_transformations(self) -> None:
        created = client.post(
            "/v1/requests",
            json={"objective": OBJECTIVE, "request_type": "research"},
        )
        assert created.status_code == 201
        request_id = created.json()["request_id"]

        state = pipeline_runner.get_state(request_id)
        if state is None:  # the background run may still be starting
            pytest.skip("pipeline state not available yet in this environment")

        for entry in state["transformations"]:
            assert set(entry) == SPEC_12_1_KEYS
            Transformation(**entry).validate()
