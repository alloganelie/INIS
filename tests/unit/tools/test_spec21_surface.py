"""§21 tool surface tests (§33.1).

Guards the full 35-signature §21 surface exported from ``app.tools`` and the
behaviour of the Phase 7 additions: agent discovery/messaging (§6, §5) and
governance tools (§19, §19.4, §18, §20).
"""

from __future__ import annotations

import inspect

import pytest

import app.tools
from app.core.errors import InfrastructureError, ValidationError
from app.registry import (
    AgentIdentity,
    AgentNotFoundError,
    AgentRegistry,
    CapabilityIndex,
)
from app.tools.agent_tools import (
    InProcessAgentChannel,
    discover_agents,
    query_agent_capabilities,
    receive_agent_result,
    send_agent_request,
)
from app.tools.governance_tools import (
    VersionStore,
    archive_record,
    check_permission,
    classify_sensitivity,
    create_version,
    write_audit_event,
)

#: The 35 §21 signatures (INIS_SPEC.md §21).
SPEC21_TOOLS: tuple[str, ...] = (
    "web_search",
    "open_url",
    "follow_link",
    "postgres_query",
    "read_csv",
    "read_excel",
    "read_json",
    "read_xml",
    "inspect_schema",
    "profile_dataset",
    "read_pdf",
    "extract_document",
    "extract_image_content",
    "locate_fragment",
    "detect_duplicates",
    "validate_schema",
    "check_missing_values",
    "check_consistency",
    "check_freshness",
    "compare_sources",
    "store_source",
    "store_information",
    "store_evidence",
    "vector_search",
    "hybrid_search",
    "retrieve_context",
    "discover_agents",
    "query_agent_capabilities",
    "send_agent_request",
    "receive_agent_result",
    "check_permission",
    "classify_sensitivity",
    "create_version",
    "archive_record",
    "write_audit_event",
)


def _identity(agent_id: str, capabilities: list[str]) -> AgentIdentity:
    return AgentIdentity(
        agent_id=agent_id,
        name=agent_id,
        description="test agent",
        version="1.0.0",
        status="available",
        capabilities=capabilities,
        protocols=["inis/1"],
        message_types=["INFORMATION_REQUEST"],
        input_schemas=[],
        output_schemas=[],
        security_requirements=[],
        health={},
        performance_profile={},
        learning_profile={},
    )


def _envelope(
    message_id: str = "MSG_01J00000000000000000000000",
    correlation_id: str = "CORR_01J00000000000000000000000",
) -> dict:
    return {
        "protocol_version": "1.0",
        "message_id": message_id,
        "correlation_id": correlation_id,
        "timestamp": "2026-01-01T00:00:00Z",
        "sender": {"agent_id": "agt_planner", "agent_version": "1.0.0"},
        "recipient": {"agent_id": "agt_worker", "agent_version": "1.0.0"},
        "message_type": "INFORMATION_REQUEST",
        "priority": "normal",
        "ttl_seconds": 60,
        "payload": {},
        "security": {"auth_method": "mtls"},
        "trace": {
            "trace_id": "0" * 32,
            "span_id": "0" * 16,
            "correlation_id": correlation_id,
        },
    }


class TestSpec21Surface:
    def test_all_35_tools_are_exported_and_callable(self) -> None:
        """Every §21 signature is reachable from ``app.tools`` (§21)."""
        assert len(SPEC21_TOOLS) == 35
        for name in SPEC21_TOOLS:
            assert name in app.tools.__all__, f"{name} missing from app.tools.__all__"
            assert callable(getattr(app.tools, name)), name

    def test_most_spec21_tools_are_async(self) -> None:
        """§21 declares ``async def``; the six file readers are sync today.

        The audit methodology (docs/AUDIT_GAPS_V2.md §4) accepts both
        ``def`` and ``async def`` for §21 — this pins the current set.
        """
        sync_allowed = {
            "read_csv",
            "read_excel",
            "read_json",
            "read_xml",
            "read_pdf",
            "extract_document",
        }
        for name in SPEC21_TOOLS:
            fn = getattr(app.tools, name)
            if name in sync_allowed:
                assert not inspect.iscoroutinefunction(fn), name
            else:
                assert inspect.iscoroutinefunction(fn), name

    def test_unknown_attribute_raises(self) -> None:
        with pytest.raises(AttributeError):
            getattr(app.tools, "not_a_tool")


