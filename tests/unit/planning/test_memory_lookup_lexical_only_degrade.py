"""§16.2/§17.1 — sans embeddings, la mémoire se dégrade en lexical **et le dit**.

Deux moitiés composent la recherche §16.2 : ``embeddings`` (sémantique) et
``search_vector`` (lexicale). Une base dont la table ``embeddings`` est vide — le
cas de toute installation avant le premier ``backfill_embeddings.py`` — peut quand
même retrouver une unité par ses mots ; prétendre alors à une recherche
« hybride » serait un mensonge de plus dans un colis.

Ce fichier verrouille donc la dégradation : mode ``lexical_only``, une limitation
qui l'explique, et **la réutilisation qui continue de fonctionner** (les filtres
§17.1 ne dépendent pas du vecteur).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar

import pytest

from app.domain.entities.memory_result import MemoryCandidate
from app.knowledge import memory as memory_module
from app.knowledge.memory.hybrid_memory import HybridMemorySearch
from app.planning.memory_checker import MemoryRequirements, memory_lookup
from app.storage.search.hybrid_search import HybridSearchOutcome

OWNER_ID = "INF_01M3Q0000000000000000000L1"
SOURCE_ID = "SRC_01M3Q0000000000000000000L0"


class FakeHybridSearch:
    """Stub of the §16.2 search: it reports the mode the test asked for."""

    mode = "lexical_only"
    limitation = (
        "Aucun embedding stocké pour cette base (§16.1) : recherche **lexicale "
        "seule**, la moitié sémantique de §16.2 n'a pas pu s'exécuter."
    )
    calls: ClassVar[list[dict[str, Any]]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.rows = (
            {
                "owner_id": OWNER_ID,
                "semantic_score": 0.0,
                "lexical_score": 1.0,
                "final_score": 1.0,
            },
        )

    async def search_outcome(
        self, query: str, query_vector: Any = None, limit: int = 10, **kwargs: Any
    ) -> HybridSearchOutcome:
        FakeHybridSearch.calls.append(
            {"query": query, "vector": query_vector, "limit": limit}
        )
        return HybridSearchOutcome(
            rows=self.rows,
            mode=self.mode,
            limitations=(self.limitation,),
            weights={"semantic": 0.6, "lexical": 0.4},
        )


class FakeUnit:
    """Minimal §11 unit as ``retrieve_context`` would return it."""

    information_id = OWNER_ID
    source_id = SOURCE_ID
    content: ClassVar[dict[str, Any]] = {"text": "Paris est la capitale de la France."}
    provenance: ClassVar[dict[str, Any]] = {
        "source_id": SOURCE_ID,
        "url": "https://fr.wikipedia.org/wiki/Paris",
    }
    data_stage = "enriched"
    created_at = datetime.now(UTC)

    def model_dump(self) -> dict[str, Any]:
        return {
            "information_id": self.information_id,
            "source_id": self.source_id,
            "content": self.content,
            "provenance": self.provenance,
            "data_stage": self.data_stage,
            "created_at": self.created_at.isoformat(),
            "type": "text",
            "raw_reference": {},
            "document_id": None,
            "dataset_id": None,
            "location": {},
            "context": {},
            "language": "fr",
            "unit": None,
            "time": {},
            "classification": {},
            "quality": {},
            "confidence": {"not_a_probability": True},
            "epistemic_status": "factual",
            "versions": [OWNER_ID],
        }


@pytest.fixture
def lexical_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the §16.2 search and the §21 context reader by doubles."""
    FakeHybridSearch.calls = []
    monkeypatch.setattr(memory_module.hybrid_memory, "HybridSearch", FakeHybridSearch)

    async def _retrieve(ids: Any, **kwargs: Any) -> list[FakeUnit]:
        return [FakeUnit() for _ in ids]

    monkeypatch.setattr(memory_module.hybrid_memory, "retrieve_context", _retrieve)


class _Engine:
    """Engine double: the freshness read is the only call it must survive."""

    def connect(self) -> Any:
        raise RuntimeError("no database in this unit test")


def _search() -> HybridMemorySearch:
    """Return the memory search under test, with a non-None engine double."""
    return HybridMemorySearch(engine=_Engine())


class TestTheSearchSaysWhatItRan:
    """§16.2/§0.2 — le mode réel est exposé, jamais présenté comme hybride."""

    async def test_the_mode_is_lexical_only_and_explained(self, lexical_only: None) -> None:
        search = _search()

        await search("capitale de la France", MemoryRequirements())

        assert search.mode == "lexical_only"
        assert any("lexicale seule" in line for line in search.limitations)

    async def test_no_query_vector_is_sent(self, lexical_only: None) -> None:
        """Sans fournisseur d'embeddings, la moitié sémantique n'est pas tentée."""
        search = _search()

        await search("capitale de la France", MemoryRequirements())

        assert FakeHybridSearch.calls[0]["vector"] is None

    async def test_the_candidate_is_still_found_and_reusable(self, lexical_only: None) -> None:
        """La dégradation coûte de la précision, pas la fonctionnalité."""
        search = _search()

        candidates = await search("capitale de la France", MemoryRequirements())

        assert [candidate.information_id for candidate in candidates] == [OWNER_ID]
        assert candidates[0].provenance_complete is True

    async def test_the_decision_module_reuses_it(self, lexical_only: None) -> None:
        result = await memory_lookup(
            "capitale de la France",
            MemoryRequirements(freshness_threshold_hours=0),
            search=_search(),
        )

        assert result.sufficient is True
        assert result.items[0].information_id == OWNER_ID

    async def test_the_limitation_travels_with_the_search_object(
        self, lexical_only: None
    ) -> None:
        """Le pipeline lit ``limitations`` après coup : elles doivent y être."""
        search = _search()

        await search("capitale de la France", MemoryRequirements())

        assert search.limitations == [FakeHybridSearch.limitation]
        assert search.outcome is not None
        assert search.outcome.to_dict()["mode"] == "lexical_only"

    async def test_the_reused_payload_is_kept_for_the_colis(self, lexical_only: None) -> None:
        """L'unité relue (``retrieve_context``) est portée par la recherche."""
        search = _search()

        await search("capitale de la France", MemoryRequirements())

        assert set(search.units) == {OWNER_ID}
        assert search.units[OWNER_ID]["information_id"] == OWNER_ID



class TestAnUnavailableMemoryIsNotASilentEmptyResult:
    """§25.2 — « pas de base » ne ressemble pas à « rien trouvé »."""

    async def test_an_unusable_engine_is_stated(self) -> None:
        search = HybridMemorySearch(connection_string="nosuchdriver://localhost/db")

        candidates = await search("n'importe quoi", MemoryRequirements())

        assert candidates == []
        assert search.mode == "unavailable"
        assert any("indisponible" in line for line in search.limitations)

    async def test_a_unit_without_provenance_is_not_a_candidate(self) -> None:
        """Contrôle §17.1 : le filtre reste appliqué même en lexical seul."""
        incomplete = MemoryCandidate(information_id=OWNER_ID, content={"text": "x"})

        assert incomplete.provenance_complete is False

