"""§12/§16/§17.1 — what the « enriched » step of a unit must and must not do.

The lifecycle of §12 is a chain (``raw → normalized → enriched → derived``). This
file pins each link the enricher owns:

* notation is normalised, **content is never rewritten**: ``15/01/2024`` gains an
  ISO form beside its original span, ``12 kilos`` gains ``kg``, ``1 234,50 €``
  gains ``EUR`` — and no value is ever converted or invented (§0.2);
* the convention comes from somewhere: the unit's own declared or detected
  language, otherwise the policy locale. An unknown convention produces *no*
  value and one stated limitation, never a plausible neighbour;
* the language is detected by a documented stop-word ratio, or not at all: the
  answer is ``None`` rather than a probability (§11, §0.2);
* the fingerprint covers the source material, never the enrichment block, so a
  unit that was enriched is still recognised as itself (§17.1);
* a stage jump is **refused**: a ``raw`` unit is not promoted to ``enriched``,
  and an already ``enriched`` one is left untouched (idempotence).
"""

from __future__ import annotations

import pytest

from app.knowledge.enrichment import (
    STAGE_ORDER,
    EnrichedUnit,
    EnrichmentOutcome,
    StageTransitionError,
    advance_stage,
    can_transition,
    detect_language,
    enrich_units,
    normalize_currencies,
    normalize_dates,
    normalize_measures,
    resolved_dataset_stages,
    unit_fingerprint,
    unit_text,
)
from app.knowledge.normalization.language_policy import LanguagePolicy

GOOD_ID = "INF_01M3Q0000000000000000000AA"
OTHER_ID = "INF_01M3Q0000000000000000000AB"
FRENCH_TEXT = "Le fournisseur a livré le 15/01/2024 et 12 kilos de café."


def _unit(
    *,
    information_id: str = GOOD_ID,
    text: str,
    data_stage: str = "normalized",
    language: str | None = None,
    source_id: str = "SRC_01M3Q0000000000000000000AA",
) -> dict:
    """Return a minimal §11 unit whose analysable text is *text*."""
    return {
        "information_id": information_id,
        "type": "text",
        "content": {"text": text},
        "source_id": source_id,
        "document_id": "DOC_01M3Q0000000000000000000AA",
        "location": {"kind": "page", "page": 1},
        "context": {"request_id": "REQ_01M3Q0000000000000000000AA"},
        "language": language,
        "data_stage": data_stage,
    }


class TestStageOrder:
    """The §12 chain, and the refusal of every shortcut across it."""

    def test_the_order_is_the_one_of_the_spec(self) -> None:
        assert STAGE_ORDER == ("raw", "normalized", "enriched", "derived")

    @pytest.mark.parametrize(
        ("origin", "target"),
        [
            ("raw", "normalized"),
            ("normalized", "enriched"),
            ("enriched", "derived"),
        ],
    )
    def test_a_single_step_is_allowed(self, origin: str, target: str) -> None:
        assert can_transition(origin, target) is True
        assert advance_stage(origin, target) == target

    @pytest.mark.parametrize(
        ("origin", "target"),
        [
            ("raw", "enriched"),
            ("raw", "derived"),
            ("normalized", "derived"),
            ("derived", "normalized"),
            ("enriched", "raw"),
            ("", "normalized"),
            ("unknown", "normalized"),
        ],
    )
    def test_a_jump_or_a_rewind_is_refused(self, origin: str, target: str) -> None:
        assert can_transition(origin, target) is False

    def test_advance_stage_names_the_unit_it_refused(self) -> None:
        with pytest.raises(StageTransitionError) as excinfo:
            advance_stage("raw", "enriched", context=GOOD_ID)

        assert GOOD_ID in str(excinfo.value)
        assert "raw" in str(excinfo.value)
        assert "enriched" in str(excinfo.value)

    def test_a_stage_with_no_predecessor_is_refused(self) -> None:
        assert can_transition(None, "raw") is False
        assert can_transition("raw", None) is False