class TestDiscoverAgents:
    @pytest.mark.asyncio
    async def test_discovers_only_matching_capability(self) -> None:
        registry = AgentRegistry()
        registry.register("agt_a", _identity("agt_a", ["search", "fetch"]))
        registry.register("agt_b", _identity("agt_b", ["fetch"]))
        found = await discover_agents("search", registry=registry)
        assert [a.agent_id for a in found] == ["agt_a"]

    @pytest.mark.asyncio
    async def test_index_narrows_candidates_before_registry_lookup(self) -> None:
        registry = AgentRegistry()
        registry.register("agt_a", _identity("agt_a", ["search"]))
        index = CapabilityIndex()
        index.add_agent("agt_a", ["search"])
        found = await discover_agents("search", registry=registry, capability_index=index)
        assert [a.agent_id for a in found] == ["agt_a"]
        assert await discover_agents("fetch", registry=registry, capability_index=index) == []

    @pytest.mark.asyncio
    async def test_missing_registry_raises_instead_of_empty_list(self) -> None:
        """No registry is an infrastructure failure, not "no agent" (§0.2)."""
        with pytest.raises(InfrastructureError):
            await discover_agents("search")
        with pytest.raises(InfrastructureError):
            await discover_agents("search", capability_index=CapabilityIndex())

    @pytest.mark.asyncio
    async def test_empty_capability_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            await discover_agents("", registry=AgentRegistry())


class TestQueryAgentCapabilities:
    @pytest.mark.asyncio
    async def test_returns_sorted_capabilities(self) -> None:
        registry = AgentRegistry()
        registry.register("agt_a", _identity("agt_a", ["fetch", "search"]))
        assert await query_agent_capabilities("agt_a", registry=registry) == [
            "fetch",
            "search",
        ]

    @pytest.mark.asyncio
    async def test_unknown_agent_raises_not_found(self) -> None:
        with pytest.raises(AgentNotFoundError):
            await query_agent_capabilities("agt_x", registry=AgentRegistry())

    @pytest.mark.asyncio
    async def test_missing_registry_raises_infrastructure_error(self) -> None:
        with pytest.raises(InfrastructureError):
            await query_agent_capabilities("agt_a")


class TestAgentMessaging:
    @pytest.mark.asyncio
    async def test_send_then_receive_roundtrip(self) -> None:
        channel = InProcessAgentChannel()
        sent = await send_agent_request("agt_worker", _envelope(), channel=channel)
        assert sent["correlation_id"] == "CORR_01J00000000000000000000000"
        pending = channel.take_pending(sent["correlation_id"])
        assert pending is not None and pending["agent_id"] == "agt_worker"

        channel.deposit(
            sent["correlation_id"], {**_envelope(), "message_type": "INFORMATION_RESPONSE"}
        )
        result = await receive_agent_result(sent["correlation_id"], channel=channel)
        assert result["message_type"] == "INFORMATION_RESPONSE"

    @pytest.mark.asyncio
    async def test_missing_result_raises_not_empty_envelope(self) -> None:
        """Absence of a result is reported, never synthesised (§0.2)."""
        with pytest.raises(InfrastructureError):
            await receive_agent_result("CORR_unknown", channel=InProcessAgentChannel())

    @pytest.mark.asyncio
    async def test_malformed_envelope_is_rejected(self) -> None:
        channel = InProcessAgentChannel()
        with pytest.raises(ValidationError):
            await send_agent_request("agt_worker", {"message_id": "MSG_x"}, channel=channel)
        with pytest.raises(ValidationError):
            await send_agent_request("", _envelope(), channel=channel)

    @pytest.mark.asyncio
    async def test_delivery_failure_surfaces_as_infrastructure_error(self) -> None:
        class BrokenChannel:
            async def deliver(self, agent_id: str, envelope: dict) -> None:
                raise RuntimeError("broker down")

            async def fetch(self, correlation_id: str) -> dict | None:
                return None

        with pytest.raises(InfrastructureError):
            await send_agent_request("agt_worker", _envelope(), channel=BrokenChannel())


