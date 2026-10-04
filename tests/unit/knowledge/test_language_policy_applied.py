"""§41.3 — la langue **effective** des unités est tracée, et un mélange se dit.

Le plan demandait de vérifier deux choses que la suite ne démontrait pas :

* la langue des unités est **tracée** sur l'unité elle-même, pas seulement dans la
  tête du pipeline ;
* un **mélange de langues** ne passe pas silencieusement pour une langue unique.

Ce que ce fichier établit, sur la donnée **réellement produite** :

* les deux règles pures du §41.3 — le bloc de langue d'une unité (absence
  comprise : aucune étiquette n'est inventée) et la phrase qui décrit ce qu'une
  livraison a observé ;
* **l'intégration réelle** : `PipelineRunner.run()` alimenté par des sources en
  français, en allemand et **sans langue** produit des unités qui portent chacune
  leur bloc, la livraison qui **dit** le mélange, et des lignes **persistées**
  dont le `context` porte le bloc — la langue effective survit donc au
  redémarrage.

Ce que ce fichier ne fait pas : il n'invente ni détecteur (la détection est celle
du dépôt, ``app.knowledge.enrichment.detect_language``), ni code de mélange — la
spec n'en définit aucun, et la représentation d'une langue non établie dans le
dépôt est l'absence (``None``), pour l'unité comme pour le bloc.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text

from app.api.v1.requests.pipeline_runner import PipelineRunner
from app.domain.entities.search_result import SearchResult
from app.domain.value_objects.ulid import ULID
from app.knowledge.normalization.language_policy import (
    UNKNOWN_LANGUAGE_BLOCK,
    LanguagePolicy,
    describe_observed_languages,
    language_block,
)

#: Les quatre règles [CONFIG] du §41.3, telles que la requête les porte.
POLICY = LanguagePolicy(
    working_language="en",
    source_languages_allowed=("en", "fr", "de"),
    translation_policy="always",
    normalization_locale="en-US",
)

#: Trois sources : deux langues différentes et une dont rien ne permet de dire la
#: langue (texte trop court pour que la détection du dépôt se prononce — elle
#: préfère ne rien dire plutôt que de se tromper).
PAGES: dict[str, tuple[str | None, str]] = {
    "https://fr.wikipedia.org/wiki/Paris": (
        "fr",
        (
            "Paris est la capitale de la France et la ville la plus peuplee du pays. "
            "Elle compte de nombreux monuments et musees."
        ),
    ),
    "https://de.wikipedia.org/wiki/Berlin": (
        "de",
        (
            "Berlin ist die Hauptstadt der Bundesrepublik Deutschland und ein Land. "
            "Die Stadt hat viele Museen und ist ein wichtiger Verkehrsknotenpunkt."
        ),
    ),
    "https://example.org/muet": (None, "???"),
}


class TestLanguageBlock:
    """§41.3 — le bloc que chaque unité DOIT porter, absence comprise."""

    def test_a_known_language_fills_the_five_spec_fields(self) -> None:
        block = language_block(POLICY, "fr")

        assert block["source_language"] == "fr"
        assert block["normalized_language"] == "fr", "sans traduction, la langue ne change pas"
        assert block["translation_applied"] is False
        assert block["translation_model"] is None
        assert block["translation_transformation_id"] is None

    def test_an_unknown_language_is_not_replaced_by_english(self) -> None:
        """Le défaut corrigé : une langue inconnue était déclarée « en »."""
        block = language_block(POLICY, None)

        assert block == UNKNOWN_LANGUAGE_BLOCK
        assert block["source_language"] is None, "aucune étiquette n'est inventée"
        assert block["normalized_language"] is None

    def test_a_malformed_tag_is_treated_as_an_absence(self) -> None:
        """« english ! » n'est pas une langue BCP-47 : pas d'étiquette inventée."""
        assert language_block(POLICY, "english !") == UNKNOWN_LANGUAGE_BLOCK

    def test_without_a_usable_policy_no_language_is_claimed(self) -> None:
        assert language_block(None, "fr") == UNKNOWN_LANGUAGE_BLOCK


class TestObservedLanguagesStatement:
    """§41.3 — « pas de mélange silencieux » : ce que la livraison doit dire."""

    def test_a_single_working_language_says_nothing(self) -> None:
        """Rien à dire : la livraison n'est pas remplie d'une phrase vide."""
        assert describe_observed_languages(POLICY, ["en", "en-US"]) is None
        assert describe_observed_languages(POLICY, []) is None

    def test_a_mixture_names_the_languages_it_observed(self) -> None:
        statement = describe_observed_languages(POLICY, ["fr", "de"])

        assert statement is not None
        assert "de" in statement and "fr" in statement
        assert "aucune langue unique n'est affirmée" in statement

    def test_units_without_a_language_are_counted_not_guessed(self) -> None:
        statement = describe_observed_languages(POLICY, ["fr", None, None])

        assert statement is not None
        assert "2 unité(s) sans langue identifiée" in statement
        assert "sans** étiquette" in statement

    def test_a_required_translation_that_did_not_happen_is_stated(self) -> None:
        """La politique « always » exige une traduction ; INIS n'en applique aucune."""
        statement = describe_observed_languages(POLICY, ["de"])

        assert statement is not None
        assert "hors langue de travail" in statement
        assert "exige une traduction" in statement
        assert "aucune n'a été appliquée" in statement

    def test_a_language_the_policy_refuses_is_not_translated_silently(self) -> None:
        statement = describe_observed_languages(POLICY, ["es"])

        assert statement is not None
        assert "source_languages_allowed" in statement
        assert "ne les traduit pas silencieusement" in statement

    def test_an_unusable_policy_is_stated_rather_than_hidden(self) -> None:
        statement = describe_observed_languages(None, ["fr", "de"])

        assert statement is not None
        assert "sans bloc de langue §41.3" in statement


