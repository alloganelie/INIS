"""§12/§16/§17.1 — enrich §11 units without ever inventing a value.

The lifecycle of §12 is a **chain**:

.. code-block:: text

    raw -> normalized -> enriched -> derived

Before this module, every produced unit was stamped ``raw`` whatever had
happened to it, the ``enriched`` stage only ever carried the synthesis of a run,
and nothing normalised a date, a measurement, a currency amount or a language:
two units saying the same thing in two notations stayed two unrelated
fingerprints (C11/C12, plan §4 L3.1).

What this module does — and only this:

* it **normalises notation**, never content: ``15/01/2024`` becomes
  ``2024-01-15`` *in addition to* the original span, ``12 kilos`` becomes
  ``{"value": 12.0, "unit": "kg"}``, ``1 234,50 €`` becomes
  ``{"value": 1234.5, "currency": "EUR"}``. The unit's own text is never
  rewritten, and no conversion is performed (``kg`` is not turned into ``lb``);
* it **detects the language** of a unit with a documented stop-word heuristic.
  When the evidence is not conclusive the answer is ``None``, never a guess —
  §0.2 and §37 both prefer a stated gap to an invented fact;
* it **fingerprints** every unit (``record_hash`` of source + document +
  location + content) and names the exact duplicates it found (§17.1) instead
  of silently dropping them: a dropped unit loses its provenance, a named one
  does not;
* it **refuses a stage jump**. A unit still at ``raw`` is *not* promoted to
  ``enriched``: :func:`advance_stage` only accepts the next stage of §12, so
  the gap stays visible and is counted in the limitations.

No I/O, no database, no LLM: this layer is pure and unit-testable, and the
pipeline is what decides to apply its result (see ``pipeline_runner``).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from app.core.constants import DATA_STAGES
from app.core.errors import ValidationError
from app.core.hashing import canonical_json, record_hash
from app.knowledge.normalization.language_policy import (
    COMMA_DECIMAL_LOCALES,
    LanguagePolicy,
    language_base,
)

__all__ = [
    "DATA_STAGES",
    "STAGE_ORDER",
    "EnrichedUnit",
    "EnrichmentOutcome",
    "NormalizedValue",
    "StageTransitionError",
    "advance_stage",
    "can_transition",
    "detect_language",
    "enrich_units",
    "normalize_currencies",
    "normalize_dates",
    "normalize_measures",
    "resolved_dataset_stages",
    "unit_fingerprint",
    "unit_text",
]

#: The §12 stages, in order. Re-exported so callers do not re-declare them.
STAGE_ORDER: tuple[str, ...] = tuple(DATA_STAGES)


class StageTransitionError(ValidationError):
    """Raised when a unit would jump over a §12 stage."""


def can_transition(current: str | None, target: str | None) -> bool:
    """Return whether *current* → *target* is exactly one §12 stage step.

    A jump (``raw`` → ``enriched``, ``raw`` → ``derived``), a step backwards
    (``derived`` → ``normalized``) and an unknown stage are all refused: the
    lifecycle of §12 has four ordered stages and no shortcut.
    """
    origin = str(current or "").strip().lower()
    destination = str(target or "").strip().lower()
    if origin not in STAGE_ORDER or destination not in STAGE_ORDER:
        return False
    return STAGE_ORDER.index(destination) == STAGE_ORDER.index(origin) + 1


def advance_stage(current: str | None, target: str, *, context: str = "") -> str:
    """Return *target* when it is the next §12 stage after *current*.

    Args:
        current: The stage the unit is at.
        target: The stage the caller wants to move it to.
        context: Optional label (an ``information_id``) for the error message.

    Returns:
        The normalised *target* stage.

    Raises:
        StageTransitionError: If the transition is not a single §12 step.
    """
    if not can_transition(current, target):
        where = f" ({context})" if context else ""
        raise StageTransitionError(
            f"Transition d'étape §12 refusée{where} : « {current} » → « {target} » "
            f"n'est pas l'étape suivante de {list(STAGE_ORDER)} — un saut d'étape "
            "n'est jamais enregistré (§0.2)."
        )
    return str(target).strip().lower()


@dataclass(frozen=True)
class NormalizedValue:
    """One value whose notation was normalised, with the span it came from.

    ``start``/``end`` are the offsets of the original text inside the analysed
    unit text, so the delivery can always point back at what was read.
    """

    kind: Literal["date", "measure", "currency"]
    raw: str
    value: dict[str, Any]
    start: int
    end: int

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON block carried by the enriched unit."""
        return {
            "kind": self.kind,
            "raw": self.raw,
            "value": dict(self.value),
            "offset": self.start,
            "length": self.end - self.start,
        }


