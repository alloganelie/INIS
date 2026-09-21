"""Conflict-detection prompt per INIS spec §22.3 (contradictions)."""

from __future__ import annotations


def build(
    item_a: str,
    item_b: str,
    context: str | None = None,
) -> str:
    """Build the contradiction-detection prompt for two information items.

    Args:
        item_a: First information item description.
        item_b: Second information item description.
        context: Optional shared context (topic, period, …).

    Returns:
        Prompt string asking for a JSON conflict verdict.
    """
    if not item_a or not item_a.strip():
        raise ValueError("item_a must be a non-empty string")
    if not item_b or not item_b.strip():
        raise ValueError("item_b must be a non-empty string")
    lines = [
        "You are the INIS conflict-detection assistant.",
        "Compare the two information items and decide if they contradict.",
        "",
        f"Item A: {item_a.strip()}",
        f"Item B: {item_b.strip()}",
    ]
    if context and context.strip():
        lines.append(f"Context: {context.strip()}")
    lines.extend(
        [
            "",
            "Absolute rule (§22.3): you only flag candidate contradictions;",
            "resolution requires sourced evidence, never your verdict alone.",
            "",
            "Respond with JSON only, using exactly these keys:",
            '{"conflict": <true|false>, '
            '"difference_type": "<value|definition|date|methodology|scope|none>", '
            '"severity": "<low|medium|high|none>", '
            '"explanation": "<one-sentence justification>"}',
        ]
    )
    return "\n".join(lines)
