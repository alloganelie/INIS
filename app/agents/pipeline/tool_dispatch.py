"""Resolve a §8.4 plan action to the §21 tool that implements it (§8.4, §21, §25.2).

Two problems this module exists to solve.

**The registry was never populated.** The 35 tools of §21 are all implemented
(``app/tools/__init__.py`` resolves every name to a real callable — checked by
``tests/unit/agents/pipeline/test_tool_dispatch.py``), but nothing ever called
``ToolRegistry.register``: the tools were unreachable from a plan. This module
registers them and answers "which callable implements this name?".

**An action must be able to say it cannot run.** Before this module, the
acquisition loop looked at ``step["action"]``, ignored it, and searched the web
with the *action name* as the query — a ``file_ingest`` step became a web search
for the literal string ``file_ingest``, and a step that produced nothing was
replaced by invented text. :func:`describe_action` makes the honest answer
possible: which §21 tools an action needs, whether the pipeline can execute it
today, and if not, **why** — so a delivery can state a limitation instead of
inventing a result (§25.2, §37).

``file_ingest`` is executable since L2.3/L2.4: the pipeline re-reads the §11 units
of the documents already ingested for the request (``app.knowledge.ingestion.
request_material``). It stays *conditionally* executable — a request that ingested
no document cannot run it, and that case is named by :attr:`ActionSpec.reason`
instead of being turned into a web search.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.core.errors import InfrastructureError
from app.tools.registry import ToolRegistry

__all__ = [
    "ACTIONS",
    "WEB_TOOLS",
    "ActionSpec",
    "UnavailableTool",
    "default_registry",
    "describe_action",
    "is_web_action",
    "populate_registry",
    "registered_tools",
    "resolve",
    "unavailable_tools",
]

#: §21 tools that acquire over the network: the pipeline runs them through the
#: provider router (§9/§10) and its own cache, never as a bare registry call.
WEB_TOOLS: tuple[str, ...] = ("web_search", "open_url", "follow_link")


class UnavailableTool(InfrastructureError):
    """Raised when a plan names a tool that cannot be resolved (§25.2)."""


@dataclass(frozen=True)
class ActionSpec:
    """What the pipeline knows about one §8.4 plan action."""

    action: str
    tools: tuple[str, ...]
    executable: bool
    reason: str | None = None
    web: bool = False
    #: What the action needs to be able to run (documented for the delivery):
    #: an executable action may still be un-runnable for *this* request — a
    #: ``file_ingest`` needs an ingested document, which is per-request state.
    requires: str | None = None

    def refusal(self) -> str:
        """Return the §25.2 sentence explaining why the action cannot run today."""
        if self.reason:
            return self.reason
        return f"L'action '{self.action}' n'est pas branchée sur le pipeline (§8.4)."


#: The closed vocabulary of plan actions, with the truth about each one.
ACTIONS: dict[str, ActionSpec] = {
    "collect_information": ActionSpec(
        action="collect_information",
        tools=WEB_TOOLS,
        executable=True,
        web=True,
    ),
    "fetch_page": ActionSpec(
        action="fetch_page",
        tools=("open_url", "follow_link"),
        executable=True,
        web=True,
    ),
    "file_ingest": ActionSpec(
        action="file_ingest",
        tools=(
            "read_csv",
            "read_excel",
            "read_json",
            "read_xml",
            "read_pdf",
            "extract_document",
        ),
        executable=True,
        requires=(
            "un document déjà ingéré pour la requête "
            "(POST /v1/requests/{request_id}/documents, §9.1)"
        ),
        reason=(
            "aucun document n'a été ingéré pour cette requête : un file_ingest relit "
            "les unités §11 du document téléversé (POST /v1/requests/{request_id}/documents), "
            "il ne va pas le chercher sur le réseau"
        ),
    ),
    "query_database": ActionSpec(
        action="query_database",
        tools=("postgres_query",),
        executable=True,
        requires=(
            "une source PostgreSQL nommée par la requête : "
            "constraints.source_preferences = [\"postgres:<credential_ref>[#table]\"] (§7/§36.7)"
        ),
        reason=(
            "aucune source PostgreSQL n'est nommée par la requête : les identifiants "
            "viennent du vault (§41.4) et la requête ne porte jamais de DSN. Nommer la "
            "source voulue : source_preferences = [\"postgres:<credential_ref>#<table>\"]"
        ),
    ),
    "analyze_dataset": ActionSpec(
        action="analyze_dataset",
        tools=(
            "inspect_schema",
            "profile_dataset",
            "detect_duplicates",
            "validate_schema",
            "check_missing_values",
            "check_consistency",
        ),
        executable=False,
        reason="les contrôles §13 exigent un Dataset construit (§11) — lot L2.3 puis L5",
    ),
    "extract_image_content": ActionSpec(
        action="extract_image_content",
        tools=("extract_image_content",),
        executable=False,
        reason=(
            "l'extraction d'image dépend de Pillow (optionnel, décision D6) et d'un document "
            "matérialisé — hors périmètre V1"
        ),
    ),
    "compare_sources": ActionSpec(
        action="compare_sources",
        tools=("compare_sources", "check_freshness"),
        executable=False,
        reason="la comparaison exige des unités et sources structurées (§14.4) — lot L4",
    ),
    "retrieve_context": ActionSpec(
        action="retrieve_context",
        tools=("retrieve_context", "hybrid_search", "vector_search", "locate_fragment"),
        executable=True,
        requires=(
            "des unités §11 déjà stockées (la mémoire §17.1) et une base PostgreSQL "
            "configurée : la recherche §16.2 lit ``information_units``"
        ),
        reason=(
            "aucune unité §11 n'est consultable : la mémoire §17.1 est vide ou sa base "
            "n'est pas configurée, la reconstruction de contexte n'a donc rien à relire"
        ),
    ),
    "memory_lookup": ActionSpec(
        action="memory_lookup",
        tools=("hybrid_search", "vector_search", "retrieve_context"),
        executable=True,
        requires=(
            "une mémoire §17.1 alimentée : des unités §11 déjà stockées (elles viennent "
            "des runs précédents) et, pour la moitié sémantique de §16.2, des embeddings "
            "§16.1 — sinon la recherche est lexicale seule et le dit"
        ),
        reason=(
            "la mémoire §17.1 n'est pas consultable : aucune base PostgreSQL n'est "
            "configurée, la requête repart donc d'une acquisition complète plutôt que "
            "de réutiliser des unités dont l'existence n'est pas prouvée"
        ),
    ),
    "persist_results": ActionSpec(
        action="persist_results",
        tools=("store_source", "store_information", "store_evidence"),
        executable=False,
        reason=(
            "le pipeline persiste par pipeline_persistence (§27) ; les tools de stockage §21 "
            "ne sont pas appelés depuis un plan"
        ),
    ),
    "classify_sensitivity": ActionSpec(
        action="classify_sensitivity",
        tools=("classify_sensitivity",),
        executable=False,
        reason="la classification §19.4 est appliquée à l'ingestion (L2.1), pas depuis un plan",
    ),
    "check_permission": ActionSpec(
        action="check_permission",
        tools=("check_permission",),
        executable=False,
        reason="les permissions §19.3 sont appliquées par les middlewares, pas par le plan",
    ),
}


def is_web_action(action: str | None) -> bool:
    """Return whether *action* is executed by the acquisition stage itself.

    An unknown action is **not** a web action: defaulting to "search the web with
    the action name as the query" is exactly the behaviour this module removes.
    """
    spec = ACTIONS.get(str(action or ""))
    return bool(spec and spec.web)


def describe_action(action: str | None) -> ActionSpec:
    """Return the spec of *action*, inventing nothing for an unknown one.

    Args:
        action: The ``action`` field of a plan step.

    Returns:
        The known :class:`ActionSpec`, or a non-executable one naming the action
        as unknown — never ``None``, so every caller has a reason to state.
    """
    name = str(action or "")
    spec = ACTIONS.get(name)
    if spec is not None:
        return spec
    return ActionSpec(
        action=name or "<absente>",
        tools=(),
        executable=False,
        reason=(
            f"l'action '{name or '<absente>'}' n'appartient pas au vocabulaire fermé du "
            f"planificateur ({', '.join(sorted(ACTIONS))}) : aucun outil §21 ne lui correspond"
        ),
    )


def resolve(name: str) -> Callable[..., Any]:
    """Return the callable implementing the §21 *name*.

    Raises:
        UnavailableTool: When the name is not a §21 tool or its module cannot be
            imported (optional reader missing, for instance).
    """
    from app import tools

    try:
        return getattr(tools, name)
    except AttributeError as exc:
        raise UnavailableTool(
            f"Outil §21 inconnu : '{name}' n'est pas dans la surface de app.tools (§21)."
        ) from exc
    except Exception as exc:
        raise UnavailableTool(
            f"Outil §21 '{name}' indisponible ({type(exc).__name__}: {exc})."
        ) from exc


def populate_registry(registry: ToolRegistry | None = None) -> ToolRegistry:
    """Register every resolvable §21 tool in *registry* (idempotent).

    Args:
        registry: Registry to fill; a fresh one is created when omitted.

    Returns:
        The filled registry. A tool that cannot be resolved is **skipped**, and
        :func:`unavailable_tools` reports it with its cause — registering a stub
        would make the registry lie about what INIS can do.
    """
    target = registry if registry is not None else ToolRegistry()
    from app import tools

    for name in sorted(tools._TOOL_MODULES):
        if name in target.list():
            continue
        try:
            target.register(name, resolve(name))
        except (UnavailableTool, ValueError):
            continue
    return target


_DEFAULT_REGISTRY: ToolRegistry | None = None


def default_registry() -> ToolRegistry:
    """Return the process-wide registry, populated on first use."""
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = populate_registry()
    return _DEFAULT_REGISTRY


def registered_tools() -> list[str]:
    """Return the §21 names registered in :func:`default_registry`."""
    return sorted(default_registry().list())


def unavailable_tools() -> dict[str, str]:
    """Return the §21 names that could not be registered, with their cause."""
    from app import tools

    declared = set(tools._TOOL_MODULES)
    failures: dict[str, str] = {}
    for name in sorted(declared - set(registered_tools())):
        try:
            resolve(name)
        except UnavailableTool as exc:
            failures[name] = str(exc)
    return failures