@dataclass(frozen=True)
class EnrichedUnit:
    """The enrichment report of one unit (never the unit's content itself)."""

    information_id: str
    data_stage: str
    language: str | None
    locale: str | None = None
    values: tuple[NormalizedValue, ...] = ()
    fingerprint: str | None = None
    duplicate_of: str | None = None
    unresolved: tuple[dict[str, Any], ...] = ()

    def annotation(self) -> dict[str, Any]:
        """Return the ``context["enrichment"]`` block of an enriched unit.

        It states the stage change that really happened, the method used and
        every value that was normalised — plus what could not be, so a reader
        never has to guess what was skipped (§37).
        """
        return {
            "data_stage": self.data_stage,
            "method": "Enricher.normalize",
            "language": self.language,
            "language_method": "stopword-ratio" if self.language else None,
            "locale": self.locale,
            "not_a_probability": True,
            "values": [item.to_dict() for item in self.values],
            "fingerprint": self.fingerprint,
            "duplicate_of": self.duplicate_of,
            "unresolved": [dict(item) for item in self.unresolved],
        }


@dataclass(frozen=True)
class EnrichmentOutcome:
    """What the enricher did to a collection of units.

    ``units`` holds **copies** of the enriched units (original fields plus the
    ``context["enrichment"]`` block and the new ``data_stage``); the caller
    decides what to do with them. ``skipped`` names every unit that was left
    untouched and why — a refusal is a result, not a silence.
    """

    units: tuple[dict[str, Any], ...] = ()
    reports: tuple[EnrichedUnit, ...] = ()
    skipped: tuple[dict[str, Any], ...] = ()
    duplicates: tuple[tuple[str, str], ...] = ()
    unresolved: tuple[dict[str, Any], ...] = ()
    limitations: tuple[str, ...] = ()

    @property
    def enriched_ids(self) -> list[str]:
        """Return the ``information_id`` of every unit that was promoted."""
        return [report.information_id for report in self.reports]

    @property
    def normalized_value_count(self) -> int:
        """Return how many values were normalised in total."""
        return sum(len(report.values) for report in self.reports)

    @property
    def languages(self) -> dict[str, int]:
        """Return the languages detected, with the number of units each covers."""
        counts: dict[str, int] = {}
        for report in self.reports:
            if report.language:
                counts[report.language] = counts.get(report.language, 0) + 1
        return counts

    def lineage(self) -> dict[str, Any] | None:
        """Return the §12.1 parameters of the enrichment step, or ``None``.

        ``None`` means the step produced nothing: a stage that changed no unit
        must not appear in the lineage as if it had run (§0.2).
        """
        if not self.reports:
            return None
        return {
            "unit_ids": self.enriched_ids,
            "values": self.normalized_value_count,
            "languages": self.languages,
            "locales": sorted({report.locale for report in self.reports if report.locale}),
            "duplicates": len(self.duplicates),
            "unresolved": len(self.unresolved),
        }


def _ascii(text: str) -> str:
    """Return *text* lowercased and stripped of its diacritics (for lookups)."""
    decomposed = unicodedata.normalize("NFKD", str(text).lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _locale_decimal_separator(locale: str) -> str:
    """Return the decimal separator of *locale* (comma for the FR/DE family)."""
    try:
        base = language_base(locale)
    except Exception:  # noqa: BLE001 - an unusable locale falls back to the strict set
        base = str(locale or "").split("-", 1)[0].lower()
    return "," if base in COMMA_DECIMAL_LOCALES else "."


#: One numeric token: digits, with spaces (incl. NBSP/narrow NBSP), dot or comma
#: as separators. Kept deliberately narrow so ``v1.2.3`` is not read as a number.
_NUMBER_TOKEN_RE = re.compile(r"[+-]?\d[\d\u00a0\u202f .,]*\d|[+-]?\d")

#: Locale month names accepted in a textual date (English and French, §41.3).
_MONTH_NAMES: dict[str, int] = {
    "january": 1, "janvier": 1, "jan": 1,
    "february": 2, "fevrier": 2, "feb": 2, "fev": 2,
    "march": 3, "mars": 3, "mar": 3,
    "april": 4, "avril": 4, "apr": 4, "avr": 4,
    "may": 5, "mai": 5,
    "june": 6, "juin": 6, "jun": 6,
    "july": 7, "juillet": 7, "jul": 7,
    "august": 8, "aout": 8, "aug": 8,
    "september": 9, "septembre": 9, "sep": 9, "sept": 9,
    "october": 10, "octobre": 10, "oct": 10,
    "november": 11, "novembre": 11, "nov": 11,
    "december": 12, "decembre": 12, "dec": 12,
}

_MONTH_ALTERNATION = "|".join(sorted(_MONTH_NAMES, key=len, reverse=True))

#: ``2024-01-15`` / ``2024/01/15`` — order year/month/day, unambiguous.
_YMD_RE = re.compile(r"(?<!\d)(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?!\d)")

#: ``15/01/2024`` / ``15.01.2024`` / ``01/15/2024`` — order decided by the locale.
_NUMERIC_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})(?!\d)")

