"""Extraction primitives for traceable knowledge acquisition."""

from app.knowledge.extraction.fact_extractor import FactExtractor
from app.knowledge.extraction.sentence_splitter import split_sentences

__all__ = ["FactExtractor", "split_sentences"]
