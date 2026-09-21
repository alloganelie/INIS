"""Produce traceable raw InformationUnit payloads from source text."""

from typing import Any

from app.domain.value_objects.ulid import ULID
from app.knowledge.extraction.sentence_splitter import split_sentences


class FactExtractor:
    """Extract one factual raw information payload for each source sentence."""

    async def extract(
        self, text: str, source_id: str, document_id: str, url: str
    ) -> list[dict[str, Any]]:
        """Return source-backed factual information units extracted from *text*.

        Both source and document identifiers are required so every returned
        factual unit satisfies the provenance invariant.
        """
        if not source_id or not source_id.strip():
            raise ValueError("source_id is required for factual extraction")
        if not document_id or not document_id.strip():
            raise ValueError("document_id is required for factual extraction")

        return [
            {
                "information_id": ULID.new("INF_"),
                "type": "text",
                "content": {"text": sentence},
                "source_id": source_id,
                "document_id": document_id,
                "raw_reference": {"url": url, "excerpt": sentence[:200]},
                "data_stage": "raw",
                "epistemic_status": "factual",
                "evidence_id": ULID.new("EVID_"),
                "provenance": {
                    "extracted_from": url,
                    "method": "fact_extractor",
                },
            }
            for sentence in split_sentences(text)
        ]
