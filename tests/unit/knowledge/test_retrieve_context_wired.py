"""§21/§17.1 — les unités retrouvées sont **reconstruites**, pas devinées.

``hybrid_search`` rend des identifiants et des scores ; §11 exige bien plus pour
livrer : contenu, provenance, localisation, stade. C'est le rôle de
``retrieve_context(ids)`` (``app/tools/knowledge/fragment_locator.py``), et c'est
ce que la mémoire appelle après avoir trouvé des candidats.

Deux propriétés sont verrouillées ici :

* les identifiants demandés sont **ceux de la recherche**, dans son ordre — pas
  une liste reconstruite ailleurs ;
* si la relecture échoue, l'échec est **nommé** (mode ``unavailable`` + une
  limitation) : une mémoire muette serait prise pour une mémoire vide (§25.2).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from app.core.errors import InfrastructureError
from app.knowledge import memory as memory_module
from app.knowledge.memory.hybrid_memory import HybridMemorySearch
from app.planning.memory_checker import MemoryRequirements
from app.storage.search.hybrid_search import HybridSearchOutcome

FIRST_ID = "INF_01M3Q0000000000000000000R1"
SECOND_ID = "INF_01M3Q0000000000000000000R2"
SOURCE_ID = "SRC_01M3Q0000000000000000000R0"

ROWS = (
    {"owner_id": FIRST_ID, "semantic_score": 1.0, "lexical_score": 0.0, "final_score": 0.6},
    {"owner_id": SECOND_ID, "semantic_score": 0.5, "lexical_score": 0.5, "final_score": 0.5},
)


class FakeSearch:
    """§16.2 double: two candidates, in a fixed order."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def search_outcome(
        self, query: str, query_vector: Any = None, limit: int = 10, **kwargs: Any
    ) -> HybridSearchOutcome:
        return HybridSearchOutcome(rows=ROWS, mode="hybrid", weights={"semantic": 0.6, "lexical": 0.4})


class FakeUnit:
    """Minimal ``InformationUnit``-shaped object."""

    def __init__(self, information_id: str) -> None:
        self.information_id = information_id
        self.source_id = SOURCE_ID
        self.content = {"text": f"texte de {information_id}"}
        self.provenance = {"source_id": SOURCE_ID, "method": "test"}
        self.data_stage = "enriched"
        self.created_at = datetime.now(UTC)

    def model_dump(self) -> dict[str, Any]:
        return {
            "information_id": self.information_id,
            "source_id": self.source_id,
            "content": self.content,
            "provenance": self.provenance,
            "data_stage": self.data_stage,
            "created_at": self.created_at.isoformat(),
        }


class FakeEngine:
    """Engine double: only the (optional) freshness read goes through it."""

    def connect(self) -> Any:
        raise RuntimeError("no database in this unit test")


@pytest.fixture
def search_module(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Replace the §16.2 search; the caller patches ``retrieve_context`` itself."""
    monkeypatch.setattr(memory_module.hybrid_memory, "HybridSearch", FakeSearch)
    return {"calls": []}


class TestTheIdsComeFromTheSearch:
    """§21 — ``retrieve_context`` relit exactement ce que la recherche a trouvé."""

    async def test_the_requested_ids_are_the_searched_ones(
        self, search_module: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _retrieve(ids: Any, **kwargs: Any) -> list[FakeUnit]:
            search_module["calls"].append(list(ids))
            return [FakeUnit(identifier) for identifier in ids]

        monkeypatch.setattr(memory_module.hybrid_memory, "retrieve_context", _retrieve)

        await HybridMemorySearch(engine=FakeEngine())("capitale ?", MemoryRequirements())

        assert search_module["calls"] == [[FIRST_ID, SECOND_ID]]

    async def test_the_candidates_come_from_the_retrieved_payload(
        self, search_module: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _retrieve(ids: Any, **kwargs: Any) -> list[FakeUnit]:
            return [FakeUnit(identifier) for identifier in ids]

        monkeypatch.setattr(memory_module.hybrid_memory, "retrieve_context", _retrieve)

        candidates = await HybridMemorySearch(engine=FakeEngine())(
            "capitale ?", MemoryRequirements()
        )

        assert [candidate.information_id for candidate in candidates] == [FIRST_ID, SECOND_ID]
        assert candidates[0].content == {"text": f"texte de {FIRST_ID}"}
        assert candidates[0].provenance["method"] == "test"
        assert candidates[0].data_stage == "enriched"

    async def test_the_retrieval_score_is_kept_as_provenance(
        self, search_module: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Pourquoi ce candidat est passé devant : c'est une donnée, pas un secret."""

        async def _retrieve(ids: Any, **kwargs: Any) -> list[FakeUnit]:
            return [FakeUnit(identifier) for identifier in ids]

        monkeypatch.setattr(memory_module.hybrid_memory, "retrieve_context", _retrieve)

        candidates = await HybridMemorySearch(engine=FakeEngine())(
            "capitale ?", MemoryRequirements()
        )

        assert candidates[0].provenance["retrieval_score"] == pytest.approx(0.6)


class TestAFailedRetrievalIsNamed:
    """§25.2 — un échec de relecture ne devient pas un « rien trouvé »."""

    async def test_an_unreadable_context_is_stated(
        self, search_module: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _retrieve(ids: Any, **kwargs: Any) -> list[FakeUnit]:
            raise InfrastructureError("retrieve_context failed: boom")

        monkeypatch.setattr(memory_module.hybrid_memory, "retrieve_context", _retrieve)
        search = HybridMemorySearch(engine=FakeEngine())

        candidates = await search("capitale ?", MemoryRequirements())

        assert candidates == []
        assert search.mode == "unavailable"
        assert any("retrieve_context" in line for line in search.limitations)
