"""§28 complete request cycle: the canonical 22 stages and their execution.

§28 lists the ordered stages of one information request and states that *not
every stage is mandatory — the plan chooses which ones to activate*. This
module is the single source of truth for that list:

* :data:`CYCLE_STAGES` — the 22 stage identifiers, in spec order;
* :class:`RequestCycle` — activation set + ordered, observable execution.

A stage activated by the plan must have a handler at run time: a missing
handler is a configuration bug and fails fast (§0.2) instead of being skipped
silently. A failing handler records a ``failed`` outcome and re-raises — the
cycle never swallows an error to look successful.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Iterable, Mapping

from app.core.errors import ValidationError
from app.core.time import utc_now

#: The §28 stages in spec order (stable identifiers for plans and traces).
CYCLE_STAGES: tuple[str, ...] = (
    "RECEIVING",
    "AUTHENTICATION",
    "AUTHORIZATION",
    "UNDERSTANDING",
    "REQUIREMENT_EXTRACTION",
    "MEMORY_CHECK",
    "PLAN_GENERATION",
    "TOOL_SOURCE_DISCOVERY",
    "DATA_ACQUISITION",
    "EXTRACTION",
    "NORMALIZATION",
    "QUALITY_CONTROL",
    "SOURCE_CROSS_CHECK",
    "CONFIDENCE_ASSESSMENT",
    "CONTRADICTION_HANDLING",
    "AGENT_DELEGATION",
    "TARGETED_EXTRACTION",
    "RESULT_PACKAGING",
    "PERMISSION_CHECK",
    "DELIVERY",
    "AUDIT",
    "LEARNING_TELEMETRY",
)

#: A stage handler receives the running cycle and returns its result.
StageHandler = Callable[["RequestCycle"], Awaitable[Any]]


def _utc_timestamp() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


@dataclass(slots=True)
class StageOutcome:
    """Execution record for one activated stage."""

    stage: str
    status: str  # "completed" | "failed"
    started_at: str
    finished_at: str
    result: Any = None
    error: str | None = None


class RequestCycle:
    """One request's §28 cycle: activation set + ordered execution."""

    def __init__(
        self,
        request_id: str,
        activated: Iterable[str] | None = None,
    ) -> None:
        """Create the cycle for *request_id*.

        Args:
            request_id: Identifier of the request being processed.
            activated: Stages the plan activates; defaults to all 22 (§28:
                activation is the plan's choice, omitting it keeps the full
                cycle).

        Raises:
            ValidationError: If *request_id* is empty or *activated* contains
                a stage outside :data:`CYCLE_STAGES`.
        """
        if not request_id or not str(request_id).strip():
            raise ValidationError("request_id is required for a request cycle (§28)")
        self.request_id = request_id
        stages = CYCLE_STAGES if activated is None else tuple(activated)
        self._activated: set[str] = set(stages)
        self._validate_stages(self._activated)
        self.outcomes: list[StageOutcome] = []

    def _validate_stages(self, stages: Iterable[str]) -> None:
        unknown = sorted(set(stages) - set(CYCLE_STAGES))
        if unknown:
            raise ValidationError(
                f"unknown §28 stages: {unknown}; valid stages: {list(CYCLE_STAGES)}"
            )

    @property
    def activated(self) -> tuple[str, ...]:
        """Activated stages in canonical §28 order."""
        return tuple(stage for stage in CYCLE_STAGES if stage in self._activated)

    def activate(self, *stages: str) -> None:
        """Add stages to the activation set (order comes from §28)."""
        self._validate_stages(stages)
        self._activated.update(stages)

    def deactivate(self, *stages: str) -> None:
        """Remove stages from the activation set."""
        self._validate_stages(stages)
        self._activated.difference_update(stages)

    async def run(self, handlers: Mapping[str, StageHandler]) -> list[StageOutcome]:
        """Execute every activated stage in §28 order and return outcomes.

        Args:
            handlers: Handlers keyed by stage id; must cover every activated
                stage.

        Returns:
            One :class:`StageOutcome` per executed stage, in §28 order.

        Raises:
            ValidationError: If *handlers* names unknown stages or omits an
                activated one (misconfiguration fails fast, §0.2).
            Exception: Re-raised from a failing handler after recording its
                ``failed`` outcome — errors are never swallowed.
        """
        self._validate_stages(handlers)
        missing = [stage for stage in self.activated if stage not in handlers]
        if missing:
            raise ValidationError(
                f"activated stages without handler: {missing} (§28)"
            )

        self.outcomes.clear()
        for stage in self.activated:
            started_at = _utc_timestamp()
            try:
                result = await handlers[stage](self)
            except Exception as exc:
                self.outcomes.append(
                    StageOutcome(
                        stage=stage,
                        status="failed",
                        started_at=started_at,
                        finished_at=_utc_timestamp(),
                        error=f"{type(exc).__name__}: {exc}",
                    )
                )
                raise
            self.outcomes.append(
                StageOutcome(
                    stage=stage,
                    status="completed",
                    started_at=started_at,
                    finished_at=_utc_timestamp(),
                    result=result,
                )
            )
        return list(self.outcomes)
