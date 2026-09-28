"""Knowledge retrieval tools per §21 and §16.

Public surface: :func:`locate_fragment`, :func:`vector_search`,
:func:`hybrid_search` and :func:`retrieve_context`.
"""

from app.tools.knowledge.fragment_locator import (
    lexical_overlap,
    locate_fragment,
    retrieve_context,
)
from app.tools.knowledge.hybrid_searcher import FILTER_COLUMNS, hybrid_search
from app.tools.knowledge.vector_searcher import OWNER_TYPE, vector_search

__all__ = [
    "FILTER_COLUMNS",
    "OWNER_TYPE",
    "hybrid_search",
    "lexical_overlap",
    "locate_fragment",
    "retrieve_context",
    "vector_search",
]