#: ``15 January 2024`` / ``15 janvier 2024`` / ``January 15, 2024``.
_TEXT_DATE_DMY_RE = re.compile(
    rf"(?<!\w)(\d{{1,2}})\s+({_MONTH_ALTERNATION})\s+(\d{{4}})(?!\d)", re.IGNORECASE
)
_TEXT_DATE_MDY_RE = re.compile(
    rf"(?<!\w)({_MONTH_ALTERNATION})\.?\s+(\d{{1,2}}),?\s+(\d{{4}})(?!\d)", re.IGNORECASE
)

#: Languages whose short numeric dates are written month-first (``M/D/Y``).
MONTH_FIRST_LANGUAGES: frozenset[str] = frozenset({"en"})

#: Month-first languages that are in fact day-first in their country convention.
MONTH_FIRST_LOCALE_EXCEPTIONS: frozenset[str] = frozenset(
    {"en-GB", "en-AU", "en-NZ", "en-IE", "en-IN", "en-SG", "en-HK", "en-ZA"}
)

#: Languages whose short numeric dates are written day-first (``D/M/Y``).
DAY_FIRST_LANGUAGES: frozenset[str] = COMMA_DECIMAL_LOCALES | frozenset(
    {"en-GB", "en-AU", "en-NZ", "en-IE", "el", "cs", "ro", "hu", "uk", "sv", "da", "no", "fi"}
)


def validate_locale_shape(tag: str) -> str:
    """Return the locale in canonical ``ll-CC`` shape without raising.

    Only used to look a locale up in :data:`MONTH_FIRST_LOCALE_EXCEPTIONS`; an
    unparsable tag keeps its raw lowercase form, which simply will not match.
    """
    parts = str(tag or "").replace("_", "-").split("-")
    if not parts or not parts[0]:
        return ""
    if len(parts) == 1:
        return parts[0].lower()
    return f"{parts[0].lower()}-{parts[1].upper()}"


def _date_order(locale: str) -> str | None:
    """Return ``"DMY"``, ``"MDY"`` or ``None`` for an unknown *locale*.

    ``None`` is a real answer: when the locale does not tell how ``03/04/2024``
    must be read, the value is **not** normalised (§0.2). Guessing here would
    turn a date into its neighbour for half the world.
    """
    candidate = str(locale or "").replace("_", "-").strip()
    try:
        canonical = language_base(candidate)
    except Exception:  # noqa: BLE001 - an unknown tag is simply not usable
        return None
    if canonical in DAY_FIRST_LANGUAGES:
        return "DMY"
    if canonical in MONTH_FIRST_LANGUAGES:
        if validate_locale_shape(candidate) in MONTH_FIRST_LOCALE_EXCEPTIONS:
            return "DMY"
        return "MDY"
    return None


def _valid_grouping(body: str, separator: str, decimal_char: str | None) -> bool:
    """Return whether *separator* is used as a thousands separator in *body*.

    A group separator must sit between digit groups of three (the first group
    being 1 to 3 digits): ``1,234`` and ``1 234 567`` are grouped numbers, while
    ``3.5`` under a comma-decimal locale is not — it would have to be read as
    ``35``, which is exactly the kind of silent reinterpretation §0.2 forbids.
    """
    integer_part = body.partition(decimal_char)[0] if decimal_char else body
    groups = integer_part.split(separator)
    if not all(group.isdigit() for group in groups):
        return False
    return all(len(group) == 3 for group in groups[1:])


def _parse_number(token: str, *, locale: str) -> float | int | None:
    """Return *token* as a number under *locale*, or ``None`` when ambiguous.

    The declared locale decides: in ``fr-FR`` ``1,5`` is one and a half and
    ``1.5`` is fifteen hundred; in ``en-US`` it is the other way round. A token
    with **both** separators needs no locale at all — the rightmost one is the
    decimal separator, as in ``1.234,56`` and ``1,234.56``. When the token
    cannot be read under those rules (``1.2.3``, a lone ``-``) the answer is
    ``None`` — never a reinterpretation.
    """
    raw = str(token).strip()
    if not raw or not any(char.isdigit() for char in raw):
        return None
    sign = -1 if raw.startswith("-") else 1
    body = re.sub(r"[\u00a0\u202f ]", "", raw.lstrip("+-"))
    decimal_separator = _locale_decimal_separator(locale)
    dots, commas = body.count("."), body.count(",")
    if dots and commas:
        decimal_char = "." if body.rfind(".") > body.rfind(",") else ","
        other = "," if decimal_char == "." else "."
        if not _valid_grouping(body, other, decimal_char):
            return None
        integer_part, _, fractional = body.replace(other, "").partition(decimal_char)
    elif dots or commas:
        char = "." if dots else ","
        if body.count(char) > 1:
            return None
        if char == decimal_separator:
            integer_part, _, fractional = body.partition(char)
        else:
            # A group separator: ``1,234`` under en-US is the integer 1234.
            if not _valid_grouping(body, char, None):
                return None
            integer_part, fractional = body.replace(char, ""), ""
    else:
        integer_part, fractional = body, ""
    if not integer_part.isdigit() or (bool(fractional) and not fractional.isdigit()):
        return None
    if fractional:
        return sign * float(f"{integer_part}.{fractional}")
    return sign * int(integer_part)


