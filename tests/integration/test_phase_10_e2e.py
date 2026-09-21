"""PHASE-10 smoke: vraie recherche web (providers §10.1, extraction, fiabilité §10.2)."""

from __future__ import annotations

import importlib
import importlib.util
import json
import os

import pytest


def _has_module(module_name: str) -> bool:
    """Return True if *module_name* can be found without importing it."""
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ModuleNotFoundError, ValueError):
        return False


def _has_symbol(module_name: str, symbol: str) -> bool:
    """Return True if *module_name* defines *symbol* (False si absent)."""
    if not _has_module(module_name):
        return False
    try:
        module = importlib.import_module(module_name)
    except ImportError:
        return False
    return getattr(module, symbol, None) is not None


def _import_or_skip(module_name: str):
    """Import *module_name* or skip the test if it is absent."""
    if not _has_module(module_name):
        pytest.skip(f"module absent: {module_name}")
    return importlib.import_module(module_name)


def _symbol_or_skip(module, module_name: str, symbol: str):
    """Return *symbol* from *module* or skip if it is not defined."""
    value = getattr(module, symbol, None)
    if value is None:
        pytest.skip(f"symbol absent: {symbol} in {module_name}")
    return value


def test_wikipedia_provider_imports() -> None:
    """Provider Wikipedia gratuit §9.1/§10.1 (skip si module absent)."""
    module_name = "app.connectors.web.providers.wikipedia_provider"
    module = _import_or_skip(module_name)
    provider = _symbol_or_skip(module, module_name, "WikipediaProvider")
    assert provider.provider_id == "wikipedia"


def test_provider_router_fallback_imports(monkeypatch) -> None:
    """Router §10.1 avec repli Wikipedia sans clé (skip si module absent)."""
    module_name = "app.connectors.web.provider_router"
    module = _import_or_skip(module_name)
    router_cls = _symbol_or_skip(module, module_name, "ProviderRouter")
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    router = router_cls()
    assert router.provider_ids == ("wikipedia",)
    assert router.resolve().provider_id == "wikipedia"


def test_fact_extractor_imports() -> None:
    """Extracteur de faits traçables (skip si module absent)."""
    module_name = "app.knowledge.extraction.fact_extractor"
    module = _import_or_skip(module_name)
    _symbol_or_skip(module, module_name, "FactExtractor")


def test_source_reliability_imports() -> None:
    """Score de fiabilité §10.2 (skip si module absent)."""
    module_name = "app.quality.source_reliability"
    module = _import_or_skip(module_name)
    _symbol_or_skip(module, module_name, "SourceReliabilityScorer")


