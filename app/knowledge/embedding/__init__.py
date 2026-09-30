"""§16.1 — the embeddings of a colis, produced by a traced model or not at all."""

from app.knowledge.embedding.embeddings_generator import (
    EMBEDDING_DIMENSION,
    EMBEDDING_OWNER_TYPE,
    EmbeddingOutcome,
    EmbeddingRecord,
    generate_embeddings,
    persist_embeddings,
    vector_literal,
)

__all__ = [
    "EMBEDDING_DIMENSION",
    "EMBEDDING_OWNER_TYPE",
    "EmbeddingOutcome",
    "EmbeddingRecord",
    "generate_embeddings",
    "persist_embeddings",
    "vector_literal",
]
