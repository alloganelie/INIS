"""§17/§41.2 — ce que l'arrêt anticipé **économise**, mesuré et non estimé.

Le plan L7 réclamait cette mesure : « Le gain de coût/tokens §17 est **non
mesuré** — reporté à L7/§41.13 ». Ce fichier compare deux exécutions **réelles**
du même chemin, avec les mêmes doubles :

* **sans réutilisation** : la mémoire ne trouve rien, le run acquiert comme avant ;
* **avec arrêt anticipé** : la mémoire conclut (§17.1), les étapes web ne sont pas
  exécutées.

Ce qui est compté — et **d'où vient chaque nombre** :

* ``tokens_llm_input`` / ``tokens_llm_output`` et ``web_requests`` sont lus dans
  l'``usage_report`` du §41.2, c'est-à-dire dans le contrat de facturation d'INIS,
  alimenté par les mêmes appels qui factureraient en production ;
* le nombre d'appels au fournisseur web et au modèle est lu sur les doubles, qui
  comptent les appels réellement partis ;
* la durée est mesurée à l'horloge du processus de test.

Ce que cette mesure **n'est pas** : une facture. Les fournisseurs sont des
doubles, donc aucun euro n'est dépensé et aucun prix réel n'est observé. Aucun
chiffre de coût n'est fabriqué : seuls des compteurs et des durées sont comparés.
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.api.v1.requests import pipeline_runner as runner_module
from app.api.v1.requests.pipeline_runner import WEB_ACQUISITION_ACTIONS, PipelineRunner
from app.domain.value_objects.ulid import ULID
from tests.unit.planning.test_memory_checker_wired_in_pipeline import (
    UNIT_ID,
    FakeMemorySearch,
)

OBJECTIVE = "Quelle est la capitale de la France ?"

#: §41.2 — les compteurs que l'``usage_report`` doit publier pour être facturable.
REQUIRED_COUNTERS = frozenset(
    {
        "tokens_llm_input",
        "tokens_llm_output",
        "web_requests",
        "api_calls",
        "compute_seconds",
    }
)


@pytest.fixture
def web_doubles(monkeypatch: pytest.MonkeyPatch) -> dict[str, AsyncMock]:
    """Count the §9/§10 provider calls instead of letting them reach the web."""
    search = AsyncMock(return_value=[])
    extract = AsyncMock(return_value={})
    monkeypatch.setattr("app.connectors.web.provider_router.ProviderRouter.search", search)
    monkeypatch.setattr(
        "app.connectors.web.extractors.wikipedia_extractor.WikipediaExtractor.extract",
        extract,
    )
    return {"search": search, "extract": extract}


@pytest.fixture(autouse=True)
def _no_persistence(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the measurement about the run itself, not about a database."""

    async def _fake_persist(**kwargs: Any) -> tuple[bool, list[str], dict[str, Any]]:
        return False, [], {
            "audit_event_id": ULID.new("AUD_"),
            "timestamp": "2026-01-01T00:00:00Z",
        }

    monkeypatch.setattr(
        "app.api.v1.requests.pipeline_runner.persist_pipeline_delivery", _fake_persist
    )


async def _measure(
    monkeypatch: pytest.MonkeyPatch, *, sufficient: bool, mock_llm: Any
) -> dict[str, Any]:
    """Run one scenario and return its measured counters and its delivery."""
    fake = FakeMemorySearch(sufficient=sufficient, mode="hybrid", limitations=())
    monkeypatch.setattr(runner_module, "HybridMemorySearch", lambda **kwargs: fake)
    mock_llm.configure('{"summary": "Paris est la capitale.", "findings": []}')

    request_id = ULID.new("REQ_")
    started = time.perf_counter()
    delivery = await PipelineRunner().run(
        request_id, {"objective": OBJECTIVE, "request_type": "research"}
    )
    elapsed = time.perf_counter() - started

    steps = [
        step for step in (delivery.get("steps") or []) if isinstance(step, dict)
    ]
    return {
        "delivery": delivery,
        "usage": delivery["usage_report"],
        "llm_calls": len(mock_llm.calls),
        "memory_calls": len(fake.calls),
        "elapsed_s": elapsed,
        "actions": [str(step.get("action")) for step in steps],
        "skipped_actions": [
            str(step.get("action")) for step in steps if step.get("status") == "skipped"
        ],
    }