async def test_wikipedia_provider_smoke() -> None:
    """Wikipedia via httpx mocké : mapping OpenSearch → SearchResult (skip si absent)."""
    import httpx

    module_name = "app.connectors.web.providers.wikipedia_provider"
    module = _import_or_skip(module_name)
    provider_cls = _symbol_or_skip(module, module_name, "WikipediaProvider")

    payload = [
        "Paris",
        ["Paris"],
        ["Capitale de la France."],
        ["https://fr.wikipedia.org/wiki/Paris"],
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert "wikipedia.org" in str(request.url)
        return httpx.Response(200, json=payload)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        results = await provider_cls(client=client, language="fr").search("Paris", limit=5)
    finally:
        await client.aclose()
    assert len(results) == 1
    result = results[0]
    assert result.title == "Paris"
    assert result.url == "https://fr.wikipedia.org/wiki/Paris"
    assert result.provider == "wikipedia"
    assert result.score == pytest.approx(0.9)


async def test_fact_extractor_pipeline() -> None:
    """Extraction → N unités traçables (skip si module absent)."""
    module_name = "app.knowledge.extraction.fact_extractor"
    module = _import_or_skip(module_name)
    extractor_cls = _symbol_or_skip(module, module_name, "FactExtractor")
    splitter = _import_or_skip("app.knowledge.extraction.sentence_splitter")

    text = (
        "Paris est la capitale de la France. "
        "La Tour Eiffel mesure 330 mètres. "
        "La Seine traverse la ville."
    )
    expected = len(splitter.split_sentences(text))
    assert expected >= 2

    units = await extractor_cls().extract(
        text,
        source_id="SRC_TEST_01",
        document_id="DOC_TEST_01",
        url="https://fr.wikipedia.org/wiki/Paris",
    )
    assert len(units) == expected
    for unit in units:
        assert unit["information_id"].startswith("INF_")
        assert unit["evidence_id"].startswith("EVID_")
        assert unit["source_id"] == "SRC_TEST_01"
        assert unit["document_id"] == "DOC_TEST_01"
        assert unit["data_stage"] == "raw"
        assert unit["epistemic_status"] == "factual"
        assert unit["provenance"]["method"] == "fact_extractor"


def test_source_reliability_scoring() -> None:
    """Barème §10.2 sur URLs de test (skip si module absent)."""
    module_name = "app.quality.source_reliability"
    module = _import_or_skip(module_name)
    scorer_cls = _symbol_or_skip(module, module_name, "SourceReliabilityScorer")

    scorer = scorer_cls()
    gov = scorer.score("https://www.data.gouv.fr/dataset")
    wiki = scorer.score("https://fr.wikipedia.org/wiki/Paris")
    media = scorer.score("https://www.lemonde.fr/article")
    social = scorer.score("https://twitter.com/status")
    unknown = scorer.score("https://example-unknown-xyz.org/page")
    assert gov == pytest.approx(0.95)
    assert wiki == pytest.approx(0.85)
    assert media == pytest.approx(0.6)
    assert social == pytest.approx(0.3)
    assert unknown == pytest.approx(0.5)
    assert gov > wiki > media > social


async def test_pipeline_web_search_e2e() -> None:
    """Vraie recherche Serper (skip si SERPER_API_KEY absent)."""
    if not os.environ.get("SERPER_API_KEY"):
        pytest.skip("SERPER_API_KEY absent : recherche réelle non exécutée")
    module_name = "app.connectors.web.provider_router"
    module = _import_or_skip(module_name)
    router_cls = _symbol_or_skip(module, module_name, "ProviderRouter")

    router = router_cls()
    assert router.resolve().provider_id == "serper"
    results = await router.search("capitale de la France", limit=2)
    assert results, "aucun résultat Serper"
    for result in results:
        assert result.url and result.title
        assert result.provider == "serper"


def _fake_complete(content: str):
    """Fabrique un `ModelRouter.complete` async retournant *content* (stub=False)."""
    from app.llm.router.model_router import LLMResponse

    async def _complete(self, task, prompt, **kwargs):
        return LLMResponse(content=content, model="fake-test", stub=False)

    return _complete


async def test_pipeline_marks_real_findings(monkeypatch) -> None:
    """Seuls les findings avec source_id SRC_ restent vérifiés (skip si absent)."""
    module_name = "app.api.v1.requests.pipeline_runner"
    module = _import_or_skip(module_name)
    runner_cls = _symbol_or_skip(module, module_name, "PipelineRunner")
    router_module = _import_or_skip("app.llm.router.model_router")

    content = json.dumps(
        {
            "summary": "Synthèse de test.",
            "findings": [
                {
                    "finding": "Paris est la capitale de la France.",
                    "source_id": "SRC_WIKIPEDIA_01",
                    "evidence_id": "EVID_01",
                },
                "Le ciel est bleu.",
            ],
        }
    )
    monkeypatch.setattr(
        router_module.ModelRouter, "complete", _fake_complete(content)
    )
    out = await runner_cls().run("REQ_TEST10", {"objective": "test findings"})
    assert len(out["findings"]) == 1
    assert out["findings"][0]["source_id"] == "SRC_WIKIPEDIA_01"
    assert out["status"] == "completed"
    dropped = [a["statement"] for a in out["assumptions"]]
    assert any("ciel est bleu" in s for s in dropped)


async def test_pipeline_does_not_use_llm_as_source(monkeypatch) -> None:
    """§0.2 inv.8 : le LLM n'est jamais source unique d'un fait (skip si absent)."""
    module_name = "app.api.v1.requests.pipeline_runner"
    module = _import_or_skip(module_name)
    runner_cls = _symbol_or_skip(module, module_name, "PipelineRunner")
    router_module = _import_or_skip("app.llm.router.model_router")

    content = json.dumps(
        {
            "summary": "Synthèse non sourcée.",
            "findings": [
                {"finding": "Le LLM affirme X.", "source_id": "llm"},
                {"finding": "Z sans preuve.", "source_id": "hypothesis"},
                "Y sans source.",
            ],
        }
    )
    monkeypatch.setattr(
        router_module.ModelRouter, "complete", _fake_complete(content)
    )
    out = await runner_cls().run("REQ_TEST10B", {"objective": "test §0.2"})
    assert out["findings"] == []
    assert out["status"] == "INSUFFICIENT_EVIDENCE"
    assert out["assumptions"], "attendus : claims reléguées en hypothèses"
    for assumption in out["assumptions"]:
        assert assumption["epistemic_status"] == "hypothesis"
        assert assumption["reason"] == "no_source"
