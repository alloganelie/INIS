"""Unit tests for §41.10 delegation topology (cycles, depth, trust graph)."""

import pytest

from app.domain.enums.delegation_effect import DelegationEffect
from app.domain.enums.trust_level import TrustLevel
from app.registry.delegation_graph import DelegationGraph
from app.registry.trust_graph import TrustGraph
from app.registry.trust_graph import can_delegate

TRUST_CONFIG = {
    "INIS": {
        "trusted_agents": ["AGT_A"],
        "trust_level": "full",
        "max_delegation_depth": 2,
    },
    "AGT_A": {
        "trusted_agents": ["AGT_B"],
        "trust_level": "partial",
        "max_delegation_depth": 2,
    },
    "AGT_B": {
        "trusted_agents": ["INIS"],
        "trust_level": "minimal",
        "max_delegation_depth": 2,
    },
}


class TestDelegationGraph:
    """detect_cycle / max_depth_reached / find_cycle (§41.10)."""

    def test_detect_cycle_on_revisiting_path(self) -> None:
        """INIS → A → B → INIS closes a cycle."""
        graph = DelegationGraph(
            [("INIS", "AGT_A"), ("AGT_A", "AGT_B"), ("AGT_B", "INIS")]
        )
        assert graph.detect_cycle(["INIS", "AGT_A", "AGT_B", "INIS"]) is True
        assert graph.detect_cycle(["INIS", "AGT_A", "AGT_B"]) is False

    def test_would_create_cycle_checks_the_next_hop(self) -> None:
        graph = DelegationGraph()
        assert graph.would_create_cycle(["INIS", "AGT_A"], "INIS") is True
        assert graph.would_create_cycle(["INIS", "AGT_A"], "AGT_B") is False
        assert graph.would_create_cycle([], "INIS") is False

    def test_max_depth_reached_counts_delegation_hops(self) -> None:
        graph = DelegationGraph()
        # [A, B, C] = 2 hops
        assert graph.max_depth_reached(["A", "B", "C"], 2) is True
        assert graph.max_depth_reached(["A", "B", "C"], 3) is False
        assert graph.max_depth_reached(["A"], 1) is False
        assert graph.max_depth_reached([], 1) is False
        with pytest.raises(ValueError, match="max_depth"):
            graph.max_depth_reached(["A"], 0)

    def test_find_cycle_returns_the_loop_or_none(self) -> None:
        cyclic = DelegationGraph(
            [("INIS", "AGT_A"), ("AGT_A", "AGT_B"), ("AGT_B", "INIS")]
        )
        cycle = cyclic.find_cycle()
        assert cycle is not None
        assert cycle[0] == cycle[-1]
        assert set(cycle) == {"INIS", "AGT_A", "AGT_B"}

        acyclic = DelegationGraph([("INIS", "AGT_A"), ("AGT_A", "AGT_B")])
        assert acyclic.find_cycle() is None

    def test_add_delegation_validates_agents(self) -> None:
        graph = DelegationGraph()
        with pytest.raises(ValueError, match="source"):
            graph.add_delegation("", "AGT_A")
        with pytest.raises(ValueError, match="target"):
            graph.add_delegation("INIS", "")

    def test_evaluate_delegation_decides_each_step(self) -> None:
        graph = DelegationGraph(
            [("INIS", "AGT_A"), ("AGT_A", "AGT_B"), ("AGT_B", "INIS")]
        )
        assert graph.evaluate_delegation(["INIS"], "AGT_A") == (True, "ok")
        # Cycle broken before it happens (§41.10: "rompre").
        assert graph.evaluate_delegation(["INIS", "AGT_A", "AGT_B"], "INIS") == (
            False,
            "cycle",
        )
        assert graph.evaluate_delegation(["INIS"], "AGT_B") == (
            False,
            "unknown_target",
        )
        assert graph.evaluate_delegation([], "INIS") == (False, "empty_path")
        with pytest.raises(ValueError, match="max_depth"):
            graph.evaluate_delegation(["INIS"], "AGT_A", max_depth=0)

    def test_evaluate_delegation_enforces_depth(self) -> None:
        graph = DelegationGraph([("INIS", "AGT_A"), ("AGT_A", "AGT_B")])
        # ["INIS", "AGT_A"] is a 1-hop path: reached only at max_depth=1.
        assert graph.evaluate_delegation(["INIS", "AGT_A"], "AGT_B", 1) == (
            False,
            "max_depth",
        )
        assert graph.evaluate_delegation(["INIS", "AGT_A"], "AGT_B", 2) == (
            True,
            "ok",
        )