class TestGovernanceTools:
    @pytest.mark.asyncio
    async def test_restricted_resource_is_denied(self) -> None:
        allowed = await check_permission(
            "agt_a", {"type": "source", "classification": "restricted"}, "read"
        )
        assert allowed is False

    @pytest.mark.asyncio
    async def test_plain_resource_is_allowed_without_role(self) -> None:
        allowed = await check_permission("agt_a", "source", "read")
        assert allowed is True

    @pytest.mark.asyncio
    async def test_permission_rejects_missing_arguments(self) -> None:
        with pytest.raises(ValidationError):
            await check_permission("", "source", "read")
        with pytest.raises(ValidationError):
            await check_permission("agt_a", "source", "")
        with pytest.raises(ValidationError):
            await check_permission("agt_a", 42, "read")  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_classify_sensitivity_detects_critical_pii(self) -> None:
        classification = await classify_sensitivity({"note": "SSN: 123-45-6789"})
        assert classification.sensitivity == "critical"
        assert classification.pii is True

    @pytest.mark.asyncio
    async def test_classify_sensitivity_low_for_public_text(self) -> None:
        classification = await classify_sensitivity({"text": "This is public information."})
        assert classification.sensitivity == "low"
        assert classification.pii is False

    @pytest.mark.asyncio
    async def test_classify_sensitivity_rejects_empty_payload(self) -> None:
        with pytest.raises(ValidationError):
            await classify_sensitivity({})

    @pytest.mark.asyncio
    async def test_create_version_chains_parents(self) -> None:
        store = VersionStore()
        first = await create_version(
            "SRC_1", {"actor": "agt_a", "justification": "init"}, store=store
        )
        second = await create_version(
            "SRC_1", {"actor": "agt_a", "justification": "edit"}, store=store
        )
        assert first.startswith("VER_")
        assert first != second
        chain = store.versions("SRC_1")
        assert chain[0]["parent_version"] is None
        assert chain[1]["parent_version"] == first
        assert len(chain[1]["hash"]) == 64

    @pytest.mark.asyncio
    async def test_create_version_rejects_empty_inputs(self) -> None:
        store = VersionStore()
        with pytest.raises(ValidationError):
            await create_version("", {"actor": "agt_a"}, store=store)
        with pytest.raises(ValidationError):
            await create_version("SRC_1", {}, store=store)

    @pytest.mark.asyncio
    async def test_archive_record_is_idempotent(self) -> None:
        store = VersionStore()
        await archive_record("SRC_1", store=store)
        first = store.archived_at("SRC_1")
        await archive_record("SRC_1", store=store)
        assert store.is_archived("SRC_1")
        assert store.archived_at("SRC_1") == first
        with pytest.raises(ValidationError):
            await archive_record("", store=store)

    @pytest.mark.asyncio
    async def test_write_audit_event_persists_valid_event(self) -> None:
        from app.governance.audit.audit_writer import AuditWriter

        writer = AuditWriter()
        await write_audit_event(
            {
                "actor_type": "agent",
                "actor_id": "agt_a",
                "action": "read",
                "resource_type": "source",
                "resource_id": "SRC_1",
                "request_id": "REQ_1",
                "result": "allow",
                "reason": "policy",
            },
            writer=writer,
        )
        events = await writer.list_events(actor_id="agt_a")
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_write_audit_event_rejects_invalid_events(self) -> None:
        from app.governance.audit.audit_writer import AuditWriter

        with pytest.raises(ValidationError):
            await write_audit_event({}, writer=AuditWriter())
        with pytest.raises(ValidationError):
            await write_audit_event({"actor_id": "agt_a"}, writer=AuditWriter())


