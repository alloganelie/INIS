"""Make conservative delegation decisions without a registry dependency."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DelegationDecision:
    """Whether execution should be delegated and the supporting rationale."""

    should_delegate: bool
    reason: str


class DelegationDecider:
    """Decide only from explicit execution signals; discovery remains an injected concern."""

    def decide(
        self,
        *,
        specialist_required: bool = False,
        local_capability_available: bool = True,
    ) -> DelegationDecision:
        """Delegate only if the request explicitly needs an unavailable capability."""
        should_delegate = specialist_required and not local_capability_available
        reason = (
            "required specialist capability is unavailable locally"
            if should_delegate
            else "local execution remains appropriate"
        )
        return DelegationDecision(should_delegate=should_delegate, reason=reason)