def _expand_year(year: int) -> int:
    """Expand a two-digit *year* the way ISO 8601 recommends (69–99 → 19xx)."""
    if year >= 100:
        return year
    return 2000 + year if year <= 68 else 1900 + year


def _iso_date(year: int, month: int, day: int) -> str | None:
    """Return the ISO form of a calendar date, or ``None`` when it is invalid."""
    try:
        return date(_expand_year(year), month, day).isoformat()
    except ValueError:
        return None


def _overlaps(used: list[tuple[int, int]], start: int, end: int) -> bool:
    """Return whether ``[start, end)`` intersects a span already normalised."""
    return any(start < other_end and other_start < end for other_start, other_end in used)


def normalize_dates(text: str, *, locale: str = "en-US") -> list[NormalizedValue]:
    """Return the dates of *text* in ISO 8601, or none when unreadable.

    Three shapes are recognised: an unambiguous ``YYYY-MM-DD`` (or ``YYYY/MM/DD``),
    a textual date (``15 January 2024``, ``15 janvier 2024``, ``January 15, 2024``),
    and a short numeric date (``15/01/2024``) whose order comes **only** from the
    declared locale. An invalid calendar date (``2024-02-31``) and an ambiguous
    short date in an unknown locale produce nothing rather than a plausible
    neighbour (§0.2).
    """
    found: list[NormalizedValue] = []
    used: list[tuple[int, int]] = []

    def _add(start: int, end: int, iso: str, order: str, raw: str) -> None:
        used.append((start, end))
        found.append(
            NormalizedValue(
                kind="date",
                raw=raw,
                value={"iso": iso, "precision": "day", "order": order, "locale": locale},
                start=start,
                end=end,
            )
        )

    for match in _YMD_RE.finditer(text):
        iso = _iso_date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if iso:
            _add(match.start(), match.end(), iso, "YMD", match.group(0))

    for pattern, order in ((_TEXT_DATE_DMY_RE, "DMY"), (_TEXT_DATE_MDY_RE, "MDY")):
        for match in pattern.finditer(text):
            if _overlaps(used, match.start(), match.end()):
                continue
            first, second = match.group(1), match.group(2)
            day, month = (first, second) if order == "DMY" else (second, first)
            month_number = _MONTH_NAMES.get(_ascii(month))
            if month_number is None or not str(day).isdigit():
                continue
            iso = _iso_date(int(match.group(3)), month_number, int(day))
            if iso:
                _add(match.start(), match.end(), iso, order, match.group(0))

    order_hint = _date_order(locale)
    for match in _NUMERIC_DATE_RE.finditer(text):
        if _overlaps(used, match.start(), match.end()) or order_hint is None:
            continue
        first, second, year = match.group(1), match.group(2), int(match.group(3))
        day, month = (first, second) if order_hint == "DMY" else (second, first)
        iso = _iso_date(year, int(month), int(day))
        if iso:
            _add(match.start(), match.end(), iso, order_hint, match.group(0))

    return found


#: Canonical measurement units: alias (lowercase, no accent) → (symbol, dimension).
#: Notation only — no conversion is ever performed here (§12: a value is not
#: reinterpreted, and ``kg`` is never silently turned into ``lb``).
MEASURE_UNITS: dict[str, tuple[str, str]] = {}


def _declare(dimension: str, symbol: str, *aliases: str) -> None:
    """Register *symbol* and its *aliases* under *dimension*."""
    for alias in (symbol, *aliases):
        MEASURE_UNITS[_ascii(alias)] = (symbol, dimension)


_declare("length", "m", "metre", "metres", "meter", "meters", "mètre", "mètres")
_declare("length", "km", "kilometre", "kilometres", "kilometer", "kilometers",
         "kilomètre", "kilomètres")
_declare("length", "cm", "centimetre", "centimetres", "centimeter", "centimeters",
         "centimètre", "centimètres")
_declare("length", "mm", "millimetre", "millimetres", "millimeter", "millimeters",
         "millimètre", "millimètres")
_declare("length", "mi", "mile", "miles", "milles")
_declare("mass", "kg", "kilo", "kilos", "kilogramme", "kilogrammes", "kilogram",
         "kilograms")
_declare("mass", "g", "gramme", "grammes", "gram", "grams")
_declare("mass", "mg", "milligramme", "milligrammes", "milligram", "milligrams")
_declare("mass", "t", "tonne", "tonnes", "ton", "tons")
_declare("volume", "l", "litre", "litres", "liter", "liters")
_declare("volume", "ml", "millilitre", "millilitres", "milliliter", "milliliters")
_declare("time", "s", "seconde", "secondes", "second", "seconds")
_declare("time", "min", "minute", "minutes")
_declare("time", "h", "heure", "heures", "hour", "hours")
_declare("surface", "m2", "m²", "square metre", "square meter", "metre carre",
         "metres carres")
