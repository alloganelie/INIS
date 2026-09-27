"""Web tools per §21: ``web_search``, ``open_url`` and ``follow_link``."""

from app.tools.web.link_follower import follow_link, follow_link_content, resolve_link
from app.tools.web.url_opener import open_url, open_url_content, source_id_for_url
from app.tools.web.web_search import web_search

__all__ = [
    "follow_link",
    "follow_link_content",
    "open_url",
    "open_url_content",
    "resolve_link",
    "source_id_for_url",
    "web_search",
]

