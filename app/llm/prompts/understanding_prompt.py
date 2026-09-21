"""Understanding prompt per INIS spec §22.3 (comprendre la demande)."""

from __future__ import annotations

from typing import Any


def build(
    objective: str,
    question: str | None = None,
    context: dict[str, Any] | None = None,
) -> str:
    """Build the request-understanding prompt.

    Args:
        objective: Stated objective of the information request.
        question: Optional explicit question to answer.
        context: Optional request context (region, period, …).

    Returns:
        Prompt string asking for a JSON understanding of the request.
    """
    if not objective or not objective.strip():
        raise ValueError("objective must be a non-empty string")
    lines = [
        "You are the INIS understanding assistant.",
        "Analyze the following information request and extract its intent.",
        "",
        f"Objective: {objective.strip()}",
    ]
    if question and question.strip():
        lines.append(f"Question: {question.strip()}")
    if context:
        lines.append(f"Context: {context}")
    lines.extend(
        [
            "",
            "Absolute rule (§22.3): you only assist understanding; you are never",
            "the source of a fact. Propose structure and hypotheses, not facts.",
            "",
            "Respond with JSON only, using exactly these keys:",
            '{"intent": "<one-sentence intent>", '
            '"entities": ["<named entity>", "..."], '
            '"required_information": ["<needed item>", "..."], '
            '"ambiguities": ["<open point>", "..."]}',
        ]
    )
    return "\n".join(lines)
