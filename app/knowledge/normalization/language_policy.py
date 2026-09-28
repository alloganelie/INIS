"""Language policy and per-unit translation metadata per §41.3.

The spec lists four ``[CONFIG]`` rules and requires every ``InformationUnit``
to carry a translation fingerprint:

``working_language``, ``source_languages_allowed``,
``translation_policy`` (``never`` | ``on_demand`` | ``always``) and
``normalization_locale``.

This module implements exactly that:

* :class:`LanguagePolicy` validates the configuration and decides whether a
  source language may be consumed and whether translation is required.
* :class:`TranslationMetadata` is the block every ``InformationUnit`` must
  carry, including the ``TRF_{ULID}`` transformation id when a translation was
  actually applied (§12 traceability + §0.2 provenance).
* BCP-47 tags are validated without any external dependency.

No I/O: the language layer is pure and unit-testable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from typing import Literal

#: The three translation policies of §41.3.
TranslationPolicy = Literal["never", "on_demand", "always"]

TRANSLATION_POLICIES: tuple[str, ...] = ("never", "on_demand", "always")

#: Conservative BCP-47 shape: ``ll`` / ``ll-CC`` / ``ll-Script`` /
#: ``ll-Script-CC`` / ``ll-Script-CC-Variant``.
_BCP47_RE = re.compile(
    r"^[A-Za-z]{2,3}(?:-[A-Za-z]{4})?(?:-(?:[A-Za-z]{2}|\d{3}))?(?:-[A-Za-z0-9]{2,8})*$"
)

#: Locales whose decimal separator is a comma (§41.3 normalization_locale).
COMMA_DECIMAL_LOCALES: frozenset[str] = frozenset(
    {"fr", "de", "es", "it", "pt", "nl", "pl", "tr", "ru", "id", "vi"}
)


class InvalidLanguage(ValueError):
    """Raised when a language tag is not a valid BCP-47 identifier."""


def validate_bcp47(tag: str) -> str:
    """Validate and canonicalise a BCP-47 language tag.

    Returns the canonical form: lowercase language, titlecase script,
    uppercase region (e.g. ``en-us`` → ``en-US``).

    Raises:
        InvalidLanguage: if *tag* is not a valid BCP-47 identifier.
    """
    if not isinstance(tag, str) or not tag.strip():
        raise InvalidLanguage("language tag must be a non-empty string")
    candidate = tag.strip().replace("_", "-")
    if not _BCP47_RE.match(candidate):
        raise InvalidLanguage(f"'{tag}' is not a valid BCP-47 language tag")

    parts = candidate.split("-")
    canonical = [parts[0].lower()]
    for part in parts[1:]:
        if len(part) == 4 and part.isalpha():
            canonical.append(part.title())
        elif len(part) == 2 and part.isalpha():
            canonical.append(part.upper())
        else:
            canonical.append(part.lower())
    return "-".join(canonical)


def language_base(tag: str) -> str:
    """Return the primary language subtag (``fr-CA`` → ``fr``)."""
    return validate_bcp47(tag).split("-", 1)[0]


@dataclass(frozen=True)
class LanguagePolicy:
    """Per-request language configuration (§41.3 ``[CONFIG]``)."""

    working_language: str = "en"
    source_languages_allowed: tuple[str, ...] = ("en", "fr", "es", "de")
    translation_policy: TranslationPolicy = "on_demand"
    normalization_locale: str = "en-US"

    def __post_init__(self) -> None:
        validate_bcp47(self.working_language)
        validate_bcp47(self.normalization_locale)
        if self.translation_policy not in TRANSLATION_POLICIES:
            raise ValueError(
                f"translation_policy must be one of {TRANSLATION_POLICIES}, "
                f"got '{self.translation_policy}'"
            )
        # Canonicalise the configuration so later comparisons stay exact.
        object.__setattr__(self, "working_language", validate_bcp47(self.working_language))
        object.__setattr__(
            self, "normalization_locale", validate_bcp47(self.normalization_locale)
        )
        object.__setattr__(
            self,
            "source_languages_allowed",
            tuple(validate_bcp47(tag) for tag in self.source_languages_allowed),
        )

    def allows(self, source_language: str) -> bool:
        """Return whether *source_language* may be consumed at all."""
        tag = validate_bcp47(source_language)
        if tag in self.source_languages_allowed:
            return True
        return language_base(tag) in {language_base(a) for a in self.source_languages_allowed}

    def is_working_language(self, source_language: str) -> bool:
        """Return whether *source_language* already matches the working one."""
        if not self.allows(source_language):
            return False
        tag = validate_bcp47(source_language)
        return language_base(tag) == language_base(self.working_language)

    def requires_translation(
        self,
        source_language: str,
        *,
        consumer_needs_working: bool = True,
    ) -> bool:
        """Resolve the policy for one concrete unit.

        * ``never`` — never translate.
        * ``always`` — translate every non-working-language source.
        * ``on_demand`` — translate only when the consumer actually needs the
          working language (``consumer_needs_working``).

        A language outside ``source_languages_allowed`` is never translated:
        it must be rejected upstream, not silently translated.
        """
        if not self.allows(source_language) or self.is_working_language(source_language):
            return False
        if self.translation_policy == "always":
            return True
        if self.translation_policy == "on_demand":
            return consumer_needs_working
        return False

    def normalize_number(self, raw: str) -> str:
        """Normalize a decimal string to the configured locale (§41.3).

        ``"1.234,5"`` → ``"1234.5"`` in canonical form, rendered with a comma
        when ``normalization_locale`` is a comma-decimal locale.
        """
        text = raw.strip().replace(" ", "").replace(" ", "").replace(" ", "")
        if "," in text and "." in text:
            # Whichever separator comes last is the decimal separator.
            if text.rfind(",") > text.rfind("."):
                text = text.replace(".", "").replace(",", ".")
            else:
                text = text.replace(",", "")
        elif "," in text:
            text = text.replace(",", ".")
        if language_base(self.normalization_locale) in COMMA_DECIMAL_LOCALES:
            return text.replace(".", ",")
        return text

    def to_dict(self) -> dict[str, Any]:
        """Return the §41.3 ``[CONFIG]`` block."""
        return {
            "working_language": self.working_language,
            "source_languages_allowed": list(self.source_languages_allowed),
            "translation_policy": self.translation_policy,
            "normalization_locale": self.normalization_locale,
        }


@dataclass(frozen=True)
class TranslationMetadata:
    """The §41.3 block every ``InformationUnit`` must carry.

    When a translation was actually applied, ``translation_model`` and
    ``translation_transformation_id`` are mandatory: the unit is a *derived*
    value and must reference the ``TRF_{ULID}`` transformation that produced
    it (§12.1, §0.2).
    """

    source_language: str
    normalized_language: str
    translation_applied: bool = False
    translation_model: str | None = None
    translation_transformation_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_language", validate_bcp47(self.source_language))
        object.__setattr__(
            self, "normalized_language", validate_bcp47(self.normalized_language)
        )
        if self.translation_applied:
            if not self.translation_model:
                raise ValueError(
                    "translation_applied requires a translation_model (§41.3)"
                )
            if not self.translation_transformation_id:
                raise ValueError(
                    "translation_applied requires a translation_transformation_id (§41.3)"
                )
            # A translated unit is derived: it must reference a real
            # TRF_{ULID} transformation (§0.3, §12.1, §41.3).
            from app.domain.value_objects.ulid import ULID

            if not ULID.is_valid(str(self.translation_transformation_id)) or not str(
                self.translation_transformation_id
            ).startswith("TRF_"):
                raise ValueError(
                    "translation_transformation_id must be a TRF_{ULID} (§0.3, §41.3)"
                )

    def to_dict(self) -> dict[str, Any]:
        """Return the §41.3 ``InformationUnit`` language block."""
        return {
            "source_language": self.source_language,
            "normalized_language": self.normalized_language,
            "translation_applied": self.translation_applied,
            "translation_model": self.translation_model,
            "translation_transformation_id": self.translation_transformation_id,
        }


def build_translation_metadata(
    policy: LanguagePolicy,
    source_language: str,
    *,
    translated: bool = False,
    translation_model: str | None = None,
    transformation_id: str | None = None,
) -> TranslationMetadata:
    """Build the metadata block of one unit according to *policy*.

    ``translated`` must only be ``True`` when a translation really happened;
    when the policy requires one but none was performed, the block is built
    with ``translation_applied=False`` and the *source* language so the gap is
    visible in the delivery instead of being hidden.
    """
    source = validate_bcp47(source_language)
    if not translated:
        return TranslationMetadata(
            source_language=source,
            normalized_language=source,
            translation_applied=False,
        )
    return TranslationMetadata(
        source_language=source,
        normalized_language=policy.working_language,
        translation_applied=True,
        translation_model=translation_model or "unknown-model",
        translation_transformation_id=transformation_id or "TRF_UNKNOWN",
    )