_declare("volume", "m3", "m³", "cubic metre", "cubic meter", "metre cube")
_declare("speed", "km/h", "kmh", "kilometre par heure", "kilometres par heure")
_declare("energy", "kWh", "kilowattheure", "kilowattheures", "kilowatt-hour")
_declare("ratio", "%", "pourcent", "pourcents", "percent", "percents")
_declare("temperature", "°C", "celsius", "degré celsius", "degres celsius")
_declare("temperature", "°F", "fahrenheit", "degré fahrenheit", "degres fahrenheit")

#: Longest alias first: ``km/h`` must win over ``km``, ``kg`` over ``g``.
_UNIT_ALTERNATION = "|".join(
    re.escape(alias) for alias in sorted(MEASURE_UNITS, key=len, reverse=True)
)
_NUMBER_PATTERN = r"[+-]?\d[\d\u00a0\u202f .,]*\d|[+-]?\d"
_MEASURE_RE = re.compile(
    rf"(?P<number>{_NUMBER_PATTERN})\s*(?P<unit>{_UNIT_ALTERNATION})(?![a-z])",
    re.IGNORECASE,
)


def normalize_measures(text: str, *, locale: str = "en-US") -> list[NormalizedValue]:
    """Return the measurements of *text* with their canonical unit symbol.

    Only a number **immediately followed by a known unit** is normalised: the
    alias is replaced by its symbol (``kilos`` → ``kg``, ``kilomètres`` → ``km``)
    and the dimension is stated. No conversion is performed and an unknown unit
    (``12 stones``) is left untouched: inventing an equivalence would be a fact
    this module has no source for.
    """
    found: list[NormalizedValue] = []
    for match in _MEASURE_RE.finditer(text):
        number = _parse_number(match.group("number"), locale=locale)
        entry = MEASURE_UNITS.get(_ascii(match.group("unit")))
        if number is None or entry is None:
            continue
        symbol, dimension = entry
        found.append(
            NormalizedValue(
                kind="measure",
                raw=match.group(0),
                value={
                    "value": number,
                    "unit": symbol,
                    "dimension": dimension,
                    "locale": locale,
                },
                start=match.start(),
                end=match.end(),
            )
        )
    return found


#: Currency symbols that name exactly one ISO 4217 code.
CURRENCY_SYMBOLS: dict[str, str] = {
    "€": "EUR",
    "£": "GBP",
    "¥": "JPY",
    "₹": "INR",
    "₣": "CHF",
    "₽": "RUB",
    "₩": "KRW",
}

#: ISO 4217 codes accepted in a unit's text.
CURRENCY_CODES: frozenset[str] = frozenset(
    {
        "EUR", "USD", "GBP", "CHF", "JPY", "CAD", "AUD", "CNY", "INR", "BRL",
        "SEK", "NOK", "DKK", "PLN", "ZAR", "MAD", "TND", "DZD", "XOF", "XAF",
    }
)

#: Symbols that name several currencies: ``$`` alone is never resolved (§0.2).
AMBIGUOUS_CURRENCY_SYMBOLS: frozenset[str] = frozenset({"$", "元", "kr"})

_CURRENCY_ALTERNATION = "|".join(
    [re.escape(symbol) for symbol in CURRENCY_SYMBOLS]
    + [re.escape(symbol) for symbol in sorted(AMBIGUOUS_CURRENCY_SYMBOLS, key=len, reverse=True)]
    + [code for code in sorted(CURRENCY_CODES)]
)
_AMOUNT_AFTER_RE = re.compile(
    rf"(?P<number>{_NUMBER_PATTERN})\s*(?P<currency>{_CURRENCY_ALTERNATION})(?![A-Za-z])"
)
_AMOUNT_BEFORE_RE = re.compile(
    rf"(?<![A-Za-z])(?P<currency>{_CURRENCY_ALTERNATION})\s*(?P<number>{_NUMBER_PATTERN})"
)


def normalize_currencies(text: str, *, locale: str = "en-US") -> list[NormalizedValue]:
    """Return the currency amounts of *text*, in both notations (``€12`` → ``12 €``).

    Only a symbol or code that names **one** currency is normalised. ``$`` is
    deliberately not: it stands for USD, CAD, AUD and a dozen others, and
    choosing one would be an invention (§0.2). The amount is not converted:
    ``{"value": 1234.5, "currency": "EUR"}`` is the amount as written.
    """
    found: list[NormalizedValue] = []
    used: list[tuple[int, int]] = []
    for pattern, currency_first in ((_AMOUNT_AFTER_RE, False), (_AMOUNT_BEFORE_RE, True)):
        for match in pattern.finditer(text):
            if _overlaps(used, match.start(), match.end()):
                continue
            token = str(match.group("currency"))
            code = CURRENCY_SYMBOLS.get(token) or (
                token.upper() if token.upper() in CURRENCY_CODES else None
            )
            if code is None:
                # An ambiguous symbol is never resolved here; ``enrich_units``
                # reports it as unresolved instead.
                continue
            number = _parse_number(match.group("number"), locale=locale)
            if number is None:
                continue
            used.append((match.start(), match.end()))
            found.append(
                NormalizedValue(
                    kind="currency",
                    raw=match.group(0),
                    value={
                        "value": number,
                        "currency": code,
                        "locale": locale,
                        "order": "symbol_first" if currency_first else "amount_first",
                    },
                    start=match.start(),
                    end=match.end(),
                )
            )
    return found


