"""Sentence-aware text chunking for downstream knowledge processing."""

import re


class ChunkSplitter:
    """Split text into bounded chunks while retaining whole-sentence overlap."""

    def split(self, text: str, max_tokens: int = 512, overlap: int = 64) -> list[str]:
        """Return sentence-aware chunks containing at most *max_tokens* words each."""
        if max_tokens <= 0:
            raise ValueError("max_tokens must be greater than zero")
        if overlap < 0:
            raise ValueError("overlap must be non-negative")
        effective_overlap = min(overlap, max_tokens - 1)

        sentences = self._sentences(text)
        if not sentences:
            return []

        chunks: list[list[str]] = []
        current_chunk: list[str] = []
        for sentence in sentences:
            bounded_sentence = self._truncate_sentence(sentence, max_tokens)
            if self._token_count(current_chunk) + self._token_count([bounded_sentence]) <= max_tokens:
                current_chunk.append(bounded_sentence)
                continue

            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = self._overlap_sentences(chunks[-1], effective_overlap)
            if self._token_count(current_chunk) + self._token_count([bounded_sentence]) > max_tokens:
                current_chunk = []
            current_chunk.append(bounded_sentence)

        if current_chunk:
            chunks.append(current_chunk)

        return [" ".join(chunk) for chunk in chunks]

    @staticmethod
    def _sentences(text: str) -> list[str]:
        """Extract non-empty sentence strings without requiring a tokenizer dependency."""
        return [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", text.strip()) if sentence]

    @staticmethod
    def _token_count(sentences: list[str]) -> int:
        """Count whitespace-delimited tokens without a tokenizer dependency."""
        return sum(len(sentence.split()) for sentence in sentences)

    @staticmethod
    def _overlap_sentences(sentences: list[str], overlap: int) -> list[str]:
        """Keep complete trailing sentences whose total size fits the overlap budget."""
        selected: list[str] = []
        token_count = 0
        for sentence in reversed(sentences):
            sentence_tokens = len(sentence.split())
            if token_count + sentence_tokens > overlap:
                break
            selected.insert(0, sentence)
            token_count += sentence_tokens
        return selected

    @staticmethod
    def _truncate_sentence(sentence: str, max_tokens: int) -> str:
        """Bound one long sentence and make the loss explicit with an ellipsis marker."""
        tokens = sentence.split()
        if len(tokens) <= max_tokens:
            return sentence
        if max_tokens == 1:
            return "…"
        return f"{' '.join(tokens[: max_tokens - 1])} …"
