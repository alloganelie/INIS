"""L4/§17.1 — la mémoire est consultée en tête de plan, avec la recherche injectée.

Avant ce lot, ``app/planning/memory_checker.py`` existait, était testé… et
n'était appelé par **aucun run** (C13) : chaque requête ré-acquérait ce qu'INIS
savait déjà. Ce fichier verrouille le câblage :

* l'étape ``memory_lookup`` ouvre le plan, **avant** toute acquisition ;
* c'est bien ``memory_checker.memory_lookup`` qui décide, avec la recherche
  §16.2 **injectée** (le module de décision reste sans dépendance de stockage) ;
* une unité retrouvée entre dans le colis **avec son identifiant d'origine** —
  rien n'est recréé, donc rien n'est dupliqué en base (§17.1) ;
* « mémoire utilisée » se lit dans la provenance — et son absence aussi.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.api.v1.requests import pipeline_runner as runner_module
from app.api.v1.requests.pipeline_runner import PipelineRunner
from app.domain.entities.memory_result import MemoryCandidate
from app.domain.value_objects.ulid import ULID

OBJECTIVE = "Quelle est la capitale de la France ?"
SOURCE_ID = "SRC_01M3Q0000000000000000000M0"
UNIT_ID = "INF_01M3Q0000000000000000000M1"


def _unit_payload() -> dict[str, Any]:
    """Return the §11 payload of a unit already stored by a previous run."""
    return {
        "information_id": UNIT_ID,
        "type": "text",
        "content": {"text": "Paris est la capitale de la France."},
        "raw_reference": {"url": "https://fr.wikipedia.org/wiki/Paris"},
        "source_id": SOURCE_ID,
        "document_id": None,
        "dataset_id": None,
        "location": {},
        "context": {"request_id": "REQ_previous_run"},
        "language": "fr",
        "unit": None,
        "time": {},
        "classification": {},
        "quality": {},
        "confidence": {"not_a_probability": True},
        "provenance": {"source_id": SOURCE_ID, "url": "https://fr.wikipedia.org/wiki/Paris"},
        "data_stage": "enriched",
        "epistemic_status": "factual",
        "versions": [UNIT_ID],
        "created_at": datetime.now(UTC).isoformat(),
    }


class FakeMemorySearch:
    """Search double: it records the question and returns what the test decided."""

    def __init__(
        self,
        *,
        sufficient: bool = True,
        mode: str = "hybrid",
        limitations: tuple[str, ...] = (),
    ) -> None:
        self.mode = mode
        self.limitations = list(limitations)
        self.calls: list[tuple[str, Any]] = []
        self.units: dict[str, dict[str, Any]] = (
            {UNIT_ID: _unit_payload()} if sufficient else {}
        )
        self._sufficient = sufficient

    async def __call__(self, question: str, requirements: Any) -> list[MemoryCandidate]:
        self.calls.append((question, requirements))
        if not self._sufficient:
            return []
        return [
            MemoryCandidate(
                information_id=UNIT_ID,
                content={"text": "Paris est la capitale de la France."},
                source_id=SOURCE_ID,
                provenance={"source_id": SOURCE_ID},
                data_stage="enriched",
                source_freshness=datetime.now(UTC),
            )
        ]


@pytest.fixture
def web_doubles(monkeypatch: pytest.MonkeyPatch) -> dict[str, AsyncMock]:
    """Silence the §9/§10 providers: the answer comes from memory, not the web."""
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
def captured_steps(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Capture the step results handed to persistence, without a database."""
    captured: list[dict[str, Any]] = []

    async def _fake_persist(**kwargs: Any) -> tuple[bool, list[str], dict[str, Any]]:
        captured.extend(kwargs.get("step_results") or [])
        return False, [], {
            "audit_event_id": ULID.new("AUD_"),
            "timestamp": "2026-01-01T00:00:00Z",
        }

    monkeypatch.setattr(
        "app.api.v1.requests.pipeline_runner.persist_pipeline_delivery", _fake_persist
    )
    return captured


def _install_search(monkeypatch: pytest.MonkeyPatch, fake: FakeMemorySearch) -> None:
    """Inject *fake* wherever the runner builds its §17.1 search."""
    monkeypatch.setattr(runner_module, "HybridMemorySearch", lambda **kwargs: fake)


async def _run() -> dict[str, Any]:
    """Run one request with the memory step wired."""
    return await PipelineRunner().run(
        ULID.new("REQ_"), {"objective": OBJECTIVE, "request_type": "research"}
    )


