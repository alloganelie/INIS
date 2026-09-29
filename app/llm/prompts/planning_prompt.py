"""Planning prompt per INIS spec §22.3 (planifier les étapes)."""

from __future__ import annotations

from typing import Any


def build(
    objective: str,
    available_tools: list[str],
    constraints: dict[str, Any] | None = None,
    max_steps: int = 8,
    available_actions: list[str] | None = None,
    requirements: list[str] | None = None,
) -> str:
    """Build the execution-plan generation prompt.

    Args:
        objective: Objective the plan must achieve.
        available_tools: Tool identifiers the planner may use (§21).
        constraints: Optional budget/time constraints.
        max_steps: Maximum number of plan steps to propose.
        available_actions: The §8.4 closed vocabulary of plan actions. When
            given, the prompt states it and requires every step to carry one of
            its values as ``action`` — a plan naming anything else is refused by
            ``app.planning.plan_builder`` before execution (§0.2, §22.3).
        requirements: The requirements the §22.2 understanding extracted, kept in
            the prompt so the plan answers them instead of the raw objective only.

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
    if requirements:
        lines.append("Requirements to satisfy: " + "; ".join(requirements))
    if available_actions:
        lines.extend(
            [
                "",
                (
                    "Closed vocabulary of actions (§8.4): "
                    + ", ".join(sorted(available_actions))
                ),
                (
                    "Every step must declare one of them as \"action\". Any other "
                    "value makes the whole plan invalid: it will be refused, not "
                    "repaired."
                ),
            ]
        )
    if constraints:
        lines.append(f"Constraints: {constraints}")
    lines.extend(
        [
            "",
            "Absolute rule (§22.3): the plan is a proposal; each step result",
            "must be verified by tools and evidence, never trusted blindly.",
            "",
            "Respond with JSON only, using exactly this shape:",
            (
                '{"steps": [{"order": <int>, "action": "<one of the allowed actions>", '
                '"tool": "<tool id>", "description": "<what to do>", '
                '"expected_output": "<what this step yields>"}]}'
            ),
        ]
    )
    return "\n".join(lines)