#: Stop words used by the language heuristic. Deliberately small and common:
#: the detector only has to separate the languages the policy allows, and it
#: answers ``None`` when it cannot (§41.3, §0.2).
STOPWORDS: dict[str, frozenset[str]] = {
    "en": frozenset(
        {"the", "and", "of", "to", "in", "is", "that", "it", "for", "was", "with",
         "as", "on", "are", "by", "this", "be", "from", "or", "an", "not", "which",
         "have", "has", "but", "at", "they", "their"}
    ),
    "fr": frozenset(
        {"le", "la", "les", "des", "de", "du", "et", "en", "un", "une", "est", "que",
         "qui", "pour", "dans", "sur", "au", "aux", "avec", "par", "ce", "cette",
         "ces", "il", "elle", "nous", "vous", "ils", "elles", "sont", "ne", "pas",
         "plus", "mais", "comme"}
    ),
    "es": frozenset(
        {"el", "la", "los", "las", "de", "del", "y", "en", "un", "una", "es", "que",
         "por", "para", "con", "no", "se", "su", "al", "como", "mas", "pero", "este",
         "esta", "son"}
    ),
    "de": frozenset(
        {"der", "die", "das", "und", "den", "von", "zu", "mit", "sich", "des", "auf",
         "fur", "ist", "im", "dem", "nicht", "ein", "eine", "als", "auch", "es", "an",
         "werden", "aus", "er", "hat", "dass", "sie"}
    ),
}

_WORD_RE = re.compile(r"[a-z]{2,}")


def detect_language(
    text: str,
    *,
    minimum_tokens: int = 4,
    minimum_matches: int = 2,
) -> str | None:
    """Return the detected BCP-47 base language of *text*, or ``None``.

    The heuristic counts the stop words of each supported language. It answers
    ``None`` when the text is too short (*minimum_tokens*), when no language
    reaches *minimum_matches*, or when two languages tie: a wrong language tag
    is worse than an absent one (§0.2), and the result is never a probability
    (§11: ``confidence`` stays out of it).
    """
    tokens = _WORD_RE.findall(_ascii(text))
    if len(tokens) < minimum_tokens:
        return None
    scores = {
        language: sum(1 for token in tokens if token in words)
        for language, words in STOPWORDS.items()
    }
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_language, best_score = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0
    if best_score < minimum_matches or best_score <= runner_up:
        return None
    return best_language


#: ``content`` keys read as text, in a fixed order so the result is stable.
_TEXT_KEYS: tuple[str, ...] = ("text", "sentence", "excerpt", "quote", "title")


def unit_text(unit: Mapping[str, Any]) -> str:
    """Return the analysable text of a §11 unit, deterministically.

    Only the **stored** content is read: the known text keys, the ``values`` of
    a record (``key=value``, sorted) and the ``sentences`` of a prose fragment.
    Nothing is completed, translated or paraphrased — an empty unit yields an
    empty string, and the enricher then finds nothing in it.
    """
    content = unit.get("content")
    content = content if isinstance(content, Mapping) else {}
    parts: list[str] = []
    for key in _TEXT_KEYS:
        value = content.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value)
    for key in ("values", "row"):
        mapping = content.get(key)
        if isinstance(mapping, Mapping):
            parts.extend(
                f"{name}={mapping[name]}"
                for name in sorted(mapping, key=str)
                if isinstance(mapping[name], (str, int, float))
                and str(mapping[name]).strip()
            )
    sentences = content.get("sentences")
    if isinstance(sentences, Sequence) and not isinstance(sentences, str):
        parts.extend(
            sentence
            for sentence in sentences
            if isinstance(sentence, str) and sentence.strip()
        )
    return " ; ".join(dict.fromkeys(parts))


def unit_fingerprint(unit: Mapping[str, Any]) -> str | None:
    """Return the §17.1 fingerprint of a unit, or ``None`` without an id.

    The digest covers the **source material** — source, document, dataset,
    location and content — never the enrichment block: fingerprinting the
    enrichment would make a unit a stranger to itself after it was enriched.
    """
    if not unit.get("information_id"):
        return None
    return record_hash(
        {
            "source_id": unit.get("source_id"),
            "document_id": unit.get("document_id"),
            "dataset_id": unit.get("dataset_id"),
            "location": unit.get("location") or {},
            "content": unit.get("content") or {},
        }
    )