class TestDatesAreReadNotGuessed:
    """§12/§0.2 — a date is normalised only when its convention is known."""

    def test_an_iso_date_is_kept_as_it_is(self) -> None:
        values = normalize_dates("Livraison le 2024-01-15 confirmée")

        assert len(values) == 1
        assert values[0].value["iso"] == "2024-01-15"
        assert values[0].value["order"] == "YMD"
        assert values[0].raw == "2024-01-15"

    def test_the_span_points_back_at_the_original_text(self) -> None:
        text = "Facturé le 15/01/2024 par le fournisseur"
        value = normalize_dates(text, locale="fr-FR")[0]

        assert text[value.start : value.end] == "15/01/2024"
        assert value.to_dict()["offset"] == value.start
        assert value.to_dict()["length"] == 10

    def test_a_french_day_first_date_is_not_swapped(self) -> None:
        assert normalize_dates("le 15/01/2024", locale="fr-FR")[0].value["iso"] == "2024-01-15"

    def test_an_american_month_first_date_is_not_swapped(self) -> None:
        assert normalize_dates("on 01/15/2024", locale="en-US")[0].value["iso"] == "2024-01-15"

    def test_a_british_locale_reads_day_first(self) -> None:
        assert normalize_dates("on 15/01/2024", locale="en-GB")[0].value["order"] == "DMY"

    @pytest.mark.parametrize(
        "text",
        [
            "15 January 2024",
            "15 janvier 2024",
            "January 15, 2024",
        ],
    )
    def test_a_textual_date_needs_no_locale(self, text: str) -> None:
        values = normalize_dates(text)

        assert [value.value["iso"] for value in values] == ["2024-01-15"]

    def test_an_impossible_calendar_date_produces_nothing(self) -> None:
        assert normalize_dates("2024-02-31") == []

    def test_an_unknown_locale_leaves_a_short_date_alone(self) -> None:
        assert normalize_dates("03/04/2024", locale="xx-YY") == []

    def test_a_date_is_never_normalised_twice(self) -> None:
        # The ISO form is read by ``_YMD_RE`` and the same span must not be read
        # again as a short numeric date.
        assert len(normalize_dates("2024-01-15", locale="fr-FR")) == 1

    def test_a_two_digit_year_follows_the_iso_8601_window(self) -> None:
        assert normalize_dates("15/01/69", locale="fr-FR")[0].value["iso"] == "1969-01-15"
        assert normalize_dates("15/01/68", locale="fr-FR")[0].value["iso"] == "2068-01-15"


class TestMeasuresAndAmounts:
    """§12 — the notation is canonicalised, the value is never converted."""

    def test_a_french_alias_becomes_its_symbol(self) -> None:
        value = normalize_measures("12 kilos de café")[0]

        assert value.value["value"] == 12
        assert value.value["unit"] == "kg"
        assert value.value["dimension"] == "mass"

    def test_an_unknown_unit_is_left_untouched(self) -> None:
        # No source states what a « stone » is worth in this system: inventing
        # the equivalence would be an invented fact (§0.2).
        assert normalize_measures("12 stones de laine") == []

    def test_a_compound_unit_wins_over_its_parts(self) -> None:
        assert normalize_measures("90 km/h sur l'autoroute")[0].value["unit"] == "km/h"

    def test_no_conversion_is_performed(self) -> None:
        value = normalize_measures("5 miles à pied")[0]

        assert value.value["unit"] == "mi"
        assert value.value["value"] == 5

    def test_an_amount_left_of_the_symbol_is_read_too(self) -> None:
        value = normalize_currencies("1 234,50 € HT", locale="fr-FR")[0]

        assert value.value["value"] == 1234.5
        assert value.value["currency"] == "EUR"
        assert value.value["order"] == "amount_first"

    def test_an_amount_right_of_the_symbol_is_read_too(self) -> None:
        value = normalize_currencies("€12", locale="fr-FR")[0]

        assert value.value["value"] == 12
        assert value.value["order"] == "symbol_first"

    def test_an_iso_code_amount_is_read_without_any_locale(self) -> None:
        assert normalize_currencies("500 USD")[0].value["currency"] == "USD"

    def test_a_ambiguous_symbol_is_never_resolved(self) -> None:
        # ``$`` is USD, CAD, AUD… choosing one would be an invention (§0.2).
        assert normalize_currencies("500 $", locale="en-US") == []

    @pytest.mark.parametrize(
        ("text", "locale", "expected"),
        [
            ("1.5 kg", "en-US", 1.5),
            ("1,5 kg", "fr-FR", 1.5),
            ("1 234 kg", "fr-FR", 1234),
            ("1,234 kg", "en-US", 1234),
            ("1.234,56 kg", "fr-FR", 1234.56),
            ("1,234.56 kg", "en-US", 1234.56),
        ],
    )
    def test_the_locale_decides_what_a_separator_means(
        self, text: str, locale: str, expected: float
    ) -> None:
        assert normalize_measures(text, locale=locale)[0].value["value"] == expected

    @pytest.mark.parametrize(
        ("text", "locale"),
        [
            ("1.5 kg", "fr-FR"),  # a dot is not a decimal in the FR family…
            ("1,5 kg", "en-US"),  # …and a comma is not one in the US convention,
            ("1.2.3 kg", "en-US"),  # and neither is a broken grouping.
        ],
    )
    def test_an_unreadable_number_is_not_reinterpreted(self, text: str, locale: str) -> None:
        assert normalize_measures(text, locale=locale) == []


