"""Sentence-aware text chunking for downstream knowledge processing."""

import re


class ChunkSplitter:
    """Split text into bounded chunks while retaining trailing-token overlap."""

    def split(self, text: str, max_tokens: int = 512, overlap: int = 64) -> list[str]:
        """Return sentence-aware chunks containing at most *max_tokens* words each."""
        if max_tokens <= 0:
            raise ValueError("max_tokens must be greater than zero")
        if overlap < 0 or overlap >= max_tokens:
            raise ValueError("overlap must be non-negative and less than max_tokens")

        sentences = self._sentences(text)
        if not sentences:
            return []

        chunks: list[list[str]] = []
        current_chunk: list[str] = []
        for sentence in sentences:
            sentence_tokens = sentence.split()
            while sentence_tokens:
                remaining = max_tokens - len(current_chunk)
                if remaining == 0:
                    chunks.append(current_chunk)
                    current_chunk = current_chunk[-overlap:] if overlap else []
                    remaining = max_tokens - len(current_chunk)

                if len(sentence_tokens) <= remaining:
                    current_chunk.extend(sentence_tokens)
                    sentence_tokens = []
                else:
                    current_chunk.extend(sentence_tokens[:remaining])
                    sentence_tokens = sentence_tokens[remaining:]

        if current_chunk:
            chunks.append(current_chunk)

        return [" ".join(chunk) for chunk in chunks]

    @staticmethod
    def _sentences(text: str) -> list[str]:
        """Extract non-empty sentence strings without requiring a tokenizer dependency."""
        return [
            sentence.strip()
            for sentence in re.findall(r"[^.!?]+(?:[.!?]+|$)", text)
            if sentence.strip()
        ]