@pytest.fixture
def multilingual_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    """Feed the acquisition stage with three pages: French, German, and a silent one."""
    results = [
        SearchResult(
            title=url.rsplit("/", 1)[-1],
            url=url,
            snippet="page",
            score=0.9,
            provider="wikipedia",
        )
        for url in PAGES
    ]

    async def extract(url: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        language, body = PAGES[url]
        return {
            "title": url,
            "text": body,
            "language": language,
            "url": url,
            "error": None,
        }

    monkeypatch.setattr(
        "app.connectors.web.provider_router.ProviderRouter.search",
        AsyncMock(return_value=results),
    )
    monkeypatch.setattr(
        "app.connectors.web.extractors.wikipedia_extractor.WikipediaExtractor.extract",
        AsyncMock(side_effect=extract),
    )


async def _run_multilingual() -> dict[str, Any]:
    """Run the real pipeline over the three sources, with the §41.3 policy set."""
    return await PipelineRunner().run(
        ULID.new("REQ_"),
        {
            "objective": "Comparer des sources de langues differentes",
            "context": {
                "working_language": "en",
                "source_languages_allowed": ["en", "fr", "de"],
                "translation_policy": "always",
            },
        },
    )


@pytest.mark.asyncio
async def test_every_delivered_unit_carries_its_own_language_block(
    multilingual_sources: None, mock_llm: Any
) -> None:
    """§41.3 — le bloc est porté par l'unité, avec **sa** langue, jamais une autre."""
    mock_llm.configure(json.dumps({"summary": "s", "findings": []}))

    delivery = await _run_multilingual()

    units = delivery["information_units"]
    assert units, "le pipeline doit livrer les unités extraites"
    for unit in units:
        for field in (
            "source_language",
            "normalized_language",
            "translation_applied",
            "translation_model",
            "translation_transformation_id",
        ):
            assert field in unit, f"champ §41.3 manquant : {field}"

    observed = {unit["source_language"] for unit in units}
    assert observed == {"fr", "de", None}, (
        "chaque unité porte sa langue observée, et l'unité muette reste sans "
        f"étiquette — observé : {observed}"
    )
    assert "en" not in observed, "aucune unité ne doit être déclarée « en » par défaut"


@pytest.mark.asyncio
async def test_the_delivery_states_the_languages_it_observed(
    multilingual_sources: None, mock_llm: Any
) -> None:
    """§41.3 — le mélange est dit dans la livraison, pas laissé implicite."""
    mock_llm.configure(json.dumps({"summary": "s", "findings": []}))

    delivery = await _run_multilingual()

    stated = [
        line
        for line in delivery["limitations"]
        if "langue" in line or "traduction" in line
    ]
    joined = " ".join(stated)
    assert "langues observées dans cette livraison : de, fr" in joined
    assert "1 unité(s) sans langue identifiée" in joined
    assert "exige une traduction" in joined, (
        "la politique « always » exige une traduction : l'écart doit être dit"
    )


@pytest.mark.asyncio
async def test_the_effective_language_survives_persistence(
    db_url: str,
    multilingual_sources: None,
    mock_llm: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§3/§7 — la langue effective est **persistée** avec l'unité (§27), pas seulement livrée."""
    from app.storage.database.engine import create_engine, set_default_engine

    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    monkeypatch.setenv("DATABASE_URL", db_url)
    set_default_engine(None)
    mock_llm.configure(json.dumps({"summary": "s", "findings": []}))
    engine = create_engine(db_url)
    try:
        delivery = await _run_multilingual()

        delivered = {
            str(unit["information_id"]): unit["source_language"]
            for unit in delivery["information_units"]
        }
        assert delivered, "des unités doivent avoir été livrées"

        async with engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        "SELECT id, language, context ->> 'language' AS block "
                        "FROM information_units WHERE id = ANY(:ids)"
                    ),
                    {"ids": list(delivered)},
                )
            ).mappings().all()

        assert len(rows) == len(delivered), "chaque unité livrée a été persistée"
        for row in rows:
            block = json.loads(row["block"])
            assert block["source_language"] == delivered[row["id"]], (
                "le bloc persisté doit porter la langue observée de l'unité"
            )
            # §41.3 — la colonne ``language`` reste l'étiquette observée, et ``None``
            # y reste ``None`` : rien n'a été inventé pour remplir la colonne.
            assert row["language"] == delivered[row["id"]]
    finally:
        set_default_engine(None)
        await engine.dispose()