def _unresolved_currency(text: str) -> list[dict[str, Any]]:
    """Return the ``$``-style amounts that were deliberately not resolved.

    Both notations are looked for — ``500 $`` and ``$500`` — because the gap is
    the same in each: the symbol names several currencies and this module has no
    source to choose between them, so it states the amount it left alone instead
    of silently finding nothing.
    """
    alternation = "|".join(
        re.escape(symbol) for symbol in sorted(AMBIGUOUS_CURRENCY_SYMBOLS, key=len, reverse=True)
    )
    symbol = f"(?P<symbol>{alternation})"
    matches = [
        match
        for pattern in (
            rf"(?:{_NUMBER_PATTERN})\s*{symbol}",
            rf"{symbol}\s*(?:{_NUMBER_PATTERN})",
        )
        for match in re.finditer(pattern, text)
    ]
    found: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    for match in sorted(matches, key=lambda item: item.start()):
        if (match.start(), match.end()) in seen:
            continue
        seen.add((match.start(), match.end()))
        found.append(
            {
                "kind": "currency",
                "raw": match.group(0),
                "reason": (
                    f"symbole « {match.group('symbol')} » ambigu (plusieurs devises "
                    "possibles) : aucune devise n'est inventée"
                ),
            }
        )
    return found


def _unresolved_numbers(text: str, *, locale: str) -> list[dict[str, Any]]:
    """Return the measurements whose number the declared locale cannot read."""
    return [
        {
            "kind": "measure",
            "raw": match.group(0),
            "reason": (
                f"nombre « {match.group('number')} » illisible en locale « {locale} » : "
                "la valeur n'est pas devinée (§0.2)"
            ),
        }
        for match in _MEASURE_RE.finditer(text)
        if _parse_number(match.group("number"), locale=locale) is None
    ]


def _unresolved_dates(text: str, *, locale: str) -> list[dict[str, Any]]:
    """Return the short numeric dates the declared locale cannot order."""
    if _date_order(locale) is not None:
        return []
    return [
        {
            "kind": "date",
            "raw": match.group(0),
            "reason": (
                f"locale « {locale} » sans convention jour/mois connue : "
                "aucune date n'est devinée (§0.2)"
            ),
        }
        for match in _NUMERIC_DATE_RE.finditer(text)
    ]


def _dedupe_values(values: Sequence[NormalizedValue]) -> list[NormalizedValue]:
    """Return *values* without the same value found twice in one unit text.

    A record carries its text twice (``values`` and the ``text`` built from
    them), so the same amount can be matched on both occurrences: only the
    canonical value counts, and the first span is kept.
    """
    seen: set[tuple[str, str]] = set()
    unique: list[NormalizedValue] = []
    for item in values:
        key = (item.kind, canonical_json(item.value))
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def resolved_dataset_stages(
    units: Sequence[Mapping[str, Any]],
    datasets: Sequence[Mapping[str, Any]],
    *,
    default: str = "normalized",
) -> list[dict[str, Any]]:
    """Return *datasets* stamped with the §12 stage their own units reached.

    A dataset has no stage of its own: what reaches a stage is the material read
    from it. The stage of a delivered dataset is therefore the **furthest** stage
    reached by its units — a dataset whose rows were enriched is ``enriched``, one
    whose rows had nothing to normalise stays ``normalized`` (the reader produced
    it, and nothing moved it further), and a dataset with no unit in the colis
    keeps *default* rather than claiming a stage that nothing proves (§0.2).
    """
    stages: dict[str, str] = {}
    for unit in units:
        if not isinstance(unit, Mapping):
            continue
        dataset_id = str(unit.get("dataset_id") or "")
        stage = str(unit.get("data_stage") or "").strip().lower()
        if not dataset_id or stage not in STAGE_ORDER:
            continue
        current = stages.get(dataset_id)
        if current is None or STAGE_ORDER.index(stage) > STAGE_ORDER.index(current):
            stages[dataset_id] = stage
    return [
        {
            **dict(dataset),
            "data_stage": stages.get(str(dataset.get("dataset_id") or ""), default),
        }
        for dataset in datasets
    ]


