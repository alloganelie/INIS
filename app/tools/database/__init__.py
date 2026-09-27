"""Database tools per §21: ``postgres_query`` (read-only)."""

from app.tools.database.postgres_query import assert_read_only, postgres_query

__all__ = ["assert_read_only", "postgres_query"]
