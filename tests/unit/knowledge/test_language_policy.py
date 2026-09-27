"""Unit tests for the §41.3 language policy and translation metadata."""

import pytest

from app.knowledge.normalization.language_policy import (
    TRANSLATION_POLICIES,
    InvalidLanguage,
    LanguagePolicy,
    TranslationMetadata,
    build_translation_metadata,
    language_base,
    validate_bcp47,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("en", "en"), ("EN", "en"), ("en-us", "en-US"), ("fr_ca", "fr-CA"), ("zh-hans", "zh-Hans")],
)
def test_validate_bcp47_canonicalises_tags(raw: str, expected: str) -> None:
    assert validate_bcp47(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "e", "1234", "english-language-tag-too-long"])
def test_validate_bcp47_rejects_invalid_tags(raw: str) -> None:
    with pytest.raises(InvalidLanguage):
        validate_bcp47(raw)


def test_language_base_extracts_primary_subtag() -> None:
    assert language_base("fr-CA") == "fr"
    assert language_base("en") == "en"


def test_policy_canonicalises_its_configuration() -> None:
    policy = LanguagePolicy(
        working_language="en-us",
        source_languages_allowed=("FR", "de"),
        normalization_locale="fr-fr",
    )
    assert policy.working_language == "en-US"
    assert policy.source_languages_allowed == ("fr", "de")
    assert policy.normalization_locale == "fr-FR"


def test_policy_rejects_unknown_translation_policy() -> None:
    with pytest.raises(ValueError, match="translation_policy must be one of"):
        LanguagePolicy(translation_policy="sometimes")  # type: ignore[arg-type]


def test_policy_to_dict_exposes_the_config_block() -> None:
    payload = LanguagePolicy().to_dict()
    assert set(payload) == {
        "working_language",
        "source_languages_allowed",
        "translation_policy",
        "normalization_locale",
    }


def test_policy_allows_listed_languages_only() -> None:
    policy = LanguagePolicy(source_languages_allowed=("en", "fr"))
    assert policy.allows("fr-CA") is True  # base language match
    assert policy.allows("de") is False


def test_policy_never_translates_working_language() -> None:
    policy = LanguagePolicy(working_language="en", translation_policy="always")
    assert policy.requires_translation("en-GB") is False


def test_policy_always_translates_foreign_language() -> None:
    policy = LanguagePolicy(
        working_language="en", source_languages_allowed=("en", "fr"), translation_policy="always"
    )
    assert policy.requires_translation("fr") is True


def test_policy_never_translates_when_configured_never() -> None:
    policy = LanguagePolicy(
        working_language="en", source_languages_allowed=("en", "fr"), translation_policy="never"
    )
    assert policy.requires_translation("fr") is False


def test_policy_on_demand_respects_consumer_need() -> None:
    policy = LanguagePolicy(
        working_language="en", source_languages_allowed=("en", "fr"), translation_policy="on_demand"
    )
    assert policy.requires_translation("fr", consumer_needs_working=True) is True
    assert policy.requires_translation("fr", consumer_needs_working=False) is False


def test_policy_never_translates_disallowed_language() -> None:
    policy = LanguagePolicy(
        working_language="en", source_languages_allowed=("en",), translation_policy="always"
    )
    assert policy.requires_translation("de") is False


def test_translation_policies_are_the_three_from_spec() -> None:
    assert TRANSLATION_POLICIES == ("never", "on_demand", "always")


def test_normalize_number_handles_both_separators() -> None:
    en = LanguagePolicy(normalization_locale="en-US")
    assert en.normalize_number("1.234,5") == "1234.5"
    assert en.normalize_number("1,5") == "1.5"
    assert en.normalize_number("12") == "12"


def test_normalize_number_respects_comma_decimal_locale() -> None:
    fr = LanguagePolicy(normalization_locale="fr-FR")
    assert fr.normalize_number("1.5") == "1,5"
    assert fr.normalize_number("1.234,5") == "1234,5"


def test_translation_metadata_requires_model_when_applied() -> None:
    with pytest.raises(ValueError, match="translation_model"):
        TranslationMetadata(
            source_language="fr", normalized_language="en", translation_applied=True
        )


def test_translation_metadata_requires_trf_transformation_id() -> None:
    with pytest.raises(ValueError, match="translation_transformation_id"):
        TranslationMetadata(
            source_language="fr",
            normalized_language="en",
            translation_applied=True,
            translation_model="m-1",
        )


def test_translation_metadata_rejects_non_ulf_transformation_id() -> None:
    with pytest.raises(ValueError, match=r"TRF_\{ULID\}"):
        TranslationMetadata(
            source_language="fr",
            normalized_language="en",
            translation_applied=True,
            translation_model="m-1",
            translation_transformation_id="TRF_X",
        )


def test_translation_metadata_to_dict_has_the_spec_fields() -> None:
    meta = TranslationMetadata(source_language="fr-CA", normalized_language="en-US")
    assert meta.to_dict() == {
        "source_language": "fr-CA",
        "normalized_language": "en-US",
        "translation_applied": False,
        "translation_model": None,
        "translation_transformation_id": None,
    }


def test_build_metadata_without_translation_keeps_source_language() -> None:
    policy = LanguagePolicy(working_language="en")
    meta = build_translation_metadata(policy, "fr")
    assert meta.translation_applied is False
    assert meta.normalized_language == "fr"


def test_build_metadata_with_translation_sets_working_language() -> None:
    policy = LanguagePolicy(working_language="en")
    meta = build_translation_metadata(
        policy,
        "fr",
        translated=True,
        translation_model="opus-mt",
        transformation_id="TRF_01ARZ3NDEKTSV4RRFFQ69G5F01",
    )
    assert meta.translation_applied is True
    assert meta.normalized_language == "en"
    assert meta.translation_model == "opus-mt"
    assert meta.translation_transformation_id.startswith("TRF_")
