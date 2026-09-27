"""``follow_link`` internal tool per §21.

Follows a link discovered in a page. Unlike :func:`~app.tools.web.url_opener.open_url`,
this tool resolves a possibly *relative* href against the page that contains it
and refuses any scheme other than ``http``/``https`` before a request is made,
so a ``javascript:``, ``mailto:`` or ``file:`` link can never turn into a fetch
(§23: no arbitrary code execution, no local resource access).
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.errors import ValidationError
from app.domain.entities.document import Document
from app.tools.web.url_opener import (
    ALLOWED_SCHEMES,
    DEFAULT_TIMEOUT,
    open_url_content,
)

__all__ = ["follow_link", "follow_link_content", "resolve_link"]


def resolve_link(href: str, base_url: str) -> str:
    """Resolve *href* against *base_url* and validate its scheme.

    Args:
        href: Link target, absolute or relative.
        base_url: URL of the page the link was found on.

    Returns:
        The absolute, fetchable URL.

    Raises:
        ValidationError: If the resolved scheme is not ``http``/``https``, which
            is the explicit refusal required before any network call is made.
    """
    if not isinstance(href, str) or not href.strip():
        raise ValidationError("href must be a non-empty string")
    if not isinstance(base_url, str) or not base_url.strip():
        raise ValidationError("base_url must be a non-empty string")

    try:
        target = httpx.URL(base_url).join(href.strip())
    except (httpx.InvalidURL, ValueError) as exc:
        raise ValidationError(f"could not resolve link {href!r}: {exc}") from exc

    if target.scheme not in ALLOWED_SCHEMES:
        raise ValidationError(
            f"refusing to follow {target.scheme!r} link: "
            f"only {sorted(ALLOWED_SCHEMES)} are fetchable"
        )
    if not target.host:
        raise ValidationError(f"resolved link has no host: {target}")
    return str(target)


async def follow_link_content(
    url: str,
    *,
    base_url: str | None = None,
    source_id: str | None = None,
    client: httpx.AsyncClient | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[Document, str, dict[str, Any]]:
    """Follow *url* and return its document envelope, text and metadata.

    Args:
        url: Link target; may be relative when *base_url* is supplied.
        base_url: URL of the page the link was found on.
        source_id: Identifier of the owning source.
        client: Optional pre-configured ``httpx.AsyncClient``.
        timeout: Request timeout in seconds.

    Returns:
        ``(document, text, metadata)``.
    """
    target = resolve_link(url, base_url) if base_url else url
    return await open_url_content(
        target, source_id=source_id, client=client, timeout=timeout
    )


async def follow_link(
    url: str,
    *,
    base_url: str | None = None,
    source_id: str | None = None,
    client: httpx.AsyncClient | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Document:
    """Return the §21 ``Document`` envelope of the followed link."""
    document, _text, _metadata = await follow_link_content(
        url,
        base_url=base_url,
        source_id=source_id,
        client=client,
        timeout=timeout,
    )
    return document
