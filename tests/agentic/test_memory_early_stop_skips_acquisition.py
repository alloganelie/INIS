"""§17.1/§8.4 — une mémoire suffisante **arrête réellement** l'acquisition.

Le lot L4 a branché l'étape ``memory_lookup`` : le run *sait* ce qu'il sait déjà.
Il continuait pour autant à acquérir — la mémoire livrait son unité **en plus** de
tout le reste. Ce fichier verrouille la décision et ses conséquences :

* une recherche **hybride** sans limitation conclut la suffisance ⇒ les étapes
  d'acquisition web ne sont **pas exécutées** (pas seulement « inutiles » : le
  fournisseur n'est pas appelé), et elles figurent dans le colis en ``skipped`` ;
* l'unité réutilisée reste **intégralement livrée**, avec son identifiant ;
* la décision est **traçable** : événement §20 (charge utile auditée) et
  ``provenance.memory`` du colis ;
* une recherche **dégradée** (lexical seul) ou **limitée** réutilise mais
  **n'arrête rien** : c'est le garde-fou exigé, une poignée d'unités qui partagent
  des mots avec la question ne doit jamais couper un run.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.api.v1.requests.pipeline_runner import (
    WEB_ACQUISITION_ACTIONS,
    PipelineRunner,
)
from app.domain.value_objects.ulid import ULID
from tests.unit.planning.test_memory_checker_wired_in_pipeline import (
    UNIT_ID,
    FakeMemorySearch,
    _install_search,
    _run,
)


@pytest.fixture
def web_doubles(monkeypatch: pytest.MonkeyPatch) -> dict[str, AsyncMock]:
    """Silence the §9/§10 providers and record whether they were called."""
    search = AsyncMock(return_value=[])
    extract = AsyncMock(return_value={})
    monkeypatch.setattr("app.connectors.web.provider_router.ProviderRouter.search", search)
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
        return (
            False,
            [],
            {"audit_event_id": ULID.new("AUD_"), "timestamp": "2026-01-01T00:00:00Z"},
        )

    monkeypatch.setattr(
        "app.api.v1.requests.pipeline_runner.persist_pipeline_delivery", _fake_persist
    )
    return captured


@pytest.fixture
def audited(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Capture what the runner hands to the §20 audit of a memory lookup.

    The audit writer needs a database, which this test has not: the seam patched
    here is the runner's own ``_audit_memory_lookup``. What it *passes* is what
    the writer turns into an event — and the event's content is proven by
    ``tests/unit/governance/test_audit_memory_lookup.py``.
    """
    captured: list[dict[str, Any]] = []

    async def _capture(self: Any, request_id: str, result: dict[str, Any]) -> None:
        captured.append(dict(result.get("memory") or {}))

    monkeypatch.setattr(PipelineRunner, "_audit_memory_lookup", _capture)
    return captured


