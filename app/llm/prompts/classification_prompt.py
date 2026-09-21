"""Classification prompt per INIS spec §22.3 (classer les informations)."""

from __future__ import annotations


def build(
    content: str,
    candidate_labels: list[str],
    context: str | None = None,
) -> str:
    """Build the information-classification prompt.

    Args:
        content: Text content to classify.
        candidate_labels: Allowed labels (closed set).
        context: Optional disambiguating context.

    Returns:
        Prompt string asking for a JSON classification.
    """
    if not content or not content.strip():
        raise ValueError("content must be a non-empty string")
    if not candidate_labels:
        raise ValueError("candidate_labels must not be empty")
    labels = ", ".join(f'"{label}"' for label in candidate_labels)
    lines = [
        "You are the INIS classification assistant.",
        f"Classify the content into exactly one of: {labels}.",
        "",
        f"Content: {content.strip()}",
    ]
    if context and context.strip():
        lines.append(f"Context: {context.strip()}")
    lines.extend(
        [
            "",
            "Absolute rule (§22.3): classification is an assistance signal;",
            "the labeled fact must still be verified against its source.",
            "",
            "Respond with JSON only, using exactly these keys:",
            '{"label": "<one of the candidate labels>", '
            '"confidence": <float 0-1>, '
            '"rationale": "<one-sentence justification>"}',
        ]
    )
    return "\n".join(lines)