class TestTrustGraph:
    """agent_trust_graph [CONFIG] + combined delegation evaluation."""

    def test_to_dict_matches_the_spec_config_block(self) -> None:
        trust = TrustGraph(TRUST_CONFIG)
        payload = trust.to_dict()
        assert set(payload) == {"agent_trust_graph"}
        entry = payload["agent_trust_graph"]["AGT_A"]
        assert entry == {
            "trusted_agents": ["AGT_B"],
            "trust_level": "partial",
            "max_delegation_depth": 2,
        }

    def test_trust_levels_and_depth_accessors(self) -> None:
        trust = TrustGraph(TRUST_CONFIG)
        assert trust.trust_level("INIS") is TrustLevel.FULL
        assert trust.trust_level("AGT_B") is TrustLevel.MINIMAL
        assert trust.max_delegation_depth("INIS") == 2
        assert trust.is_trusted("INIS", "AGT_A") is True
        assert trust.is_trusted("INIS", "AGT_B") is False
        assert trust.is_trusted("UNKNOWN", "AGT_A") is False
        with pytest.raises(ValueError, match="Unknown agent"):
            trust.trust_level("UNKNOWN")

    def test_invalid_entries_fail_explicitly(self) -> None:
        with pytest.raises(ValueError, match="trust_level"):
            TrustGraph(
                {"INIS": {"trusted_agents": [], "trust_level": "total", "max_delegation_depth": 2}}
            )
        with pytest.raises(ValueError, match="missing keys"):
            TrustGraph({"INIS": {"trusted_agents": []}})
        with pytest.raises(ValueError, match="max_delegation_depth"):
            TrustGraph(
                {"INIS": {"trusted_agents": [], "trust_level": "full", "max_delegation_depth": 0}}
            )
        with pytest.raises(ValueError, match="agent_id"):
            TrustGraph().set_entry(
                "", trusted_agents=[], trust_level="full", max_delegation_depth=1
            )

    def test_to_delegation_graph_materializes_trust_edges(self) -> None:
        graph = TrustGraph(TRUST_CONFIG).to_delegation_graph()
        assert graph.edges == {
            "INIS": frozenset({"AGT_A"}),
            "AGT_A": frozenset({"AGT_B"}),
            "AGT_B": frozenset({"INIS"}),
        }

    def test_can_delegate_allows_a_trusted_step(self) -> None:
        trust = TrustGraph(TRUST_CONFIG)
        delegation = trust.to_delegation_graph()
        effect, reason = can_delegate(trust, delegation, ["INIS"], "AGT_A")
        assert effect is DelegationEffect.ALLOW
        assert reason == "ok"

    def test_can_delegate_breaks_cycles_and_depth_overflows(self) -> None:
        trust = TrustGraph(TRUST_CONFIG)
        delegation = trust.to_delegation_graph()

        effect, reason = can_delegate(
            trust, delegation, ["INIS", "AGT_A", "AGT_B"], "INIS"
        )
        assert (effect, reason) == (DelegationEffect.DENY, "cycle")

        # Root limit: INIS max_delegation_depth = 2 → path of 2 hops refuses.
        effect, reason = can_delegate(
            trust, delegation, ["INIS", "AGT_A", "AGT_B"], "INIS", max_depth=2
        )
        assert (effect, reason) == (DelegationEffect.DENY, "cycle")
        # Explicit depth limit refuses a path that used its only hop.
        effect, reason = can_delegate(
            trust, delegation, ["INIS", "AGT_A"], "AGT_B", max_depth=1
        )
        assert (effect, reason) == (DelegationEffect.DENY, "max_depth")

        # The root's configured limit (INIS = 1) applies to the whole chain.
        strict = TrustGraph(TRUST_CONFIG)
        strict.set_entry(
            "INIS",
            trusted_agents=["AGT_A"],
            trust_level="full",
            max_delegation_depth=1,
        )
        effect, reason = can_delegate(strict, delegation, ["INIS", "AGT_A"], "AGT_B")
        assert (effect, reason) == (DelegationEffect.DENY, "max_depth")

    def test_can_delegate_denies_untrusted_and_unknown_sources(self) -> None:
        trust = TrustGraph(TRUST_CONFIG)
        # Edge exists in the topology but no trust relation backs it.
        delegation = DelegationGraph([("INIS", "AGT_X")])
        effect, reason = can_delegate(trust, delegation, ["INIS"], "AGT_X")
        assert (effect, reason) == (DelegationEffect.DENY, "untrusted_target")

        # Source absent from the trust graph fails closed.
        effect, reason = can_delegate(trust, delegation, ["GHOST"], "AGT_X")
        assert (effect, reason) == (DelegationEffect.DENY, "unknown_source")

        effect, reason = can_delegate(trust, delegation, [], "AGT_X")
        assert (effect, reason) == (DelegationEffect.DENY, "empty_path")

