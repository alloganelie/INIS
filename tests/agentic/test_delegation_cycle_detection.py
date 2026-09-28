"""§41.10 scenario — « cycle de délégation ».

A delegation chain may never loop back on itself (``INIS → A → B → INIS``):
the runtime evaluates every hop *before* it is executed and refuses a loop
back with an explicit ``cycle`` reason instead of deadlocking the agents in an
endless hand-off. Depth limits, trust relations and fail-closed behaviour for
unknown agents complete the guard.

Pure in-memory graph logic — no Docker, no network.
"""

from __future__ import annotations

from app.domain.enums.delegation_effect import DelegationEffect
from app.registry.delegation_graph import DelegationGraph
from app.registry.trust_graph import TrustGraph, can_delegate

#: A configured topology that *contains* the loop INIS → A → B → INIS.
CYCLIC_TRUST = {
    "INIS": {
        "trusted_agents": ["AGT_A"],
        "trust_level": "full",
        "max_delegation_depth": 3,
    },
    "AGT_A": {
        "trusted_agents": ["AGT_B"],
        "trust_level": "partial",
        "max_delegation_depth": 3,
    },
    "AGT_B": {
        "trusted_agents": ["INIS"],
        "trust_level": "minimal",
        "max_delegation_depth": 3,
    },
}


def test_closing_the_loop_back_to_the_root_is_refused_as_a_cycle() -> None:
    """``INIS → A → B → INIS`` is denied with the explicit ``cycle`` reason."""
    trust = TrustGraph(CYCLIC_TRUST)
    delegation = trust.to_delegation_graph()

    effect, reason = can_delegate(
        trust, delegation, ["INIS", "AGT_A", "AGT_B"], "INIS"
    )

    assert (effect, reason) == (DelegationEffect.DENY, "cycle")
    assert effect is DelegationEffect.DENY


def test_self_delegation_is_refused_even_without_a_configured_edge() -> None:
    """An agent delegating to itself is a one-hop cycle — denied on the path alone."""
    trust = TrustGraph(CYCLIC_TRUST)
    delegation = DelegationGraph()  # no topology configured at all

    effect, reason = can_delegate(trust, delegation, ["INIS"], "INIS")

    assert (effect, reason) == (DelegationEffect.DENY, "cycle")


def test_the_loop_is_broken_before_it_is_executed() -> None:
    """The chain walks hop by hop; the closing hop never runs, so no agent loops."""
    trust = TrustGraph(CYCLIC_TRUST)
    delegation = trust.to_delegation_graph()
    # The *configured* topology does contain the latent loop...
    latent = delegation.find_cycle()
    assert latent is not None and latent[0] == latent[-1]

    path = ["INIS"]
    refusals: list[str] = []
    for hop in ("AGT_A", "AGT_B", "INIS"):
        effect, reason = can_delegate(trust, delegation, path, hop)
        if effect is DelegationEffect.ALLOW:
            path.append(hop)
        else:
            refusals.append(reason)

    assert path == ["INIS", "AGT_A", "AGT_B"], "the executed chain never revisits anyone"
    assert refusals == ["cycle"], "the closing hop is refused, not executed"
    assert delegation.detect_cycle(path) is False, "no executed hop ever looped"


def test_forward_steps_are_allowed_while_the_chain_stays_acyclic() -> None:
    """Control: trusted, in-depth, acyclic hops proceed normally."""
    trust = TrustGraph(CYCLIC_TRUST)
    delegation = trust.to_delegation_graph()

    effect, reason = can_delegate(trust, delegation, ["INIS"], "AGT_A")
    assert (effect, reason) == (DelegationEffect.ALLOW, "ok")

    effect, reason = can_delegate(trust, delegation, ["INIS", "AGT_A"], "AGT_B")
    assert (effect, reason) == (DelegationEffect.ALLOW, "ok")


def test_depth_limit_stops_endless_delegation() -> None:
    """A chain that used its only allowed hop is refused with ``max_depth``."""
    trust = TrustGraph(CYCLIC_TRUST)
    delegation = trust.to_delegation_graph()

    effect, reason = can_delegate(
        trust, delegation, ["INIS", "AGT_A"], "AGT_B", max_depth=1
    )

    assert (effect, reason) == (DelegationEffect.DENY, "max_depth")


def test_denials_fail_closed_with_an_explicit_reason() -> None:
    """Unknown, untrusted or empty delegations are refused — never raised, never allowed."""
    trust = TrustGraph(CYCLIC_TRUST)

    # An edge exists in the topology but no trust relation backs it.
    delegation = DelegationGraph([("INIS", "AGT_X")])
    effect, reason = can_delegate(trust, delegation, ["INIS"], "AGT_X")
    assert (effect, reason) == (DelegationEffect.DENY, "untrusted_target")

    # A source absent from the trust graph may not delegate at all.
    effect, reason = can_delegate(trust, delegation, ["GHOST"], "AGT_X")
    assert (effect, reason) == (DelegationEffect.DENY, "unknown_source")

    effect, reason = can_delegate(trust, delegation, [], "AGT_X")
    assert (effect, reason) == (DelegationEffect.DENY, "empty_path")