class TestLanguageDetection:
    """§41.3/§0.2 — a detected language or nothing, never a probability."""

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("The supplier did not confirm the price and it was not updated", "en"),
            ("Le fournisseur n'a pas confirmé le prix et il n'est pas à jour", "fr"),
            ("El precio de la casa es muy alto para los clientes del pueblo", "es"),
            ("Der Preis ist nicht im System und die Werte sind falsch", "de"),
        ],
    )
    def test_the_four_languages_of_the_policy_are_recognised(
        self, text: str, expected: str
    ) -> None:
        assert detect_language(text) == expected

    def test_a_text_too_short_to_decide_answers_nothing(self) -> None:
        assert detect_language("Le prix") is None

    def test_a_tie_answers_nothing(self) -> None:
        # Two languages score the same: picking one would be a coin flip.
        assert detect_language("la de la de la de la de") is None

    def test_a_text_without_any_stop_word_answers_nothing(self) -> None:
        assert detect_language("Paris Berlin Madrid Rome Lisbonne Vienne") is None

    def test_the_answer_is_never_a_probability(self) -> None:
        result = detect_language("Le fournisseur n'a pas confirmé le prix")

        assert isinstance(result, str)


class TestUnitTextAndFingerprint:
    """§17.1 — the fingerprint covers the source material, never the enrichment."""

    def test_the_text_of_a_record_is_its_values(self) -> None:
        unit = {
            "information_id": GOOD_ID,
            "content": {"values": {"city": "Paris", "population": "2145906"}},
        }
        text = unit_text(unit)

        assert "city=Paris" in text
        assert "population=2145906" in text

    def test_the_text_of_a_fragment_is_its_sentences(self) -> None:
        unit = {
            "information_id": GOOD_ID,
            "content": {"text": "Rapport", "sentences": ["La Seine traverse la ville."]},
        }

        assert "La Seine traverse la ville." in unit_text(unit)

    def test_an_empty_unit_has_no_text(self) -> None:
        assert unit_text({"information_id": GOOD_ID, "content": {}}) == ""

    def test_the_fingerprint_is_stable_and_source_based(self) -> None:
        unit = _unit(text="La Seine traverse la ville.")

        assert unit_fingerprint(unit) == unit_fingerprint(dict(unit))

    def test_the_fingerprint_ignores_the_enrichment_block(self) -> None:
        unit = _unit(text="La Seine traverse la ville.")
        enriched = {
            **unit,
            "data_stage": "enriched",
            "context": {
                **unit["context"],
                "enrichment": {"method": "Enricher.normalize", "values": [{"kind": "date"}]},
            },
        }

        assert unit_fingerprint(enriched) == unit_fingerprint(unit)

    def test_a_different_content_has_a_different_fingerprint(self) -> None:
        assert unit_fingerprint(_unit(text="Paris")) != unit_fingerprint(
            _unit(text="Berlin")
        )

    def test_a_unit_without_identifier_has_no_fingerprint(self) -> None:
        assert unit_fingerprint({"content": {"text": "Paris"}}) is None


