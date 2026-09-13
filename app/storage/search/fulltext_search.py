"""Full-text search using PostgreSQL tsvector."""

from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncEngine

from app.storage.database.engine import create_engine


class FullTextSearch:
    """Full-text search using PostgreSQL tsvector."""

    def __init__(self, connection_string: str) -> None:
        """Initialize the full-text search.

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
        limit: int = 10,
    ) -> List[dict]:
        """Search using full-text search on tsvector.

        Args:
            query: Text query for full-text search.
            limit: Maximum number of results to return.

        Returns:
            List of results with owner_id and score.
        """
        engine = await self._get_engine()
        if engine is None:
            # Degraded mode: return empty list
            return []

        async with engine.connect() as conn:
            result = await conn.execute(
                "SELECT id AS owner_id, ts_rank(search_vector, plainto_tsquery($1)) AS score "
                "FROM information_units "
                "WHERE search_vector @@ plainto_tsquery($1) "
                "ORDER BY score DESC "
                "LIMIT $2",
                query,
                limit,
            )
            rows = result.fetchall()
            return [{"owner_id": row[0], "score": float(row[1])} for row in rows]
