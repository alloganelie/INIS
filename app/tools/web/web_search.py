"""``web_search`` internal tool per §21, backed by the provider router (§10.1).

The tool is a thin, stateless façade: it delegates ranking and provider
selection to :class:`~app.connectors.web.provider_router.ProviderRouter` and
never fabricates results. A failed provider call propagates
``InfrastructureError`` so the planner can degrade explicitly instead of
receiving an empty list that looks like "no result" (§0.2).
"""

from __future__ import annotations

from app.connectors.web.provider_router import ProviderRouter
from app.domain.entities.search_result import SearchResult

__all__ = ["web_search"]


async def web_search(
    query: str,
    limit: int = 5,
    *,
    router: ProviderRouter | None = None,
    provider_id: str | None = None,
) -> list[SearchResult]:
    """Return at most *limit* ranked results for *query* (§21 signature).

    Args:
        query: Non-empty search query.
        limit: Maximum number of results, strictly positive.
        router: Provider router to use; a default router (environment-selected
            provider) is built when omitted.
        provider_id: Optional explicit provider to resolve.

    Returns:
        The ranked search results, possibly empty when the provider found
        nothing.

    Raises:
        ValueError: If *query* is empty or *limit* is not positive.
        InfrastructureError: If the provider call fails.
    """
    if not query or not isinstance(query, str):
        raise ValueError("query must be a non-empty string")
    if limit < 1:
        raise ValueError("limit must be >= 1")
    active_router = router if router is not None else ProviderRouter()
    return await active_router.search(query, limit, provider_id=provider_id)

