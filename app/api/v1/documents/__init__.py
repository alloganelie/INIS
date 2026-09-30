"""§9.1 document ingestion endpoints (§32)."""

from app.api.v1.documents.router import documents_router, router

__all__ = ["documents_router", "router"]
