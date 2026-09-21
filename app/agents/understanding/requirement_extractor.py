"""Extract explicit, traceable requirements from an information request."""

from dataclasses import dataclass

from app.agents.understanding.request_parser import InformationRequest


@dataclass(frozen=True)
class Requirement:
    """One information requirement selected for planning."""

    description: str
    requirement_type: str = "information"


class RequirementExtractor:
    """Extract requirements without treating an LLM as a factual source."""

    def extract(self, request: InformationRequest) -> tuple[Requirement, ...]:
        """Prefer explicit requirements, with the objective as a safe fallback."""
        descriptions = request.required_information or (request.objective,)
        return tuple(
            Requirement(description=description.strip())
            for description in descriptions
            if description.strip()
        )
