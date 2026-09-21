"""Identify ambiguous requests before planning begins."""

from dataclasses import dataclass

from app.agents.understanding.request_parser import InformationRequest


@dataclass(frozen=True)
class ClarificationResult:
    """Whether a request needs a user clarification and why."""

    required: bool
    reasons: tuple[str, ...] = ()


class ClarificationDetector:
    """Detect common ambiguities required by the agentic test scenarios of §33.3."""

    _AMBIGUOUS_PHRASES = ("something", "anything", "whatever", "as appropriate")

    def detect(self, request: InformationRequest) -> ClarificationResult:
        """Return a deterministic clarification signal for underspecified requests."""
        objective = request.objective.lower()
        reasons: list[str] = []

        if len(request.objective.split()) < 3:
            reasons.append("objective is too short to identify the requested information")
        if any(phrase in objective for phrase in self._AMBIGUOUS_PHRASES):
            reasons.append("objective contains an ambiguous scope")
        if not request.question and not request.required_information and objective in {
            "help",
            "research",
            "information",
        }:
            reasons.append("objective does not identify a subject or expected result")

        return ClarificationResult(required=bool(reasons), reasons=tuple(reasons))
