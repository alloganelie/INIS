"""Unit tests for §8.2 step dependency resolution.

``DependencyResolver.resolve`` implements Kahn's algorithm and must refuse a
plan whose dependencies loop instead of executing it partially.
"""

from __future__ import annotations

import pytest

from app.planning.dependency_resolver import DependencyResolver


def _step(step_id: str, *depends_on: str) -> dict[str, object]:
    """Build a minimal plan step with optional dependencies."""
    return {"step_id": step_id, "depends_on": list(depends_on)}


class TestResolveOrder:
    """§8.2 — steps execute after the steps they depend on."""

    def test_linear_chain_is_ordered(self) -> None:
        """A → B → C resolves to (A, B, C)."""
        resolver = DependencyResolver()
        order = resolver.resolve(
            [_step("C", "B"), _step("B", "A"), _step("A")]
        )
        assert order == ["A", "B", "C"]

    def test_independent_steps_are_all_returned(self) -> None:
        """No dependency means no ordering constraint, but nothing is dropped."""
        resolver = DependencyResolver()
        order = resolver.resolve([_step("A"), _step("B"), _step("C")])
        assert sorted(order) == ["A", "B", "C"]

    def test_diamond_dependency_places_join_last(self) -> None:
        """A → (B, C) → D keeps D after both branches."""
        resolver = DependencyResolver()
        order = resolver.resolve(
            [_step("D", "B", "C"), _step("B", "A"), _step("C", "A"), _step("A")]
        )
        assert order[0] == "A"
        assert order[-1] == "D"
        assert set(order[1:3]) == {"B", "C"}

    def test_single_step_plan(self) -> None:
        """A one-step plan resolves to itself."""
        assert DependencyResolver().resolve([_step("A")]) == ["A"]

    def test_empty_plan_resolves_to_empty_order(self) -> None:
        """An empty plan has no execution order (no crash)."""
        assert DependencyResolver().resolve([]) == []


class TestMissingDependencies:
    """§8.2 — a dependency outside the plan is ignored, not fatal."""

    def test_unknown_dependency_does_not_block_the_step(self) -> None:
        """The step stays executable when its dependency is absent from the plan."""
        resolver = DependencyResolver()
        order = resolver.resolve([_step("A", "GHOST")])
        assert order == ["A"]


class TestCycleDetection:
    """§8.2 — a circular dependency is a validation error (§0.2)."""

    def test_two_step_cycle_is_refused(self) -> None:
        """A ↔ B raises instead of returning a partial order."""
        resolver = DependencyResolver()
        with pytest.raises(ValueError, match="Circular dependency detected"):
            resolver.resolve([_step("A", "B"), _step("B", "A")])

    def test_cycle_path_is_reported_in_the_error(self) -> None:
        """The error names the steps involved so operators can fix the plan."""
        resolver = DependencyResolver()
        with pytest.raises(ValueError) as excinfo:
            resolver.resolve([_step("A", "C"), _step("B", "A"), _step("C", "B")])
        message = str(excinfo.value)
        assert "Circular dependency detected" in message
        assert "A" in message and "B" in message

    def test_self_dependency_is_a_cycle(self) -> None:
        """A step depending on itself can never run."""
        resolver = DependencyResolver()
        with pytest.raises(ValueError):
            resolver.resolve([_step("A", "A")])


class TestExecutableSteps:
    """§8.2 — the scheduler asks for the currently runnable steps."""

    def test_returns_steps_with_satisfied_dependencies(self) -> None:
        """Only steps whose dependencies are completed are returned."""
        steps = [_step("A"), _step("B", "A"), _step("C", "B")]
        executable = DependencyResolver().get_executable_steps(steps, {"A"})
        assert executable == ["B"]

    def test_completed_steps_are_never_returned_again(self) -> None:
        """A finished step is filtered out (idempotent scheduling)."""
        steps = [_step("A"), _step("B", "A")]
        executable = DependencyResolver().get_executable_steps(steps, {"A", "B"})
        assert executable == []

    def test_nothing_is_executable_before_the_root(self) -> None:
        """Before the first step completes, only the root is runnable."""
        steps = [_step("A"), _step("B", "A")]
        assert DependencyResolver().get_executable_steps(steps, set()) == ["A"]

