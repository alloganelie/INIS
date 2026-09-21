"""Confidence-signal prompt per INIS spec §22.3 (signaux de confiance)."""

from __future__ import annotations


def build(
    claim: str,
    supporting_evidence: list[str] | None = None,
    contradicting_evidence: list[str] | None = None,
) -> str:
    """Build the confidence-signal evaluation prompt.

    Args:
        claim: Claim to evaluate.
        supporting_evidence: Evidence excerpts supporting the claim.
        contradicting_evidence: Evidence excerpts against the claim.

    Returns:
        Prompt string asking for a JSON confidence signal (0-1, not a probability).
    """
    if not claim or not claim.strip():
        raise ValueError("claim must be a non-empty string")
    supporting = supporting_evidence or []
    contradicting = contradicting_evidence or []
    lines = [
        "You are the INIS confidence assistant.",
        "Evaluate the confidence signal for the claim below.",
        "",
        f"Claim: {claim.strip()}",
        f"Supporting evidence ({len(supporting)}):",
    ]
    lines.extend(f"- {item}" for item in supporting)
    lines.append(f"Contradicting evidence ({len(contradicting)}):")
    lines.extend(f"- {item}" for item in contradicting)
    lines.extend(
        [
            "",
            "Absolute rule (§22.3): this score is an assistance signal, not a",
            "probability and never a proof; the claim needs sourced evidence.",
            "",
            "Respond with JSON only, using exactly these keys:",
            '{"score": <float 0-1>, '
            '"dimensions": {"source_reliability": <float 0-1>, '
            '"evidence_strength": <float 0-1>, '
            '"cross_source_agreement": <float 0-1>}, '
            '"rationale": "<one-sentence justification>"}',
        ]
    )
    return "\n".join(lines)
