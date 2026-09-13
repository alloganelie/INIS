"""Hybrid search combining semantic and lexical search per §16.2."""

from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.storage.database.engine import create_engine


class HybridSearch:
    """Hybrid search combining pgvector and full-text search."""

    def __init__(self, connection_string: str) -> None:
        """Initialize the hybrid search.

        Args:
            connection_string: PostgreSQL connection string.
        """
        self._connection_string = connection_string
        self._engine: Optional[AsyncEngine] = None

    async def _get_engine(self) -> Optional[AsyncEngine]:
        """Get or create the async engine. Returns None in degraded mode."""
        if self._engine is None:
            try:
                self._engine = create_engine(self._connection_string)
            except Exception:
                # Degraded mode: engine not available
                return None
        return self._engine

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
        engine = await self._get_engine()
        if engine is None:
            # Degraded mode: return empty list
            return []

        # Convert vector to PostgreSQL array format
        vector_str = "[" + ",".join(map(str, query_vector)) + "]"

        async with engine.connect() as conn:
            result = await conn.execute(
                text("""WITH semantic AS (
                    SELECT owner_id, 1 - (vector <=> CAST(:query_vector AS vector)) AS score
                    FROM embeddings
                    WHERE owner_type = 'information_unit'
                    ORDER BY vector <=> CAST(:query_vector AS vector)
                    LIMIT :limit
                ),
                lexical AS (
                    SELECT id AS owner_id,
                           ts_rank(search_vector, plainto_tsquery(:query)) AS score
                    FROM information_units
                    WHERE search_vector @@ plainto_tsquery(:query)
                    LIMIT :limit
                )
                SELECT owner_id,
                       COALESCE(semantic.score, 0) * 0.6 +
                       COALESCE(lexical.score, 0) * 0.4 AS final_score
                FROM semantic
                FULL OUTER JOIN lexical USING (owner_id)
                ORDER BY final_score DESC
                LIMIT :limit"""),
                {"query_vector": vector_str, "query": query, "limit": limit},
            )
            rows = result.fetchall()
            return [{"owner_id": row[0], "final_score": float(row[1])} for row in rows]