class TestTheStepOpensThePlan:
    """§8.4/§17.1 — la question « le sais-je déjà ? » se pose avant d'acquérir."""

    async def test_the_first_step_is_the_memory_lookup(
        self,
        web_doubles: dict[str, AsyncMock],
        captured_steps: list[dict[str, Any]],
        mock_llm: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _install_search(monkeypatch, FakeMemorySearch())

        await _run()

        assert captured_steps, "le run a exécuté au moins une étape"
        assert captured_steps[0]["action"] == "memory_lookup"
        assert captured_steps[0]["tools_required"][0] == "hybrid_search"

    async def test_the_step_is_executed_not_degraded(
        self,
        web_doubles: dict[str, AsyncMock],
        captured_steps: list[dict[str, Any]],
        mock_llm: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _install_search(monkeypatch, FakeMemorySearch())

        await _run()

        assert captured_steps[0]["status"] == "done"

    async def test_the_decision_module_receives_the_question(
        self,
        web_doubles: dict[str, AsyncMock],
        captured_steps: list[dict[str, Any]],
        mock_llm: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """C'est ``memory_checker.memory_lookup`` qui décide, pas le runner."""
        fake = FakeMemorySearch()
        _install_search(monkeypatch, fake)

        await _run()

        assert fake.calls, "memory_checker.memory_lookup n'a pas été appelé"
        question, requirements = fake.calls[0]
        assert question == OBJECTIVE
        assert requirements.freshness_threshold_hours > 0


class TestAReusedUnitJoinsTheColis:
    """§17.1 — l'unité retrouvée est livrée telle quelle, avec son identifiant."""

    async def test_the_unit_is_delivered_with_its_original_identifier(
        self,
        web_doubles: dict[str, AsyncMock],
        captured_steps: list[dict[str, Any]],
        mock_llm: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _install_search(monkeypatch, FakeMemorySearch())

        delivery = await _run()
        ids = [unit.get("information_id") for unit in delivery["information_units"]]

        assert UNIT_ID in ids, "l'unité de mémoire doit entrer dans le colis"
        assert ids.count(UNIT_ID) == 1, "elle ne doit pas être dupliquée"

    async def test_its_context_says_it_comes_from_memory(
        self,
        web_doubles: dict[str, AsyncMock],
        captured_steps: list[dict[str, Any]],
        mock_llm: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _install_search(monkeypatch, FakeMemorySearch())

        delivery = await _run()
        unit = next(
            item for item in delivery["information_units"] if item["information_id"] == UNIT_ID
        )

        assert unit["context"]["memory"]["reused"] is True
        assert unit["context"]["memory"]["mode"] == "hybrid"

    async def test_the_delivery_reports_what_the_memory_gave(
        self,
        web_doubles: dict[str, AsyncMock],
        captured_steps: list[dict[str, Any]],
        mock_llm: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _install_search(monkeypatch, FakeMemorySearch())

        delivery = await _run()
        memory = delivery["provenance"]["memory"]

        assert memory["sufficient"] is True
        assert memory["reused_units"] == 1
        assert memory["information_ids"] == [UNIT_ID]


class TestWhenNothingCanBeReusedItIsStated:
    """§0.2/§37 — « rien en mémoire » est un résultat, et il se lit."""

    async def test_an_empty_memory_is_a_normal_outcome(
        self,
        web_doubles: dict[str, AsyncMock],
        captured_steps: list[dict[str, Any]],
        mock_llm: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _install_search(monkeypatch, FakeMemorySearch(sufficient=False))

        delivery = await _run()

        assert captured_steps[0]["status"] == "done", (
            "ne rien trouver n'est pas une dégradation"
        )
        assert "rien de réutilisable" in captured_steps[0]["output"]
        assert delivery["provenance"]["memory"]["reused_units"] == 0
        assert any(
            "Mémoire §17.1 consultée sans réutilisation" in line
            for line in delivery["limitations"]
        )

    async def test_an_unusable_memory_degrades_the_step_and_says_why(
        self,
        web_doubles: dict[str, AsyncMock],
        captured_steps: list[dict[str, Any]],
        mock_llm: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _install_search(
            monkeypatch,
            FakeMemorySearch(
                sufficient=False,
                mode="unavailable",
                limitations=("Recherche §16.2 indisponible (test) : rien n'a été consulté.",),
            ),
        )

        delivery = await _run()

        assert captured_steps[0]["status"] == "degraded"
        assert captured_steps[0]["error"]
        assert any(
            "Mémoire §17.1 non consultable" in line for line in delivery["limitations"]
        )

