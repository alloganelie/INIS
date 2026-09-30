"""§0.2/§22.3/§37 — no step output is ever fabricated.

``PipelineRunner`` used to answer a step it could not execute with the sentence
``"Extracted intelligence payload for <objective>"``, and — when even that failed
— with ``"Fallback execution output for <objective>"``. Neither sentence is a
result: they made an empty run look like a successful one, they were persisted as
step results, and they contradicted the §0.2 invariant that a delivery must be
traceable to material INIS actually obtained.

This file locks the replacement: an action the pipeline cannot execute produces a
``degraded`` step with an empty ``output`` and an ``error`` naming the cause, the
acquisition stage is **not** called for it (a ``file_ingest`` step used to become
a web search for the literal string ``file_ingest``), and the delivery says what
did not happen.

Mocked providers and LLM only — no Docker, no network.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.api.v1.requests.pipeline_runner import PipelineRunner
from app.domain.entities.search_result import SearchResult
from app.domain.value_objects.ulid import ULID

OBJECTIVE = "Ingère le fichier fourni par le client."

#: The two sentences that must never appear again, anywhere in a delivery.
FABRICATED_SENTENCES = (
    "Extracted intelligence payload for",
    "Fallback execution output for",
)


@pytest.fixture
def web_doubles(monkeypatch: pytest.MonkeyPatch) -> dict[str, AsyncMock]:
    """Mock the §9/§10 providers so any web call would be observable."""
    result = SearchResult(
        title="Paris — Wikipédia",
        url="https://fr.wikipedia.org/wiki/Paris",
        snippet="Paris est la capitale de la France.",
        score=0.95,
        provider="wikipedia",
    )
    search = AsyncMock(return_value=[result])
    extract = AsyncMock(
        return_value={
            "title": "Paris",
            "text": "Paris est la capitale de la France.",
            "language": "fr",
            "url": "https://fr.wikipedia.org/wiki/Paris",
            "error": None,
        }
    )
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
        return False, ["persistence: in-memory only (test)"], {
            "audit_event_id": ULID.new("AUD_"),
            "timestamp": "2026-01-01T00:00:00Z",
        }

    monkeypatch.setattr(
        "app.api.v1.requests.pipeline_runner.persist_pipeline_delivery", _fake_persist
    )
    return captured


def _explicit_plan(action: str) -> dict[str, Any]:
    """Return a one-step plan for *action*, as a client may submit."""
    return {
        "plan": {
            "plan_id": "PLAN_TEST",
            "steps": [
                {
                    "step_id": "STEP_TEST",
                    "order": 1,
                    "action": action,
                    "tool": "read_csv",
                    "inputs": {"requirement": OBJECTIVE},
                    "expected_output": "information_unit",
                }
            ],
        }
    }


async def _run(action: str, **payload: Any) -> tuple[dict[str, Any], PipelineRunner]:
    """Run one delivery with the given plan action."""
    runner = PipelineRunner()
    body: dict[str, Any] = {"objective": OBJECTIVE}
    body.update(payload)
    body.update(_explicit_plan(action))
    return await runner.run(ULID.new("REQ_"), body), runner


@pytest.mark.asyncio
async def test_a_non_web_action_degrades_without_inventing_output(
    web_doubles: dict[str, AsyncMock],
    captured_steps: list[dict[str, Any]],
    mock_llm: Any,
) -> None:
    """§8.4/§37 — the step reports the gap; it does not produce text."""
    mock_llm.configure('{"summary": "Rien à livrer.", "findings": []}')

    delivery, _ = await _run("file_ingest")

    assert captured_steps, "the delivery must describe what the step did"
    step = captured_steps[0]
    assert step["status"] == "degraded"
    assert step["output"] == "", "a degraded step carries no output"
    assert step["error"], "the reason must be stated"
    assert step["tools_required"], "the §21 tools it would need must be named"
    assert any("file_ingest" in limitation for limitation in delivery["limitations"])


@pytest.mark.asyncio
async def test_a_non_web_action_never_becomes_a_web_search(
    web_doubles: dict[str, AsyncMock],
    captured_steps: list[dict[str, Any]],
    mock_llm: Any,
) -> None:
    """The acquisition stage is not called for an action it cannot execute."""
    mock_llm.configure('{"summary": "Rien à livrer.", "findings": []}')

    await _run("query_database")

    assert web_doubles["search"].await_count == 0
    assert web_doubles["extract"].await_count == 0


@pytest.mark.asyncio
async def test_no_delivery_contains_a_fabricated_sentence(
    web_doubles: dict[str, AsyncMock],
    captured_steps: list[dict[str, Any]],
    mock_llm: Any,
) -> None:
    """The two sentences that used to fake a result are gone for good."""
    mock_llm.configure('{"summary": "Rien à livrer.", "findings": []}')

    delivery, _ = await _run("file_ingest")
    serialised = json.dumps(delivery, default=str) + json.dumps(captured_steps, default=str)

    for sentence in FABRICATED_SENTENCES:
        assert sentence not in serialised

    assert delivery["findings"] == [], "nothing was obtained, so nothing is reported"
    assert delivery["status"] == "INSUFFICIENT_EVIDENCE"


@pytest.mark.asyncio
async def test_an_unknown_action_is_refused_by_name(
    web_doubles: dict[str, AsyncMock],
    captured_steps: list[dict[str, Any]],
    mock_llm: Any,
) -> None:
    """§8.4 — an action outside the closed vocabulary refuses the whole plan."""
    mock_llm.configure('{"summary": "Rien à livrer.", "findings": []}')

    delivery, _ = await _run("bricoler_quelque_chose")

    assert all(
        step.get("action") != "bricoler_quelque_chose" for step in captured_steps
    ), "a refused plan must not be executed"
    assert all(step.get("step_id") != "STEP_TEST" for step in captured_steps)
    assert any("bricoler_quelque_chose" in text for text in delivery["limitations"])
    assert any("hors du vocabulaire fermé" in text for text in delivery["limitations"])


@pytest.mark.asyncio
async def test_an_llm_action_outside_the_vocabulary_refuses_the_llm_plan(
    web_doubles: dict[str, AsyncMock],
    captured_steps: list[dict[str, Any]],
    mock_llm: Any,
) -> None:
    """§8.4 — the LLM plan is validated too; the deterministic plan runs instead."""
    mock_llm.configure(
        '{"steps": [{"order": 1, "action": "bricoler", "tool": "x", '
        '"description": "faire un truc", "expected_output": "y"}]}'
    )

    runner = PipelineRunner()
    delivery = await runner.run(ULID.new("REQ_"), {"objective": OBJECTIVE})

    assert all(step.get("action") != "bricoler" for step in captured_steps)
    assert any(step.get("action") == "collect_information" for step in captured_steps), (
        "the validated plan must still run"
    )
    assert any("bricoler" in text for text in delivery["limitations"])


@pytest.mark.asyncio
async def test_an_llm_description_never_becomes_an_action(
    web_doubles: dict[str, AsyncMock],
    captured_steps: list[dict[str, Any]],
    mock_llm: Any,
) -> None:
    """§0.2 — a sentence is not an action: the LLM plan is refused, not repaired."""
    sentence = "Ingere le fichier puis calcule la moyenne des ventes"
    mock_llm.configure(f'{{"steps": [{{"description": "{sentence}"}}]}}')

    runner = PipelineRunner()
    delivery = await runner.run(ULID.new("REQ_"), {"objective": OBJECTIVE})

    serialised = json.dumps(captured_steps, default=str)
    assert sentence not in serialised, "prose must never decide what runs"
    assert any(step.get("action") == "collect_information" for step in captured_steps)
    assert any("'<absente>'" in text for text in delivery["limitations"])


@pytest.mark.asyncio
async def test_the_web_path_still_produces_traceable_material(
    web_doubles: dict[str, AsyncMock],
    captured_steps: list[dict[str, Any]],
    mock_llm: Any,
) -> None:
    """Control: the action that *is* wired keeps working, and its step is `done`."""
    mock_llm.configure('{"summary": "Paris est la capitale.", "findings": []}')

    _, _ = await _run("collect_information")

    assert web_doubles["search"].await_count >= 1
    assert captured_steps[0]["status"] == "done"
    assert captured_steps[0]["output"], "a successful search reports what it found"
