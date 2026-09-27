"""INIS internal tools — §21 surface.

The 35 §21 tool signatures are exported from this package. Imports are lazy
(:pep:`562`) so ``import app.tools`` stays cheap and never pulls optional
readers (openpyxl, pdfplumber, ...) or triggers import cycles; each name is
resolved from its sub-package on first access::

    from app.tools import read_csv, check_permission

Sub-packages:

* :mod:`app.tools.files` — readers, dataset analysis, quality checks
* :mod:`app.tools.web` — ``web_search``, ``open_url``, ``follow_link``
* :mod:`app.tools.database` — ``postgres_query`` (read-only)
* :mod:`app.tools.images` — ``extract_image_content``
* :mod:`app.tools.knowledge` — fragment/vector/hybrid retrieval
* :mod:`app.tools.storage_tools` — ``store_source``/``store_information``/``store_evidence``
* :mod:`app.tools.agent_tools` — discovery (§6) and envelopes (§5)
* :mod:`app.tools.governance_tools` — permissions, classification, versioning, audit
"""

from importlib import import_module
from typing import Any

from app.tools.registry import ToolRegistry

#: §21 tool name -> defining sub-module.
_TOOL_MODULES: dict[str, str] = {
    # web
    "web_search": "app.tools.web",
    "open_url": "app.tools.web",
    "follow_link": "app.tools.web",
    # database
    "postgres_query": "app.tools.database",
    # files / datasets / quality
    "read_csv": "app.tools.files",
    "read_excel": "app.tools.files",
    "read_json": "app.tools.files",
    "read_xml": "app.tools.files",
    "read_pdf": "app.tools.files",
    "extract_document": "app.tools.files",
    "inspect_schema": "app.tools.files",
    "profile_dataset": "app.tools.files",
    "detect_duplicates": "app.tools.files",
    "validate_schema": "app.tools.files",
    "check_missing_values": "app.tools.files",
    "check_consistency": "app.tools.files",
    "check_freshness": "app.tools.files",
    "compare_sources": "app.tools.files",
    # images
    "extract_image_content": "app.tools.images",
    # knowledge retrieval
    "locate_fragment": "app.tools.knowledge",
    "vector_search": "app.tools.knowledge",
    "hybrid_search": "app.tools.knowledge",
    "retrieve_context": "app.tools.knowledge",
    # storage
    "store_source": "app.tools.storage_tools",
    "store_information": "app.tools.storage_tools",
    "store_evidence": "app.tools.storage_tools",
    # agent cooperation
    "discover_agents": "app.tools.agent_tools",
    "query_agent_capabilities": "app.tools.agent_tools",
    "send_agent_request": "app.tools.agent_tools",
    "receive_agent_result": "app.tools.agent_tools",
    # governance
    "check_permission": "app.tools.governance_tools",
    "classify_sensitivity": "app.tools.governance_tools",
    "create_version": "app.tools.governance_tools",
    "archive_record": "app.tools.governance_tools",
    "write_audit_event": "app.tools.governance_tools",
}

__all__ = ["ToolRegistry", *_TOOL_MODULES]


def __getattr__(name: str) -> Any:
    """Resolve a §21 tool from its sub-package on first access (PEP 562)."""
    module_name = _TOOL_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(__all__)

