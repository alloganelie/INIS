"""Compatibility shim over :mod:`app.storage.repositories.source_repository`.

The §9 persistence moved to the storage layer, where SQLAlchemy belongs
(CODING_RULES §2). This module keeps the historical import path used by the
API routers and the test suite, and nothing else.
"""

from __future__ import annotations

from app.storage.repositories.source_repository import (
    SourceRepository,
    get_database_engine,
    set_database_engine,
    sources_table,
    to_source_response,
)

__all__ = [
    "SourceRepository",
    "get_database_engine",
    "set_database_engine",
    "sources_table",
    "to_source_response",
]

