"""Synthetic / AI-generated content detection (§41.7).

Heuristic, dependency-free signals only — no external API calls:

1. Explicit generator metadata (``generator`` tag / ``generated_by``).
2. First-person AI boilerplate markers (FR / EN).
3. Stylometric uniformity: sentence lengths with suspiciously low variance.
4. Exact duplicate consecutive sentences.

The detector returns ``(detected, reason)`` so the caller can build the
``suspicion_reason`` field of the §41.7 ``source_suspicion`` block.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

#: Phrases commonly emitted by chatbots when they reveal themselves.
SYNTHETIC_MARKERS: tuple[str, ...] = (
    "as an ai",
    "as an artificial intelligence",
    "i cannot assist",
    "en tant qu'ia",
    "je suis un modèle de langage",
    "language model developed",
    "modèle de langage développé",
    "in conclusion,",
    "it is important to note that",
    "il convient de noter que",
    "dans cet article, nous verrons",
    "we will explore",
    "nous explorerons",
)

#: Minimum sentences required before stylometry is considered.
_MIN_SENTENCES = 4
#: Coefficient of variation of sentence length below which text is "uniform".
_UNIFORM_CV = 0.20
#: Minimum word count for stylometry to be meaningful.
_MIN_WORDS = 40

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_WORD_SPLIT = re.compile(r"\w+", re.UNICODE)


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(text.strip()) if s.strip()]


def detect_synthetic_content(
    text: str,
    *,
    metadata: Mapping[str, Any] | None = None,
) -> tuple[bool, str | None]:
    """Return ``(detected, reason)`` for a synthetic/AI-generated text (§41.7).

    Args:
        text: the source content to inspect.
        metadata: optional source metadata; a ``generator`` (or
            ``generated_by``) value flags the content immediately.
    """
    if metadata:
        generator = metadata.get("generator") or metadata.get("generated_by")
        if generator:
            return True, f"generator metadata declares {generator!r}"

    lowered = text.casefold()
    for marker in SYNTHETIC_MARKERS:
        if marker in lowered:
            return True, f"AI boilerplate marker {marker!r}"

    words = _WORD_SPLIT.findall(lowered)
    sentences = _sentences(text)
    if len(words) >= _MIN_WORDS and len(sentences) >= _MIN_SENTENCES:
        lengths = [len(_WORD_SPLIT.findall(s)) for s in sentences]
        mean = sum(lengths) / len(lengths)
        if mean > 0:
            variance = sum((n - mean) ** 2 for n in lengths) / len(lengths)
            cv = variance**0.5 / mean
            if cv < _UNIFORM_CV:
                return True, (
                    f"sentence-length uniformity (cv={cv:.2f} < {_UNIFORM_CV}) "
                    "typical of generated text"
                )

    for previous, current in zip(sentences, sentences[1:]):
        if previous and previous == current:
            return True, "identical consecutive sentences (template output)"

    return False, None
