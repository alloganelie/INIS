"""Full-text search using PostgreSQL tsvector."""

from typing import List


class FullTextSearch:
    """Full-text search using PostgreSQL tsvector."""

    def __init__(self, connection_string: str) -> None:
        """Initialize the full-text search.

        Args:
            connection_string: PostgreSQL connection string.
        """
        self._connection_string = connection_string

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
        # Stub implementation - would use asyncpg to execute:
        # SELECT information_id AS owner_id,
        #        ts_rank(search_vector, plainto_tsquery($1)) AS score
        # FROM information_units
        # WHERE search_vector @@ plainto_tsquery($1)
        # ORDER BY score DESC
        # LIMIT $2
        return []
