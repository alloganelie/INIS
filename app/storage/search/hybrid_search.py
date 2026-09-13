"""Hybrid search combining semantic and lexical search per §16.2."""

from typing import List


class HybridSearch:
    """Hybrid search combining pgvector and full-text search."""

    def __init__(self, connection_string: str) -> None:
        """Initialize the hybrid search.

        Args:
            connection_string: PostgreSQL connection string.
        """
        self._connection_string = connection_string

    async def search(
        self,
        query: str,
        query_vector: List[float],
        limit: int = 10,
    ) -> List[dict]:
        """Search using hybrid semantic + lexical approach per §16.2.

        Args:
            query: Text query for lexical search.
            query_vector: Query vector for semantic search.
            limit: Maximum number of results to return.

        Returns:
            List of results with owner_id and final_score.
        """
        # Stub implementation - would use asyncpg to execute:
        # WITH semantic AS (
        #   SELECT owner_id, 1 - (vector <=> $1::vector) AS score
        #   FROM embeddings
        #   WHERE owner_type = $2
        #   ORDER BY vector <=> $1::vector
        #   LIMIT $3
        # ),
        # lexical AS (
        #   SELECT information_id AS owner_id,
        #          ts_rank(search_vector, plainto_tsquery($4)) AS score
        #   FROM information_units
        #   WHERE search_vector @@ plainto_tsquery($4)
        #   LIMIT $3
        # )
        # SELECT owner_id,
        #        COALESCE(semantic.score, 0) * 0.6 +
        #        COALESCE(lexical.score, 0) * 0.4 AS final_score
        # FROM semantic
        # FULL OUTER JOIN lexical USING (owner_id)
        # ORDER BY final_score DESC
        return []
