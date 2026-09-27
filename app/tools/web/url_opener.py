"""``open_url`` internal tool per §21.

Fetches a Web page and returns the §21 :class:`Document` envelope. The literal
page text and the extractor metadata are returned alongside it by
:func:`open_url_content`, so the caller never re-downloads the page.

The transport is injectable: the pipeline passes its own ``httpx.AsyncClient``
(and the §41.8 circuit breaker) while tests inject an ``httpx.MockTransport``.
A network failure raises :class:`~app.core.errors.InfrastructureError`; INIS
never substitutes an empty document for an unreachable page (§0.2, §25.1).
"""

from __future__ import annotations

from typing import Any

import httpx

from app.connectors.web.extractors.trafilatura_extractor import TrafilaturaExtractor
from app.core.errors import InfrastructureError, ValidationError
from app.core.hashing import sha256_hex
from app.domain.entities.document import Document
from app.domain.value_objects.ulid import ULID

__all__ = ["open_url", "open_url_content", "source_id_for_url"]

#: Schemes the Web tools are allowed to fetch (§23: no local file or data URI).
ALLOWED_SCHEMES = frozenset({"http", "https"})

#: Default request timeout in seconds.
DEFAULT_TIMEOUT = 20.0


def source_id_for_url(url: str) -> str:
    """Return a stable, clearly-derived source identifier for *url*.

    The value matches the placeholder convention already used by the request
    pipeline (``URL:<url>``, truncated to the 64-character identifier budget).
    It is deliberately **not** a ``SRC_{ULID}``: the canonical §0.3 identifier
    is minted by ``store_source`` once the source is actually persisted, and
    minting one here would let an unpersisted source masquerade as a stored one.
    """
    return f"URL:{url}"[:64]


def _require_fetchable(url: str, label: str = "url") -> str:
    """Validate that *url* is an absolute HTTP(S) URL."""
    if not isinstance(url, str) or not url.strip():
        raise ValidationError(f"{label} must be a non-empty string")
    parsed = httpx.URL(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise ValidationError(
            f"{label} scheme {parsed.scheme!r} is not allowed "
            f"(expected one of {sorted(ALLOWED_SCHEMES)})"
        )
    if not parsed.host:
        raise ValidationError(f"{label} must be an absolute URL with a host")
    return str(parsed)


async def open_url_content(
    url: str,
    *,
    source_id: str | None = None,
    client: httpx.AsyncClient | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    extractor: TrafilaturaExtractor | None = None,
) -> tuple[Document, str, dict[str, Any]]:
    """Fetch *url* and return its document envelope, text and metadata.

    Args:
        url: Absolute ``http``/``https`` URL to fetch.
        source_id: Identifier of the owning source; defaulted to
            :func:`source_id_for_url` when omitted.
        client: Optional pre-configured ``httpx.AsyncClient``.
        timeout: Request timeout in seconds.
        extractor: Page-text extractor; a default one is built when omitted.

    Returns:
        ``(document, text, metadata)`` where metadata is the extractor contract
        (``title``, ``author``, ``date``, ``language``, ``error``…).

    Raises:
        ValidationError: If *url* is not an absolute HTTP(S) URL.
        InfrastructureError: If the request fails, returns a non-2xx status, or
            the page cannot be decoded.
    """
    target = _require_fetchable(url)

    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=timeout, follow_redirects=True)
    try:
        try:
            response = await active_client.get(target)
        except httpx.HTTPError as exc:
            raise InfrastructureError(f"could not fetch {target}: {exc}") from exc
        if response.status_code >= 400:
            raise InfrastructureError(
                f"could not fetch {target}: HTTP {response.status_code}"
            )
        html = response.text
    finally:
        if owns_client:
            await active_client.aclose()

    active_extractor = extractor or TrafilaturaExtractor()
    metadata = await active_extractor.extract(html, target)
    text = str(metadata.get("text") or "")

    document = Document(
        document_id=ULID.new("DOC_"),
        source_id=source_id or source_id_for_url(target),
        mime_type=response.headers.get("content-type", "text/html").split(";")[0].strip(),
        content_hash=sha256_hex(html),
        storage_ref=target,
    )
    return document, text, metadata


async def open_url(
    url: str,
    *,
    source_id: str | None = None,
    client: httpx.AsyncClient | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Document:
    """Return the §21 ``Document`` envelope of the page at *url*."""
    document, _text, _metadata = await open_url_content(
        url, source_id=source_id, client=client, timeout=timeout
    )
    return document