class TestEnrichUnitsPromotesOnlyWhatItRead:
    """§12 — the step runs on the chain, and only on the chain."""

    def test_a_normalized_unit_is_promoted(self) -> None:
        outcome = enrich_units([_unit(text=FRENCH_TEXT)])

        assert outcome.enriched_ids == [GOOD_ID]
        assert outcome.units[0]["data_stage"] == "enriched"
        assert outcome.normalized_value_count == 2

    def test_the_original_text_is_never_rewritten(self) -> None:
        unit = _unit(text=FRENCH_TEXT)
        outcome = enrich_units([unit])

        assert outcome.units[0]["content"] == unit["content"]

    def test_the_input_units_are_not_mutated(self) -> None:
        unit = _unit(text=FRENCH_TEXT)
        enrich_units([unit])

        assert unit["data_stage"] == "normalized"
        assert "enrichment" not in unit["context"]

    def test_the_enrichment_block_states_the_method_and_the_values(self) -> None:
        outcome = enrich_units([_unit(text=FRENCH_TEXT)])
        block = outcome.units[0]["context"]["enrichment"]

        assert block["method"] == "Enricher.normalize"
        assert block["data_stage"] == "enriched"
        assert block["not_a_probability"] is True
        assert {value["kind"] for value in block["values"]} == {"date", "measure"}
        assert block["values"][0]["raw"] in FRENCH_TEXT

    def test_a_raw_unit_is_refused_rather_than_jumped(self) -> None:
        outcome = enrich_units([_unit(text="15/01/2024, 12 kilos", data_stage="raw")])

        assert outcome.units == ()
        assert outcome.enriched_ids == []
        assert outcome.skipped[0]["reason"] == "stage_jump_refused"
        assert any("raw" in line for line in outcome.limitations)
        assert outcome.lineage() is None

    def test_an_enriched_unit_is_left_alone(self) -> None:
        outcome = enrich_units([_unit(text="15/01/2024", data_stage="enriched")])

        assert outcome.units == ()
        assert outcome.skipped[0]["reason"] == "already_enriched"

    def test_a_derived_unit_is_left_alone(self) -> None:
        outcome = enrich_units([_unit(text="15/01/2024", data_stage="derived")])

        assert outcome.units == ()
        assert outcome.skipped[0]["reason"] == "stage_jump_refused"

    def test_a_unit_with_nothing_to_read_is_named_and_skipped(self) -> None:
        outcome = enrich_units([_unit(text="")])

        assert outcome.units == ()
        assert outcome.skipped[0]["reason"] == "nothing_to_enrich"

    def test_running_twice_changes_nothing_the_second_time(self) -> None:
        first = enrich_units([_unit(text=FRENCH_TEXT)])
        second = enrich_units(first.units)

        assert second.units == ()
        assert second.enriched_ids == []


