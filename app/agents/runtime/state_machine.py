"""State transitions for the INIS agent runtime."""

from enum import Enum
from typing import Final

from app.core.errors import ValidationError


class AgentState(str, Enum):
    """Runtime states supported by the Phase-02 agent loop."""

    RECEIVED = "RECEIVED"
    UNDERSTANDING = "UNDERSTANDING"
    PLANNED = "PLANNED"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    DELIVERING = "DELIVERING"
    DONE = "DONE"
    FAILED = "FAILED"


VALID_TRANSITIONS: Final[dict[AgentState, frozenset[AgentState]]] = {
    AgentState.RECEIVED: frozenset({AgentState.UNDERSTANDING, AgentState.FAILED}),
    AgentState.UNDERSTANDING: frozenset({AgentState.PLANNED, AgentState.FAILED}),
    AgentState.PLANNED: frozenset({AgentState.EXECUTING, AgentState.FAILED}),
    AgentState.EXECUTING: frozenset({AgentState.VERIFYING, AgentState.FAILED}),
    AgentState.VERIFYING: frozenset({AgentState.DELIVERING, AgentState.FAILED}),
    AgentState.DELIVERING: frozenset({AgentState.DONE, AgentState.FAILED}),
    AgentState.DONE: frozenset(),
    AgentState.FAILED: frozenset(),
}


class StateMachine:
    """Enforce the permitted progression of an agent runtime."""

    def __init__(self, initial_state: AgentState = AgentState.RECEIVED) -> None:
        self.current_state = initial_state

    @property
    def state(self) -> AgentState:
        """Return the current runtime state."""
        return self.current_state

    def transition(self, to: AgentState) -> AgentState:
        """Move to *to* when it is valid from the current state."""
        try:
            target_state = AgentState(to)
        except ValueError as error:
            raise ValidationError(f"Unknown agent state: {to}") from error

        if target_state not in VALID_TRANSITIONS[self.current_state]:
            raise ValidationError(
                f"Invalid transition: {self.current_state.value} -> {target_state.value}"
            )

        self.current_state = target_state
        return self.current_state
