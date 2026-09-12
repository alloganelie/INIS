"""Tests for the INIS agent state machine."""

import pytest

from app.agents.runtime.state_machine import AgentState, StateMachine
from app.core.errors import ValidationError


def test_state_machine_starts_received() -> None:
    assert StateMachine().state is AgentState.RECEIVED


def test_state_machine_allows_valid_transition() -> None:
    machine = StateMachine()

    assert machine.transition(AgentState.UNDERSTANDING) is AgentState.UNDERSTANDING


def test_state_machine_rejects_invalid_transition() -> None:
    machine = StateMachine()

    with pytest.raises(ValidationError, match="Invalid transition"):
        machine.transition(AgentState.EXECUTING)


def test_state_machine_terminal_state_has_no_outgoing_transition() -> None:
    machine = StateMachine()
    for state in (
        AgentState.UNDERSTANDING,
        AgentState.PLANNED,
        AgentState.EXECUTING,
        AgentState.VERIFYING,
        AgentState.DELIVERING,
        AgentState.DONE,
    ):
        machine.transition(state)

    with pytest.raises(ValidationError, match="Invalid transition"):
        machine.transition(AgentState.FAILED)