def _statuses(steps: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Return the ``(action, status)`` pairs of the executed steps."""
    return [(str(step.get("action")), str(step.get("status"))) for step in steps]


class TestASufficientMemoryStopsTheAcquisition:
    """Le cas nominal de §17.1 : la question a déjà sa réponse."""

    async def test_the_web_acquisition_is_not_executed(
        self,
        web_doubles: dict[str, AsyncMock],
        captured_steps: list[dict[str, Any]],
        mock_llm: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Le fournisseur web n'est pas appelé du tout, pas même « pour rien »."""
        _install_search(monkeypatch, FakeMemorySearch())

        await _run()

        web_doubles["search"].assert_not_awaited()
        web_doubles["extract"].assert_not_awaited()
        assert any(
            status == "skipped" for _, status in _statuses(captured_steps)
        ), f"aucune étape sautée : {_statuses(captured_steps)}"

    async def test_the_skipped_steps_are_the_web_ones_and_say_why(
        self,
        web_doubles: dict[str, AsyncMock],
        captured_steps: list[dict[str, Any]],
        mock_llm: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _install_search(monkeypatch, FakeMemorySearch())

        await _run()

        skipped = [step for step in captured_steps if step.get("status") == "skipped"]
        assert skipped, _statuses(captured_steps)
        for step in skipped:
            assert step["action"] in WEB_ACQUISITION_ACTIONS
            assert "§17.1" in str(step.get("output"))

    async def test_the_reused_unit_is_still_delivered(
        self,
        web_doubles: dict[str, AsyncMock],
        mock_llm: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Aucun contenu n'est perdu : l'arrêt ne retire rien du colis."""
        _install_search(monkeypatch, FakeMemorySearch())

        delivery = await _run()

        identifiers = [unit["information_id"] for unit in delivery["information_units"]]
        assert UNIT_ID in identifiers, identifiers

    async def test_the_delivery_carries_the_decision(
        self,
        web_doubles: dict[str, AsyncMock],
        mock_llm: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """La provenance du colis dit *pourquoi* le run s'est arrêté."""
        _install_search(monkeypatch, FakeMemorySearch())

        delivery = await _run()

        memory = delivery["provenance"]["memory"]
        assert memory["sufficient"] is True
        assert memory["stopped_acquisition"] is True
        assert memory["mode"] == "hybrid"
        assert memory["criteria"] == [
            "provenance_complete",
            "freshness_acceptable",
            "policy_allows_reuse",
        ]
        assert memory["withheld_reason"] is None
        assert UNIT_ID in memory["information_ids"]

    async def test_the_delivery_limitations_name_the_stop(
        self,
        web_doubles: dict[str, AsyncMock],
        mock_llm: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _install_search(monkeypatch, FakeMemorySearch())

        delivery = await _run()

        limitations = " | ".join(delivery["limitations"])
        assert "Acquisition arrêtée (§17.1)" in limitations
        assert "critères :" in limitations

    async def test_the_audit_event_carries_the_decision(
        self,
        web_doubles: dict[str, AsyncMock],
        audited: list[dict[str, Any]],
        mock_llm: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """§20 — une décision invisible serait une décision incontestable."""
        _install_search(monkeypatch, FakeMemorySearch())

        await _run()

        assert audited, "l'événement d'audit n'a pas été construit"
        note = audited[0]
        assert note["stopped_acquisition"] is True
        assert note["sufficient"] is True
        assert note["information_ids"] == [UNIT_ID]


class TestWhatNeverStopsTheAcquisition:
    """Le cas négatif exigé : mémoire insuffisante **ou** limitée."""

    async def test_a_lexical_only_memory_reuses_but_does_not_stop(
        self,
        web_doubles: dict[str, AsyncMock],
        captured_steps: list[dict[str, Any]],
        mock_llm: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _install_search(monkeypatch, FakeMemorySearch(mode="lexical_only"))

        delivery = await _run()

        # L'acquisition a bien tourné (le fournisseur est appelé)…
        web_doubles["search"].assert_awaited()
        assert not [step for step in captured_steps if step.get("status") == "skipped"]
        # …l'unité est quand même réutilisée (aucune perte)…
        assert UNIT_ID in [
            unit["information_id"] for unit in delivery["information_units"]
        ]
        # …et la raison est dite dans la provenance et dans les limitations.
        memory = delivery["provenance"]["memory"]
        assert memory["sufficient"] is True
        assert memory["stopped_acquisition"] is False
        assert "lexical_only" in str(memory["withheld_reason"])
        assert "Mémoire suffisante mais acquisition maintenue" in " | ".join(
            delivery["limitations"]
        )

    async def test_a_limited_search_does_not_stop(
        self,
        web_doubles: dict[str, AsyncMock],
        captured_steps: list[dict[str, Any]],
        mock_llm: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _install_search(
            monkeypatch,
            FakeMemorySearch(limitations=("2 candidat(s) sans vecteur",)),
        )

        delivery = await _run()

        web_doubles["search"].assert_awaited()
        assert not [step for step in captured_steps if step.get("status") == "skipped"]
        assert delivery["provenance"]["memory"]["stopped_acquisition"] is False

    async def test_an_insufficient_memory_keeps_the_normal_acquisition(
        self,
        web_doubles: dict[str, AsyncMock],
        captured_steps: list[dict[str, Any]],
        mock_llm: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Comportement inchangé : rien n'est arrêté et rien n'est réutilisé."""
        _install_search(monkeypatch, FakeMemorySearch(sufficient=False))

        delivery = await _run()

        web_doubles["search"].assert_awaited()
        assert not [step for step in captured_steps if step.get("status") == "skipped"]
        memory = delivery["provenance"]["memory"]
        assert memory["sufficient"] is False
        assert memory["stopped_acquisition"] is False
        assert all(
            unit["information_id"] != UNIT_ID for unit in delivery["information_units"]
        )
        assert not any(
            "Acquisition arrêtée" in limitation for limitation in delivery["limitations"]
        )
