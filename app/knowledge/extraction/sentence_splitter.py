"""Sentence splitting utilities for source text extraction."""

import re


_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s*")
_MIN_SENTENCE_LENGTH = 20
_MAX_SENTENCES = 50


def split_sentences(text: str) -> list[str]:
    """Split *text* into meaningful sentences for fact extraction.

    Short fragments are treated as noise and the result is capped to protect
    downstream extraction from unusually large documents.
    """
    if not text:
        return []

    sentences = (sentence.strip() for sentence in _SENTENCE_BOUNDARY.split(text))
    return [
        sentence
        for sentence in sentences
        if len(sentence) >= _MIN_SENTENCE_LENGTH
    ][:_MAX_SENTENCES]
