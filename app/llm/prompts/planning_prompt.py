"""Planning prompt per INIS spec §22.3 (planifier les étapes)."""

from __future__ import annotations

from typing import Any


def build(
    objective: str,
    available_tools: list[str],
    constraints: dict[str, Any] | None = None,
    max_steps: int = 8,
) -> str:
    """Build the execution-plan generation prompt.

    Args:
        objective: Objective the plan must achieve.
        available_tools: Tool identifiers the planner may use (§21).
        constraints: Optional budget/time constraints.
        max_steps: Maximum number of plan steps to propose.

    Returns:
        Prompt string asking for a JSON plan skeleton.
    """
    if not objective or not objective.strip():
        raise ValueError("objective must be a non-empty string")
    if not available_tools:
        raise ValueError("available_tools must not be empty")
    if max_steps < 1:
        raise ValueError("max_steps must be >= 1")
    lines = [
        "You are the INIS planning assistant.",
        "Propose an ordered execution plan to achieve the objective.",
        "",
        f"Objective: {objective.strip()}",
        f"Available tools: {', '.join(available_tools)}",
        f"Maximum steps: {max_steps}",
    ]
    if constraints:
        lines.append(f"Constraints: {constraints}")
    lines.extend(
        [
            "",
            "Absolute rule (§22.3): the plan is a proposal; each step result",
            "must be verified by tools and evidence, never trusted blindly.",
            "",
            "Respond with JSON only, using exactly this shape:",
            '{"steps": [{"order": <int>, "tool": "<tool id>", '
            '"description": "<what to do>", '
            '"expected_output": "<what this step yields>"}]}',
        ]
    )
    return "\n".join(lines)
