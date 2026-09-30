"""§21/§8.4 — every tool of §21 is registered, and every action tells the truth.

Two gaps this file pins:

* **C5** — ``ToolRegistry`` was never populated: the 35 §21 tools were
  implemented but unreachable from a plan. The registry now lists all 35, and the
  test fails if one of them stops resolving;
* **C4/§8.4** — an action must be able to say it cannot run. The closed
  vocabulary below declares, per action, the §21 tools it needs, whether the
  pipeline can execute it today, and why not when it cannot.
"""

from __future__ import annotations

import inspect

import pytest

from app.agents.pipeline.tool_dispatch import (
    ACTIONS,
    UnavailableTool,
    default_registry,
    describe_action,
    is_web_action,
    populate_registry,
    registered_tools,
    resolve,
    unavailable_tools,
)
from app.tools.registry import ToolRegistry

#: §8.4 actions the pipeline can execute today. ``file_ingest`` joined them in
#: L2.4 (it re-reads the §11 units of the documents already ingested for the
#: request) and ``query_database`` in L2.5 (it reads the PostgreSQL source named
#: by ``constraints.source_preferences``). ``memory_lookup`` and
#: ``retrieve_context`` joined them in L4: the §17.1 memory is consulted at the
#: head of every plan, with the §16.2 hybrid search injected. Each is executable
#: and *conditional*: without the material it needs, the step is degraded with
#: the reason, never turned into a web search.
EXECUTABLE_ACTIONS = {
    "collect_information",
    "fetch_page",
    "file_ingest",
    "query_database",
    "memory_lookup",
    "retrieve_context",
}

#: §8.4 actions that are declared but not wired yet, with the reason why.
KNOWN_GAPS = {
    "analyze_dataset",
    "extract_image_content",
    "compare_sources",
    "persist_results",
    "classify_sensitivity",
    "check_permission",
}


class TestRegistryPopulation:
    """C5 — the §21 surface is registered and resolvable."""

    def test_every_declared_tool_is_registered(self) -> None:
        from app import tools

        declared = set(tools._TOOL_MODULES)

        assert set(registered_tools()) == declared
        assert len(declared) == 35

    def test_no_declared_tool_is_unavailable(self) -> None:
        """Every §21 name resolves; a missing reader would be listed with its cause."""
        assert unavailable_tools() == {}

    def test_registration_is_idempotent(self) -> None:
        """Populating twice must not raise (``ToolRegistry.register`` does)."""
        registry = populate_registry(ToolRegistry())

        again = populate_registry(registry)

        assert again is registry
        assert len(again.list()) == 35

    def test_a_registered_tool_is_callable(self) -> None:
        tool = default_registry().get("read_csv")

        assert callable(tool)
        assert tool.__name__ == "read_csv"

    def test_an_unknown_name_is_refused_explicitly(self) -> None:
        with pytest.raises(UnavailableTool, match="inconnu"):
            resolve("definitely_not_a_spec21_tool")

    def test_the_registry_exposes_the_spec_names_not_stubs(self) -> None:
        """A registered tool must be a real function, never a fabricated placeholder."""
        for name in registered_tools():
            tool = resolve(name)
            assert callable(tool)
            assert name in (tool.__name__, tool.__qualname__)
            assert not inspect.isclass(tool)


class TestActionVocabulary:
    """§8.4 — a closed vocabulary, and the truth about each entry."""

    def test_web_actions_are_the_executable_ones_today(self) -> None:
        executable = {name for name, spec in ACTIONS.items() if spec.executable}

        assert executable == EXECUTABLE_ACTIONS

    def test_a_conditional_action_declares_what_it_needs(self) -> None:
        """§9.1 — an executable action may still need per-request state."""
        spec = describe_action("file_ingest")

        assert spec.executable is True
        assert spec.requires, "a conditional action must state its condition"
        assert "documents" in spec.requires
        assert spec.reason, "the un-runnable case must be explainable"
        assert "aucun document" in spec.refusal()

    def test_the_database_action_declares_the_source_it_needs(self) -> None:
        """§36.7 — the same rule for ``query_database``: it needs a named source."""
        spec = describe_action("query_database")

        assert spec.executable is True
        assert spec.tools == ("postgres_query",)
        assert "postgres:" in (spec.requires or "")
        assert spec.reason and "vault" in spec.refusal()

    def test_the_declared_action_is_the_executed_one(self) -> None:
        """Control: an executable action is not listed as a gap."""
        gaps = {name for name, spec in ACTIONS.items() if not spec.executable}

        assert "file_ingest" not in gaps
        assert gaps == KNOWN_GAPS

    def test_every_action_names_registered_tools(self) -> None:
        """An action may only require §21 tools that exist (§21)."""
        registered = set(registered_tools())

        for name, spec in ACTIONS.items():
            assert spec.tools, f"action '{name}' declares no §21 tool"
            assert set(spec.tools) <= registered, f"action '{name}' names an unknown tool"

    def test_a_gap_always_says_why(self) -> None:
        """§25.2 — an action that cannot run states the reason, never a bare refusal."""
        for name, spec in ACTIONS.items():
            if spec.executable:
                continue
            assert spec.reason, f"action '{name}' is not executable without a reason"
            assert len(spec.reason) > 30

    def test_an_unknown_action_is_not_executable_and_is_named(self) -> None:
        spec = describe_action("totally_made_up_action")

        assert spec.executable is False
        assert spec.tools == ()
        assert "totally_made_up_action" in spec.refusal()
        assert "vocabulaire fermé" in spec.refusal()

    def test_a_missing_action_is_described_not_crashed(self) -> None:
        spec = describe_action(None)

        assert spec.action == "<absente>"
        assert spec.executable is False

    def test_only_web_actions_route_to_the_acquisition_stage(self) -> None:
        """An unknown action is **not** a web action: that was the defect."""
        assert is_web_action("collect_information") is True
        assert is_web_action("file_ingest") is False
        assert is_web_action("totally_made_up_action") is False
        assert is_web_action(None) is False

    def test_the_web_actions_are_the_network_tools(self) -> None:
        from app.agents.pipeline.tool_dispatch import WEB_TOOLS

        assert ACTIONS["collect_information"].tools == WEB_TOOLS
        assert set(WEB_TOOLS) <= set(registered_tools())