def enrich_units(
    units: Sequence[Mapping[str, Any]],
    *,
    policy: LanguagePolicy | None = None,
    locale: str | None = None,
) -> EnrichmentOutcome:
    """Enrich the §11 units that are ready for it — and only those.

    Args:
        units: The units of a run (or of a document), as §11 mappings.
        policy: The §41.3 language policy. Its ``normalization_locale`` is the
            convention applied to a unit that declares no language and shows
            none.
        locale: Explicit override of the policy locale (BCP-47).

    Returns:
        An :class:`EnrichmentOutcome`: a copy of every unit that was really
        promoted to ``enriched`` (with its ``context["enrichment"]`` block and
        its new ``data_stage``), the report of what was found, the duplicates,
        what could not be read, and the limitations that state it.

    A unit is promoted only when the enrichment found something: a detected
    language or at least one normalised value. A unit at ``raw`` is **refused**
    rather than jumped to ``enriched`` (§12), and a unit already at ``enriched``
    or downstream of it is left alone — the operation is idempotent.

    Each unit is read with the convention it announces: the language it declares,
    otherwise the one detected in it, otherwise the policy locale. One colis can
    therefore mix a French page read day-first and an English one read
    month-first without either being guessed.
    """
    active_policy = policy or LanguagePolicy()
    normalization_locale = locale or active_policy.normalization_locale
    produced: list[dict[str, Any]] = []
    reports: list[EnrichedUnit] = []
    skipped: list[dict[str, Any]] = []
    duplicates: list[tuple[str, str]] = []
    unresolved: list[dict[str, Any]] = []
    limitations: list[str] = []
    fingerprints: dict[str, str] = {}
    refused_stage = 0
    nothing_found = 0

    for unit in units:
        if not isinstance(unit, Mapping):
            continue
        information_id = str(unit.get("information_id") or "")
        current = str(unit.get("data_stage") or "raw").strip().lower()
        if current == "enriched":
            skipped.append({"information_id": information_id, "reason": "already_enriched"})
            continue
        if not can_transition(current, "enriched"):
            refused_stage += 1
            skipped.append(
                {
                    "information_id": information_id,
                    "reason": "stage_jump_refused",
                    "data_stage": current,
                }
            )
            continue

        text = unit_text(unit)
        declared = str(unit.get("language") or "").strip() or None
        detected = detect_language(text)
        language = declared or detected
        # §12/§0.2 — the unit's own language decides how its dates and decimals
        # are read; only a unit that declares (or shows) none falls back to the
        # policy locale. Reading a French ``15/01/2024`` as ``en-US`` would swap
        # the day and the month, which is exactly the reinterpretation refused.
        unit_locale = declared or detected or normalization_locale
        values = _dedupe_values(
            [
                *normalize_dates(text, locale=unit_locale),
                *normalize_measures(text, locale=unit_locale),
                *normalize_currencies(text, locale=unit_locale),
            ]
        )
        fingerprint = unit_fingerprint(unit)
        duplicate_of = fingerprints.get(fingerprint) if fingerprint else None
        if fingerprint and duplicate_of is None:
            fingerprints[fingerprint] = information_id
        if duplicate_of:
            duplicates.append((information_id, duplicate_of))

        if not values and language is None:
            nothing_found += 1
            skipped.append(
                {"information_id": information_id, "reason": "nothing_to_enrich"}
            )
            continue

        unit_unresolved = [
            *_unresolved_dates(text, locale=unit_locale),
            *_unresolved_numbers(text, locale=unit_locale),
            *_unresolved_currency(text),
        ]
        unresolved.extend(
            {"information_id": information_id, **item} for item in unit_unresolved
        )
        report = EnrichedUnit(
            information_id=information_id,
            data_stage="enriched",
            language=language,
            locale=unit_locale,
            values=tuple(values),
            fingerprint=fingerprint,
            duplicate_of=duplicate_of,
            unresolved=tuple(unit_unresolved),
        )
        enriched = dict(unit)
        enriched["data_stage"] = advance_stage(current, "enriched", context=information_id)
        if language and not enriched.get("language"):
            enriched["language"] = language
        context = enriched.get("context")
        context = dict(context) if isinstance(context, Mapping) else {}
        context["enrichment"] = report.annotation()
        enriched["context"] = context
        reports.append(report)
        produced.append(enriched)

    if refused_stage:
        limitations.append(
            f"{refused_stage} unité(s) §11 encore au stade « raw » n'ont pas été "
            "enrichies : le cycle §12 exige l'étape « normalized » d'abord, et un "
            "saut d'étape (raw → enriched) n'est jamais enregistré (§0.2)."
        )
    if duplicates:
        limitations.append(
            f"{len(duplicates)} doublon(s) exact(s) détecté(s) par empreinte (§17.1) : "
            "ils sont conservés et marqués « duplicate_of » plutôt que supprimés, "
            "pour ne pas perdre leur provenance."
        )
    if unresolved:
        limitations.append(
            f"{len(unresolved)} valeur(s) non normalisée(s) faute d'interprétation "
            "sûre (nombre illisible dans la locale déclarée, symbole de devise ambigu "
            "ou convention de date inconnue) : elles restent telles quelles, aucune "
            "n'est devinée (§0.2)."
        )
    if nothing_found and not produced:
        limitations.append(
            "Aucune unité §11 n'a été enrichie : leur contenu ne portait ni date, ni "
            "mesure, ni montant, ni langue détectable — l'étape « enriched » n'est "
            "donc pas revendiquée dans le lignage (§0.2)."
        )

    return EnrichmentOutcome(
        units=tuple(produced),
        reports=tuple(reports),
        skipped=tuple(skipped),
        duplicates=tuple(duplicates),
        unresolved=tuple(unresolved),
        limitations=tuple(limitations),
    )