class TestEnrichUnitsStatesWhatItCouldNotRead:
    """§0.2/§37 — a gap is stated, never filled with a plausible value."""

    def test_a_declared_language_decides_the_convention(self) -> None:
        outcome = enrich_units([_unit(text="le 03/04/2024", language="fr-FR")])
        value = outcome.reports[0].values[0]

        assert value.value["iso"] == "2024-04-03"
        assert value.value["locale"] == "fr-FR"

    def test_a_detected_language_decides_the_convention(self) -> None:
        outcome = enrich_units([_unit(text="Le fournisseur a livré le 03/04/2024 au client")])
        value = outcome.reports[0].values[0]

        assert outcome.reports[0].language == "fr"
        assert value.value["iso"] == "2024-04-03"

    def test_the_policy_locale_is_the_last_resort(self) -> None:
        policy = LanguagePolicy(normalization_locale="en-US")
        outcome = enrich_units([_unit(text="shipment of 03/04/2024 done")], policy=policy)
        value = outcome.reports[0].values[0]

        # Nothing declares (or shows) a language here: the policy locale is the
        # stated convention, and the report says which one was used.
        assert outcome.reports[0].language is None
        assert value.value["locale"] == "en-US"
        assert value.value["order"] == "MDY"
        assert value.value["iso"] == "2024-03-04"

    def test_an_ambiguous_symbol_is_reported_as_unresolved(self) -> None:
        outcome = enrich_units([_unit(text="The budget is $500 for the project")])

        assert outcome.unresolved[0]["kind"] == "currency"
        assert outcome.unresolved[0]["information_id"] == GOOD_ID
        assert any("devise" in line for line in outcome.limitations)

    def test_an_unreadable_number_is_reported_as_unresolved(self) -> None:
        outcome = enrich_units(
            [_unit(text="le stock est passé à 3.5 metres", language="fr-FR")]
        )

        assert outcome.unresolved[0]["kind"] == "measure"
        assert outcome.unresolved[0]["raw"] == "3.5 metres"

    def test_an_unknown_locale_reports_the_short_dates_it_cannot_order(self) -> None:
        outcome = enrich_units(
            [_unit(text="The shipment of 03/04/2024 was late", language="xx-YY")],
            locale="xx-YY",
        )

        assert outcome.unresolved[0]["kind"] == "date"

    def test_a_duplicate_is_named_rather_than_dropped(self) -> None:
        outcome = enrich_units(
            [
                _unit(text="Le fournisseur a livré 12 kilos de café"),
                _unit(information_id=OTHER_ID, text="Le fournisseur a livré 12 kilos de café"),
            ]
        )

        assert outcome.duplicates == ((OTHER_ID, GOOD_ID),)
        assert outcome.enriched_ids == [GOOD_ID, OTHER_ID]
        assert outcome.reports[1].duplicate_of == GOOD_ID
        assert any("doublon" in line for line in outcome.limitations)

    def test_the_report_and_the_outcome_agree(self) -> None:
        outcome = enrich_units([_unit(text=FRENCH_TEXT)])

        assert isinstance(outcome, EnrichmentOutcome)
        assert isinstance(outcome.reports[0], EnrichedUnit)
        assert outcome.lineage() is not None
        assert outcome.lineage()["unit_ids"] == [GOOD_ID]
        assert outcome.lineage()["values"] == outcome.normalized_value_count
        assert outcome.lineage()["languages"] == {"fr": 1}


class TestDatasetsExposeTheStageOfTheirUnits:
    """§12 — a dataset has no stage of its own: its units do."""

    def test_a_dataset_whose_row_was_enriched_is_enriched(self) -> None:
        unit = {**_unit(text=FRENCH_TEXT), "dataset_id": "DATA_01M3Q0000000000000000000AA"}
        outcome = enrich_units([unit])
        datasets = [{"dataset_id": "DATA_01M3Q0000000000000000000AA"}]

        stamped = resolved_dataset_stages(outcome.units, datasets)

        assert stamped[0]["data_stage"] == "enriched"

    def test_a_dataset_with_nothing_to_normalise_stays_normalized(self) -> None:
        unit = {
            **_unit(text="city=Berlin"),
            "dataset_id": "DATA_01M3Q0000000000000000000AA",
        }

        stamped = resolved_dataset_stages([unit], [{"dataset_id": "DATA_01M3Q0000000000000000000AA"}])

        assert stamped[0]["data_stage"] == "normalized"

    def test_a_dataset_with_no_unit_in_the_colis_keeps_the_default(self) -> None:
        stamped = resolved_dataset_stages(
            [], [{"dataset_id": "DATA_01M3Q0000000000000000000AA"}]
        )

        assert stamped[0]["data_stage"] == "normalized"

    def test_the_furthest_stage_of_the_units_wins(self) -> None:
        dataset_id = "DATA_01M3Q0000000000000000000AA"
        units = [
            {**_unit(text=FRENCH_TEXT), "dataset_id": dataset_id, "data_stage": "enriched"},
            {**_unit(text=FRENCH_TEXT), "dataset_id": dataset_id, "data_stage": "derived"},
        ]

        stamped = resolved_dataset_stages(units, [{"dataset_id": dataset_id}])

        assert stamped[0]["data_stage"] == "derived"

    def test_the_original_dataset_mapping_is_not_mutated(self) -> None:
        dataset = {"dataset_id": "DATA_01M3Q0000000000000000000AA"}

        resolved_dataset_stages([], [dataset])

        assert "data_stage" not in dataset
