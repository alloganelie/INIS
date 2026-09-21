"""Coordinate the request lifecycle without hard dependencies on planning or LLM modules."""

from dataclasses import dataclass
from typing import Any, Protocol

from app.agents.decision.termination_evaluator import (
    TerminationContext,
    TerminationDecision,
    TerminationEvaluator,
)
from app.agents.pipeline.step_executor import StepExecutor, StepTool
from app.agents.understanding.clarification_detector import ClarificationDetector
from app.agents.understanding.context_enricher import ContextEnricher
from app.agents.understanding.request_parser import InformationRequest, RequestParser
from app.agents.understanding.requirement_extractor import Requirement, RequirementExtractor
from app.agents.runtime.state_machine import AgentState, StateMachine


class PlanBuilderProtocol(Protocol):
    """Planning boundary for creating a section 8.2 plan."""

    def build(
        self,
        request_id: str,
        objective: str,
        steps: list[dict[str, Any]],
        budget: dict[str, int | float | None],
    ) -> dict[str, Any]:
        """Build a normalized execution plan."""


class ConfidenceEvaluatorProtocol(Protocol):
    """Confidence boundary; concrete confidence implementations remain optional."""

    def evaluate(self, results: list[dict[str, Any]]) -> float:
        """Return a score between zero and one for executed results."""


@dataclass(frozen=True)
class PipelineResult:
    """Observable result of one in-memory request pipeline run."""

    request: InformationRequest
    requirements: tuple[Requirement, ...]
    plan: dict[str, Any] | None
    step_results: tuple[dict[str, Any], ...]
    confidence_score: float
    termination: TerminationDecision | None
    state: AgentState
    clarification_reasons: tuple[str, ...] = ()
    model_enrichment_skipped: bool = False


class PipelineCoordinator:
    """Orchestrate state machine, understanding, planning, execution, and confidence."""

    def __init__(
        self,
        *,
        request_parser: RequestParser | None = None,
        requirement_extractor: RequirementExtractor | None = None,
        clarification_detector: ClarificationDetector | None = None,
        context_enricher: ContextEnricher | None = None,
        termination_evaluator: TerminationEvaluator | None = None,
        step_executor: StepExecutor | None = None,
    ) -> None:
        self._request_parser = request_parser or RequestParser()
        self._requirement_extractor = requirement_extractor or RequirementExtractor()
        self._clarification_detector = clarification_detector or ClarificationDetector()
        self._context_enricher = context_enricher or ContextEnricher()
        self._termination_evaluator = termination_evaluator or TerminationEvaluator()
        self._step_executor = step_executor or StepExecutor()

    def run(
        self,
        text: str,
        *,
        plan_builder: PlanBuilderProtocol,
        tool: StepTool,
        confidence_evaluator: ConfidenceEvaluatorProtocol | None = None,
        additional_context: dict[str, Any] | None = None,
    ) -> PipelineResult:
        """Run the supported §28 stages and return their observable in-memory state."""
        state_machine = StateMachine()
        request = self._request_parser.parse(text, context=additional_context)
        state_machine.transition(AgentState.UNDERSTANDING)

        clarification = self._clarification_detector.detect(request)
        enrichment = self._context_enricher.enrich(request, additional_context)
        requirements = self._requirement_extractor.extract(request)
        if clarification.required:
            state_machine.transition(AgentState.FAILED)
            return PipelineResult(
                request=request,
                requirements=requirements,
                plan=None,
                step_results=(),
                confidence_score=0.0,
                termination=None,
                state=state_machine.state,
                clarification_reasons=clarification.reasons,
                model_enrichment_skipped=enrichment.model_enrichment_skipped,
            )

        state_machine.transition(AgentState.PLANNED)
        steps = [
            {
                "action": "collect_information",
                "tool": "selected_tool",
                "inputs": {"requirement": requirement.description},
                "expected_output": "information",
            }
            for requirement in requirements
        ]
        plan = plan_builder.build(
            request.request_id,
            request.objective,
            steps,
            {
                "max_iterations": request.constraints.maximum_iterations,
                "max_cost": request.constraints.maximum_cost,
                "max_execution_time_seconds": request.constraints.maximum_execution_time_seconds,
            },
        )

        state_machine.transition(AgentState.EXECUTING)
        results = [self._step_executor.execute(step, tool) for step in plan["steps"]]
        confidence_score = (
            confidence_evaluator.evaluate(results) if confidence_evaluator is not None else 0.0
        )
        termination = self._termination_evaluator.evaluate(
            TerminationContext(
                requirements_satisfied=bool(results) and all(
                    result["status"] == "done" for result in results
                ),
                confidence_score=confidence_score,
                minimum_confidence=request.constraints.minimum_confidence,
                information_unavailable=any(
                    result["status"] == "failed" for result in results
                ),
            )
        )

        state_machine.transition(AgentState.VERIFYING)
        state_machine.transition(AgentState.DELIVERING)
        state_machine.transition(AgentState.DONE)
        return PipelineResult(
            request=request,
            requirements=requirements,
            plan=plan,
            step_results=tuple(results),
            confidence_score=confidence_score,
            termination=termination,
            state=state_machine.state,
            model_enrichment_skipped=enrichment.model_enrichment_skipped,
        )