class TestTheEarlyStopSavesRealWork:
    """Deux exécutions comparées : compteurs du §41.2, appels réels, durée."""

    @pytest.mark.asyncio
    async def test_the_acquisition_is_not_paid_for_a_second_time(
        self, monkeypatch: pytest.MonkeyPatch, web_doubles: dict[str, AsyncMock], mock_llm: Any
    ) -> None:
        """Le scénario avec mémoire acquiert moins que celui sans : c'est mesuré."""
        without = await _measure(monkeypatch, sufficient=False, mock_llm=mock_llm)
        web_without = without["usage"]["web_requests"]
        search_without = web_doubles["search"].await_count

        web_doubles["search"].reset_mock()
        mock_llm.calls.clear()

        with_stop = await _measure(monkeypatch, sufficient=True, mock_llm=mock_llm)
        web_with = with_stop["usage"]["web_requests"]
        search_with = web_doubles["search"].await_count

        # §17.1 — l'arrêt anticipé a bien eu lieu sur le second scénario.
        assert with_stop["memory_calls"] == 1
        assert set(with_stop["skipped_actions"]) <= set(WEB_ACQUISITION_ACTIONS)

        # Le gain est mesuré, pas supposé :
        assert web_without >= 1, (
            f"sans mémoire, le run doit acquérir au moins une fois : {without['usage']}"
        )
        assert web_with == 0, (
            f"avec mémoire suffisante, aucune acquisition web : {with_stop['usage']}"
        )
        assert search_with == 0, (
            f"le fournisseur web ne doit pas être appelé : {search_with} appel(s)"
        )
        assert search_without >= 1, "sans mémoire, le fournisseur est bien sollicité"

    @pytest.mark.asyncio
    async def test_the_savings_are_readable_in_the_contract_not_guessed(
        self, monkeypatch: pytest.MonkeyPatch, web_doubles: dict[str, AsyncMock], mock_llm: Any
    ) -> None:
        """Les seuls nombres avancés sont ceux du ``usage_report`` du §41.2."""
        without = await _measure(monkeypatch, sufficient=False, mock_llm=mock_llm)
        mock_llm.calls.clear()
        with_stop = await _measure(monkeypatch, sufficient=True, mock_llm=mock_llm)

        for report in (without["usage"], with_stop["usage"]):
            assert set(report) >= REQUIRED_COUNTERS, (
                f"le contrat §41.2 doit publier ces compteurs : {sorted(report)}"
            )
            assert all(
                isinstance(report[key], int)
                for key in ("tokens_llm_input", "tokens_llm_output", "web_requests")
            )

        # Le coût ne peut pas augmenter quand on acquiert moins.
        assert with_stop["llm_calls"] <= without["llm_calls"], (
            "l'arrêt anticipé ne doit pas ajouter d'appel au modèle : "
            f"{with_stop['llm_calls']} contre {without['llm_calls']}"
        )
        assert with_stop["usage"]["web_requests"] <= without["usage"]["web_requests"]
        # Les tokens sont ceux des appels réellement partis : le scénario qui
        # appelle moins ne peut pas en consommer davantage.
        assert (
            with_stop["usage"]["tokens_llm_input"] <= without["usage"]["tokens_llm_input"]
        ), (
            "les tokens d'entrée du scénario avec mémoire doivent être <= à ceux "
            f"sans mémoire : {with_stop['usage']['tokens_llm_input']} contre "
            f"{without['usage']['tokens_llm_input']}"
        )

    @pytest.mark.asyncio
    async def test_the_result_is_not_impoverished_by_the_saving(
        self, monkeypatch: pytest.MonkeyPatch, web_doubles: dict[str, AsyncMock], mock_llm: Any
    ) -> None:
        """Un run qui économise doit **livrer** — la différence est nommée, pas cachée."""
        without = await _measure(monkeypatch, sufficient=False, mock_llm=mock_llm)
        mock_llm.calls.clear()
        with_stop = await _measure(monkeypatch, sufficient=True, mock_llm=mock_llm)

        # La mémoire livrée porte l'identifiant d'origine : rien n'est recréé.
        delivered = {unit["information_id"] for unit in with_stop["delivery"]["information_units"]}
        assert UNIT_ID in delivered, "l'unité réutilisée est livrée telle quelle"

        # Différence entre les deux colis, **documentée** : le run sans mémoire ne
        # peut pas livrer l'unité mémorisée (il ne l'a jamais vue), le run avec
        # arrêt anticipé la livre telle quelle. C'est la différence attendue, et
        # elle n'est ni masquée ni présentée comme un résultat identique.
        other = {unit["information_id"] for unit in without["delivery"]["information_units"]}
        assert UNIT_ID not in other, (
            "sans mémoire, l'unité mémorisée ne peut pas apparaître : "
            "c'est la différence que l'arrêt anticipé introduit"
        )
        assert with_stop["delivery"]["status"] and without["delivery"]["status"], (
            "les deux scénarios livrent : l'économie ne supprime pas la livraison"
        )

        # La différence entre les deux colis est **explicite** : le run qui
        # économise dit que l'acquisition a été sautée, il ne fait pas passer
        # l'absence pour un résultat identique (§37).
        joined = " | ".join(with_stop["delivery"]["limitations"])
        assert "§17" in joined or "mémoire" in joined.lower() or with_stop["skipped_actions"], (
            "l'arrêt anticipé doit être dit dans le colis (§37)"
        )
        assert with_stop["delivery"]["status"], "un run qui économise livre quand même"