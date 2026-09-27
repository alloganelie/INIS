"""Vector search using pgvector per §16.1."""

import time
from typing import List, Tuple, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.storage.database.engine import create_engine_or_none


class VectorSearch:
    """Vector search using pgvector cosine similarity."""

    def __init__(self, connection_string: str) -> None:
        """Initialize the vector search.

        Args:
            connection_string: PostgreSQL connection string.
        """
        self._connection_string = connection_string
        self._engine: Optional[AsyncEngine] = None

    async def _get_engine(self) -> Optional[AsyncEngine]:
        """Get or create the async engine. Returns None in degraded mode."""
        if self._engine is None:
            self._engine = create_engine_or_none(self._connection_string)
        return self._engine

    async def search(
        self,
        owner_type: str,
        query_vector: List[float],
        limit: int = 10,
    ) -> List[Tuple[str, float]]:
        """Search for similar vectors using cosine similarity.

        Args:
            owner_type: Type of the owner (e.g., 'information_unit').
            query_vector: Query vector for similarity search.
            limit: Maximum number of results to return.

        Returns:
            List of (owner_id, score) tuples sorted by score descending.
        """
        engine = await self._get_engine()
        if engine is None:
            # Degraded mode: return empty list
            return []

        # Convert vector to PostgreSQL array format
        vector_str = "[" + ",".join(map(str, query_vector)) + "]"

        started = time.perf_counter()
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                "SELECT owner_id, 1 - (vector <=> CAST(:query_vector AS vector)) AS score "
                "FROM embeddings "
                "WHERE owner_type = :owner_type "
                "ORDER BY vector <=> CAST(:query_vector AS vector) "
                "LIMIT :limit"
                ),
                {
                    "query_vector": vector_str,
                    "owner_type": owner_type,
                    "limit": limit,
                },
            )
            rows = result.fetchall()
        # §34 — feed vector_search_latency (milliseconds).
        try:
            from app.observability.metrics import observe_value

            observe_value("vector_search_latency", (time.perf_counter() - started) * 1000.0)
        except Exception:  # noqa: BLE001 - observability never breaks search
            pass
        return [(row[0], float(row[1])) for row in rows]

