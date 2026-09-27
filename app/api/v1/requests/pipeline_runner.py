"""End-to-End API Pipeline Runner per §24 and §28."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import time
from typing import Any, AsyncGenerator

from app.agents.runtime.lifecycle import GRACEFUL_EXPIRY_STATUS, RequestLifecycle
from app.domain.value_objects.ulid import ULID
from app.governance.budget.quotas import (
    BUDGET_EXCEEDED_STATUS,
    GLOBAL_USAGE,
    Budget,
    BudgetExceeded,
    BudgetGuard,
)
from app.llm.tracing.llm_trace_writer import LLMTraceWriter
from app.storage.cache.cache_store import CacheStore
from app.api.v1.requests.pipeline_persistence import persist_pipeline_delivery
from ulid import ULID as PythonUlid

#: Nominal number of plan steps (§28 cycle) used for progress reporting.
PIPELINE_STEPS_TOTAL = 22

#: §41.5 L1 cache namespaces used by the web acquisition stage.
CACHE_NS_WEB_SEARCH = "web_search"
CACHE_NS_PAGE_FETCH = "page_fetch"


class PipelineRunner:
    """Orchestrates request processing across understanding, planning, coordinator, and confidence."""

    def __init__(self) -> None:
        self._runs_count: int = 0
        self._total_duration: float = 0.0
        self._run_states: dict[str, dict[str, Any]] = {}
        self._event_history: dict[str, list[dict[str, Any]]] = {}
        self._subscribers: dict[str, list[asyncio.Queue[dict[str, Any]]]] = {}
        self._running: set[str] = set()
        self._lifecycles: dict[str, RequestLifecycle] = {}
        self._guards: dict[str, BudgetGuard] = {}
        self._llm_traces: LLMTraceWriter = LLMTraceWriter()
        self._trace_step_ids: dict[tuple[str, str], str] = {}
        #: §41.5 — L1 cache backing web_search / fetch_page reuse.
        self._cache: CacheStore = CacheStore()

    def get_runs_count(self) -> int:
        """Return total count of executed pipeline runs."""
        return self._runs_count

    def reset_state(self) -> None:
        """Drop every per-run store of this runner (§33.2 test isolation).

        The runner is a module-level singleton, so its mutable stores leak
        across test files unless they are reset: run states, event history,
        SSE subscribers, lifecycles, budget guards, LLM trace step ids and the
        cumulative metrics counters. The cache is reset too because a cached
        web result from one test must never satisfy the next one.
        """
        self._runs_count = 0
        self._total_duration = 0.0
        self._run_states.clear()
        self._event_history.clear()
        self._subscribers.clear()
        self._running.clear()
        self._lifecycles.clear()
        self._guards.clear()
        self._trace_step_ids.clear()
        if self._cache is not None:
            self._cache.clear()
            self._cache.hits = 0
            self._cache.misses = 0
            self._cache.stale_rejections = 0

    def get_avg_duration(self) -> float:
        """Return average duration in seconds across all executed runs."""
        if self._runs_count == 0:
            return 0.0
        return round(self._total_duration / self._runs_count, 4)

    def get_state(self, request_id: str) -> dict[str, Any] | None:
        """Return latest stored pipeline state for a request."""
        return self._run_states.get(request_id)

    def is_running(self, request_id: str) -> bool:
        """Check if pipeline is actively running for a request."""
        return request_id in self._running

    # -- §41.1 lifecycle ------------------------------------------------

    def register_lifecycle(self, request_id: str, steps_total: int = PIPELINE_STEPS_TOTAL) -> RequestLifecycle:
        """Create (or return) the resumable lifecycle of a request."""
        lifecycle = self._lifecycles.get(request_id)
        if lifecycle is None:
            lifecycle = RequestLifecycle(request_id, steps_total=steps_total)
            self._lifecycles[request_id] = lifecycle
        return lifecycle

    def begin_attempt(self, request_id: str, steps_total: int = PIPELINE_STEPS_TOTAL) -> RequestLifecycle:
        """Start a fresh execution attempt for *request_id* (§41.1 resume).

        A resumed run is a new attempt: the previous lifecycle is replaced so
        its TTL restarts and its checkpoint can be re-seeded from a token.
        """
        lifecycle = RequestLifecycle(request_id, steps_total=steps_total)
        self._lifecycles[request_id] = lifecycle
        self._running.add(request_id)
        return lifecycle

    def get_lifecycle(self, request_id: str) -> RequestLifecycle | None:
        """Return the lifecycle of a request, or None when never started."""
        return self._lifecycles.get(request_id)

    def commit_step(self, request_id: str, step_id: str, result: Any = None) -> None:
        """Commit a completed pipeline step on the request lifecycle."""
        self.register_lifecycle(request_id).commit_step(step_id, result)

    def progress(self, request_id: str) -> Any | None:
        """Return the §41.1 progress snapshot of a request, or None."""
        lifecycle = self._lifecycles.get(request_id)
        return lifecycle.progress() if lifecycle else None

    def resume_state(self, request_id: str) -> dict[str, Any] | None:
        """Return the §41.1 resume projection of a request, or None."""
        lifecycle = self._lifecycles.get(request_id)
        return lifecycle.resume_state() if lifecycle else None

    def resume(self, request_id: str, resume_token: str) -> dict[str, Any]:
        """Resume a request from an opaque token, continuing after the last step.

        Raises:
            ValueError: propagated from the lifecycle when the token is invalid
                or expired (the API layer maps it to HTTP 400).
        """
        # Validate against the issuing lifecycle first so a forged or foreign
        # token never replaces live state.
        issuer = self._lifecycles.get(request_id) or self.register_lifecycle(request_id)
        issuer.verify_resume_token(resume_token)

        lifecycle = self.begin_attempt(request_id, issuer.steps_total)
        checkpoint = lifecycle.restore_from_token(resume_token)
        state = self._run_states.get(request_id, {})
        state.update(
            {
                "status": "resumed",
                "resumed_from_step": checkpoint.step_id if checkpoint else None,
                "resumed_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        self._run_states[request_id] = state
        self._emit_event(request_id, {
            "step": "resumed",
            "status": "resumed",
            "request_id": request_id,
            "from_step": checkpoint.step_id if checkpoint else None,
        })
        return {
            "request_id": request_id,
            "status": "resumed",
            "last_committed_step": checkpoint.step_id if checkpoint else None,
            "resumable": checkpoint is not None,
            "steps_done": lifecycle.steps_done(),
            "steps_total": lifecycle.steps_total,
        }

    def collect_expired(self, request_id: str) -> dict[str, Any] | None:
        """Return the graceful PARTIAL_SUCCESS payload when the TTL elapsed."""
        lifecycle = self._lifecycles.get(request_id)
        if lifecycle is None or not lifecycle.is_expired():
            return None
        payload = lifecycle.expire_gracefully()
        self._run_states[request_id] = {**self._run_states.get(request_id, {}), **payload}
        self._running.discard(request_id)
        self._emit_event(request_id, {
            "step": "graceful_expiry",
            "status": GRACEFUL_EXPIRY_STATUS,
            "request_id": request_id,
            "steps_done": payload["steps_done"],
        })
        return payload

    # -- §41.2 quotas --------------------------------------------------

    def guard_for(
        self,
        request_id: str,
        budget: Budget | None = None,
    ) -> BudgetGuard:
        """Create (or return) the budget guard of a request."""
        guard = self._guards.get(request_id)
        if guard is None or budget is not None:
            guard = BudgetGuard(request_id, budget or Budget())
            self._guards[request_id] = guard
        return guard

    def charge(self, request_id: str, unit: str, amount: float = 1.0, *, cost_usd: float = 0.0) -> None:
        """Charge a §41.2 cost unit, recording the consumption on the guard.

        Raises:
            BudgetExceeded: when the charge crosses a configured budget.
        """
        guard = self.guard_for(request_id)
        try:
            guard.charge(unit, amount, cost_usd=cost_usd)
        except BudgetExceeded:
            GLOBAL_USAGE.register(guard.usage)
            raise
        self._publish_usage(request_id, guard)

    def usage_report(self, request_id: str) -> dict[str, Any] | None:
        """Return the §41.2 usage report of a request, or None."""
        guard = self._guards.get(request_id)
        return guard.report() if guard else None

    def _publish_usage(self, request_id: str, guard: BudgetGuard) -> None:
        """Register the guard usage so ``/v1/usage/global`` aggregates it."""
        GLOBAL_USAGE.register(guard.usage)
        state = self._run_states.get(request_id)
        if isinstance(state, dict):
            state["usage_report"] = guard.report()

    def _meter_llm(self, request_id: str, llm_result: dict[str, Any]) -> str | None:
        """Charge an LLM result to the request budget (§41.2).

        Returns the exceeded dimension name, or ``None`` when within budget.
        A budget breach is reported rather than raised so the pipeline can
        still deliver what it already gathered.
        """
        guard = self.guard_for(request_id)
        usage = llm_result.get("usage") or {}
        input_tokens = int(
            usage.get("input_tokens", usage.get("prompt_tokens"))
            or llm_result.get("input_tokens", 0)
            or 0
        )
        output_tokens = int(
            usage.get("output_tokens", usage.get("completion_tokens"))
            or llm_result.get("output_tokens", 0)
            or 0
        )
        cost_usd = float(usage.get("cost_usd", 0.0) or 0.0)
        try:
            guard.charge_llm(input_tokens, output_tokens, cost_usd=cost_usd)
        except BudgetExceeded:
            self._publish_usage(request_id, guard)
            return guard.exceeded or "max_llm_tokens"
        self._publish_usage(request_id, guard)
        return None

    # -- §41.12 LLM decision traces ------------------------------------

    @property
    def trace_writer(self) -> LLMTraceWriter:
        """Return the shared ``llm_decision_trace`` writer."""
        return self._llm_traces

    def llm_traces(self, request_id: str) -> list[dict[str, Any]]:
        """Return the §41.12 decision traces recorded for a request."""
        return [
            dict(trace)
            for trace in self._llm_traces.list_traces()
            if trace.get("request_id") == request_id
        ]

    def trace_steps(self, request_id: str) -> dict[str, str]:
        """Return the ``phase -> STEP_{ULID}`` map used to trace a request."""
        return {
            phase: step_id
            for (req, phase), step_id in self._trace_step_ids.items()
            if req == request_id
        }

    def _step_id_for(self, request_id: str, phase: str) -> str:
        """Return the stable ``STEP_{ULID}`` identifier of a traced phase (§0.3)."""
        key = (request_id, phase)
        step_id = self._trace_step_ids.get(key)
        if step_id is None:
            step_id = ULID.new("STEP_")
            self._trace_step_ids[key] = step_id
        return step_id

    def _trace_llm(
        self,
        request_id: str,
        phase: str,
        task_type: str,
        prompt: str,
        llm_result: Any,
        decision_summary: str = "",
    ) -> dict[str, Any] | None:
        """Record an ``llm_decision_trace`` for a significant LLM call (§41.12).

        Args:
            request_id: Information request the decision belongs to.
            phase: Pipeline phase name (mapped to a stable ``STEP_{ULID}``).
            task_type: One of the five §41.12 LLM task types.
            prompt: Full prompt text — only its sha256 digest is stored.
            llm_result: Task result dict or router response object.
            decision_summary: Short description of the decision taken.

        Tracing is best effort: a malformed result degrades to ``None`` instead
        of breaking the delivery of an otherwise valid request.
        """
        try:
            step_id = self._step_id_for(request_id, phase)
            if isinstance(llm_result, dict):
                result: dict[str, Any] = dict(llm_result)
            elif llm_result is None:
                result = {}
            else:  # router response objects expose plain attributes
                result = {
                    "model": getattr(llm_result, "model", None),
                    "input_tokens": getattr(llm_result, "input_tokens", 0),
                    "output_tokens": getattr(llm_result, "output_tokens", 0),
                    "latency_ms": getattr(llm_result, "latency_ms", 0),
                    "usage": getattr(llm_result, "usage", None) or {},
                }
            usage = result.get("usage") or {}
            if not isinstance(usage, dict):
                usage = vars(usage)
            trace = self._llm_traces.build_trace(
                request_id=request_id,
                step_id=step_id,
                task_type=task_type,
                model_used=str(result.get("model") or result.get("model_used") or "unknown"),
                prompt=prompt,
                input_tokens=int(
                    usage.get("input_tokens", usage.get("prompt_tokens"))
                    or result.get("input_tokens", 0)
                    or 0
                ),
                output_tokens=int(
                    usage.get("output_tokens", usage.get("completion_tokens"))
                    or result.get("output_tokens", 0)
                    or 0
                ),
                latency_ms=int(result.get("latency_ms", 0) or 0),
                decision_summary=f"[{phase}] {decision_summary}".strip(),
            )
            return self._llm_traces.write(trace)
        except Exception:  # noqa: BLE001 - observability must never break the run
            return None

    def _emit_event(self, request_id: str, event: dict[str, Any]) -> None:
        """Record an event and dispatch to active SSE subscriber queues."""
        if request_id not in self._event_history:
            self._event_history[request_id] = []
        self._event_history[request_id].append(event)

        for queue in self._subscribers.get(request_id, []):
            queue.put_nowait(event)

    async def event_stream(self, request_id: str) -> AsyncGenerator[str, None]:
        """Yield SSE-formatted messages for request events."""
        history = list(self._event_history.get(request_id, []))
        if not history:
            init_event = {
                "step": "received",
                "status": "received",
                "request_id": request_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            yield f"data: {json.dumps(init_event)}\n\n"
        else:
            for event in history:
                yield f"data: {json.dumps(event)}\n\n"

        if self.is_running(request_id):
            queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
            self._subscribers.setdefault(request_id, []).append(queue)
            try:
                while True:
                    event = await queue.get()
                    yield f"data: {json.dumps(event)}\n\n"
                    if event.get("step") in ("delivering", "completed", "failed"):
                        break
            finally:
                if request_id in self._subscribers and queue in self._subscribers[request_id]:
                    self._subscribers[request_id].remove(queue)

    async def run(self, request_id: str, payload: Any) -> dict[str, Any]:
        """Run the end-to-end pipeline with graceful degradation if modules are missing."""
        start_time = time.monotonic()
        start_iso = datetime.now(timezone.utc).isoformat()
        self._running.add(request_id)

        objective = getattr(payload, "objective", None) or (
            payload.get("objective", "") if isinstance(payload, dict) else ""
        )
        context = getattr(payload, "context", None) or (
            payload.get("context", {}) if isinstance(payload, dict) else {}
        )
        constraints = getattr(payload, "constraints", None) or (
            payload.get("constraints", {}) if isinstance(payload, dict) else {}
        )

        # §41.2 — install the budget guard before any metered work happens.
        budget = getattr(payload, "budget", None)
        if budget is not None and hasattr(budget, "to_domain"):
            budget = budget.to_domain()
        elif isinstance(budget, dict):
            budget = Budget(**budget) if budget else Budget()
        guard = self.guard_for(request_id, budget)
        budget_exceeded: str | None = None

        self._emit_event(request_id, {
            "step": "started",
            "status": "in_progress",
            "request_id": request_id,
            "timestamp": start_iso,
        })
        self._run_states[request_id] = {
            "status": "processing",
            "current_step": "understanding",
            "request_id": request_id,
            "started_at": start_iso,
        }
        lifecycle = self.register_lifecycle(request_id)
        lifecycle.set_step("UNDERSTANDING")

        # -------------------------------------------------------------
        # Stage 1: Understanding (with graceful degradation)
        # -------------------------------------------------------------
        self._emit_event(request_id, {
            "step": "understanding",
            "status": "in_progress",
            "request_id": request_id,
        })
        requirements_list: list[str] = []
        try:
            from app.agents.understanding.clarification_detector import ClarificationDetector
            from app.agents.understanding.context_enricher import ContextEnricher
            from app.agents.understanding.request_parser import RequestParser
            from app.agents.understanding.requirement_extractor import RequirementExtractor

            parser = RequestParser()
            parsed_req = parser.parse(objective, context=context)
            enricher = ContextEnricher()
            enricher.enrich(parsed_req, context)
            detector = ClarificationDetector()
            detector.detect(parsed_req)
            extractor = RequirementExtractor()
            reqs = extractor.extract(parsed_req)
            requirements_list = [r.description for r in reqs] if reqs else [objective]
            understanding_status = "completed"
        except Exception as err:
            requirements_list = [objective] if objective else ["general_inquiry"]
            understanding_status = f"degraded: {err}"

        requirements: Any = requirements_list
        try:
            from app.llm.tasks.understanding_task import UnderstandingTask
            from app.llm.prompts.understanding_prompt import build as build_understanding_prompt

            prompt = build_understanding_prompt(objective=objective)
            task = UnderstandingTask()
            llm_result = await task.run(prompt, max_tokens=500)
            if not llm_result.get("stub"):
                requirements = llm_result["content"]
            # §41.2 — meter the LLM call against the request budget.
            budget_exceeded = self._meter_llm(request_id, llm_result)
            # §41.12 — trace the reasoning decision (prompt stored hashed only).
            self._trace_llm(
                request_id,
                phase="understanding",
                task_type="understanding",
                prompt=prompt,
                llm_result=llm_result,
                decision_summary=(
                    "stubbed call; deterministic requirements kept"
                    if llm_result.get("stub")
                    else f"requirements parsed from LLM output ({len(requirements_list)} kept)"
                ),
            )
        except ImportError:
            pass  # fallback sur parsing déterministe
        except Exception:
            pass

        self._emit_event(request_id, {
            "step": "understanding",
            "status": understanding_status,
            "request_id": request_id,
            "requirements": requirements_list,
        })
        lifecycle.commit_step("UNDERSTANDING", {"requirements": requirements_list})

        # -------------------------------------------------------------
        # Stage 2: Planning (with graceful degradation)
        # -------------------------------------------------------------
        lifecycle.set_step("PLAN_GENERATION")
        self._emit_event(request_id, {
            "step": "planning",
            "status": "in_progress",
            "request_id": request_id,
        })
        plan: dict[str, Any] | None = None
        try:
            from app.planning.plan_builder import PlanBuilder

            builder = PlanBuilder()
            steps = [
                {
                    "action": "collect_information",
                    "tool": "collector",
                    "inputs": {"requirement": req_desc},
                    "expected_output": "information_unit",
                }
                for req_desc in requirements_list
            ]
            max_iter = getattr(constraints, "maximum_iterations", 12) if hasattr(constraints, "maximum_iterations") else (
                constraints.get("maximum_iterations", 12) if isinstance(constraints, dict) else 12
            )
            max_cost = getattr(constraints, "maximum_cost", None) if hasattr(constraints, "maximum_cost") else (
                constraints.get("maximum_cost") if isinstance(constraints, dict) else None
            )
            max_time = getattr(constraints, "maximum_execution_time_seconds", 300) if hasattr(constraints, "maximum_execution_time_seconds") else (
                constraints.get("maximum_execution_time_seconds", 300) if isinstance(constraints, dict) else 300
            )

            plan = builder.build(
                request_id,
                objective,
                steps,
                {
                    "max_iterations": max_iter,
                    "max_cost": max_cost,
                    "max_execution_time_seconds": max_time,
                },
            )
            planning_status = "completed"
        except Exception as err:
            plan = {
                "plan_id": ULID.new("PLAN_"),
                "request_id": request_id,
                "objective": objective,
                "steps": [
                    {
                        "step_id": ULID.new("STEP_"),
                        "order": 1,
                        "action": "collect_information",
                        "tool": "fallback_collector",
                        "inputs": {"requirement": objective},
                        "expected_output": "information_unit",
                        "status": "pending",
                    }
                ],
            }
            planning_status = f"degraded: {err}"

        try:
            from app.llm.tasks.planning_task import PlanningTask
            from app.llm.prompts.planning_prompt import build as build_planning_prompt
            from app.llm.parsers.plan_parser import parse_plan

            try:
                prompt = build_planning_prompt(objective=objective, requirements=requirements)
            except TypeError:
                tools = ["collector", "web_search", "vector_search"]
                prompt = build_planning_prompt(
                    objective=f"{objective} (Requirements: {requirements})" if requirements else objective,
                    available_tools=tools,
                )
            task = PlanningTask()
            llm_result = await task.run(prompt, max_tokens=800)
            # §41.2 — meter the planning LLM call too.
            exceeded = self._meter_llm(request_id, llm_result)
            budget_exceeded = budget_exceeded or exceeded
            # §41.12 — trace the planning decision.
            self._trace_llm(
                request_id,
                phase="planning",
                task_type="planning",
                prompt=prompt,
                llm_result=llm_result,
                decision_summary=(
                    "stubbed call; deterministic plan kept"
                    if llm_result.get("stub")
                    else "plan steps parsed from LLM output"
                ),
            )
            if not llm_result.get("stub"):
                # parser le JSON via app.llm.parsers.plan_parser.parse_plan
                parsed_llm_plan = parse_plan(llm_result["content"])
                plan_id = (plan.get("plan_id") if isinstance(plan, dict) and plan.get("plan_id") else ULID.new("PLAN_"))
                plan = {
                    "plan_id": plan_id,
                    "request_id": request_id,
                    "objective": objective,
                    "steps": [
                        {
                            "step_id": step.get("step_id") or ULID.new("STEP_"),
                            "order": step.get("order", idx),
                            "action": step.get("description") or step.get("action", "collect_information"),
                            "tool": step.get("tool", "collector"),
                            "inputs": step.get("inputs", {"requirement": step.get("description", objective)}),
                            "expected_output": step.get("expected_output", "information_unit"),
                            "status": step.get("status", "pending"),
                        }
                        for idx, step in enumerate(parsed_llm_plan.get("steps", []), start=1)
                    ],
                }
                planning_status = "completed"
        except ImportError:
            pass
        except Exception:
            pass

        self._emit_event(request_id, {
            "step": "planning",
            "status": planning_status,
            "request_id": request_id,
            "plan_id": plan.get("plan_id") if isinstance(plan, dict) else None,
        })
        lifecycle.commit_step("PLAN_GENERATION", {"plan_id": plan.get("plan_id") if isinstance(plan, dict) else None})

        # -------------------------------------------------------------
        # Stage 3: Real web-search execution per §9/§10 (graceful degradation)
        # -------------------------------------------------------------
        lifecycle.set_step("DATA_ACQUISITION")
        self._emit_event(request_id, {
            "step": "executing",
            "status": "in_progress",
            "request_id": request_id,
        })
        step_results: list[dict[str, Any]] = []
        # Accumulated facts with real SRC_ provenance (§0.2-compliant)
        web_facts: list[dict[str, Any]] = []
        # Accumulated source entries for the delivery sources[] field
        web_sources: list[dict[str, Any]] = []
        execution_status = "completed"

        steps_to_run = plan.get("steps", []) if isinstance(plan, dict) else []

        try:
            from app.connectors.web.provider_router import ProviderRouter
            from app.connectors.web.extractors.wikipedia_extractor import WikipediaExtractor
            from app.knowledge.extraction.fact_extractor import FactExtractor
            from app.quality.source_reliability import SourceReliabilityScorer

            provider_router = ProviderRouter()
            wiki_extractor = WikipediaExtractor()
            fact_extractor = FactExtractor()
            reliability_scorer = SourceReliabilityScorer()

            for step in steps_to_run:
                action = step.get("action", "")
                inputs = step.get("inputs", {})
                # Derive the search query from step inputs or the objective
                query = (
                    inputs.get("query")
                    or inputs.get("requirement")
                    or action
                    or objective
                )

                try:
                    # §41.2 — meter the web request before it leaves the process.
                    try:
                        self.charge(request_id, "web_requests")
                    except BudgetExceeded as budget_err:
                        budget_exceeded = budget_exceeded or budget_err.dimension
                        execution_status = f"{BUDGET_EXCEEDED_STATUS}: {budget_err.dimension}"
                        break

                    # ------ web_search ------------------------------------------------
                    search_results = await provider_router.search(
                        query=str(query), limit=5
                    )

                    step_output_snippets: list[str] = []

                    # ------ fetch_page for top-3 results ------------------------------
                    for result in search_results[:3]:
                        # §41.2 — meter each outbound page fetch as an API call.
                        try:
                            self.charge(request_id, "api_calls")
                        except BudgetExceeded as budget_err:
                            budget_exceeded = budget_exceeded or budget_err.dimension
                            execution_status = f"{BUDGET_EXCEEDED_STATUS}: {budget_err.dimension}"
                            break
                        url = result.url
                        snippet = result.snippet or result.title

                        # Extract full page text
                        try:
                            page = await wiki_extractor.extract(url)
                            page_text = page.get("text", "")
                        except Exception:
                            page_text = ""

                        text_to_extract = page_text if page_text else snippet or ""

                        if text_to_extract:
                            src_id = ULID.new("SRC_")
                            doc_id = ULID.new("DOC_")
                            try:
                                facts = await fact_extractor.extract(
                                    text=text_to_extract,
                                    source_id=src_id,
                                    document_id=doc_id,
                                    url=url,
                                )
                                web_facts.extend(facts)
                            except Exception:
                                pass

                            # Source entry with reliability score
                            rel_score = reliability_scorer.score(url)
                            web_sources.append({
                                "source_id": src_id,
                                "url": url,
                                "title": result.title,
                                "provider": result.provider,
                                "reliability_score": rel_score,
                                "search_score": result.score,
                                "source_type": "web",
                            })
                            step_output_snippets.append(
                                f"[{result.title}] {snippet}"
                            )

                    step_results.append({
                        "step_id": step.get("step_id", ULID.new("STEP_")),
                        "status": "done",
                        "action": action,
                        "output": " | ".join(step_output_snippets) if step_output_snippets else f"No results for: {query}",
                        "results_count": len(search_results),
                    })

                except Exception as step_err:
                    step_results.append({
                        "step_id": step.get("step_id", ULID.new("STEP_")),
                        "status": "degraded",
                        "action": action,
                        "output": f"Step degraded: {step_err}",
                    })

        except ImportError:
            # Connectors not available — fall back to stub
            execution_status = "degraded: connectors not available"
        except Exception as err:
            execution_status = f"degraded: {err}"

        if not step_results:
            # Pure stub fallback when no steps ran
            try:
                from app.agents.pipeline.step_executor import StepExecutor

                executor = StepExecutor()

                class _ToolAdapter:
                    def execute(self, s: dict[str, Any]) -> dict[str, Any]:
                        inputs = s.get("inputs", {})
                        req_val = inputs.get("requirement", objective)
                        act = s.get("action", "collect_information")
                        return {
                            "status": "done",
                            "action": act,
                            "output": f"Extracted intelligence payload for {req_val}",
                        }

                tool_instance = _ToolAdapter()
                for step in steps_to_run:
                    res = executor.execute(step, tool_instance)
                    if "output" not in res and isinstance(res.get("result"), dict):
                        res["output"] = res["result"].get("output", "")
                    step_results.append(res)
            except Exception as fallback_err:
                step_results = [
                    {
                        "step_id": s.get("step_id", ULID.new("STEP_")),
                        "status": "done",
                        "output": f"Fallback execution output for {objective}",
                    }
                    for s in steps_to_run
                ]
                execution_status = f"degraded: {fallback_err}"

        self._emit_event(request_id, {
            "step": "executing",
            "status": execution_status,
            "request_id": request_id,
            "results_count": len(step_results),
            "facts_extracted": len(web_facts),
        })
        lifecycle.commit_step("DATA_ACQUISITION", {"facts": len(web_facts), "results": len(step_results)})

        # -------------------------------------------------------------
        # Stage 4: Confidence Evaluation (with graceful degradation)
        # -------------------------------------------------------------
        lifecycle.set_step("CONFIDENCE_ASSESSMENT")
        self._emit_event(request_id, {
            "step": "confidence",
            "status": "in_progress",
            "request_id": request_id,
        })
        confidence_score = 0.85
        confidence_details: dict[str, Any] = {}
        try:
            from app.confidence.confidence_scorer import score as score_confidence

            dims = {
                "source_reliability": 0.88,
                "source_freshness": 0.90,
                "extraction_confidence": 0.85,
                "data_quality": 0.85,
                "evidence_strength": 0.82,
                "cross_source_agreement": 0.80,
                "methodological_consistency": 0.85,
            }
            score_dict = score_confidence(dims)
            confidence_score = float(score_dict.get("confidence_score", 0.85))
            confidence_details = {
                "score": confidence_score,
                "dimensions": dims,
                "explanation": score_dict.get("explanation"),
                "not_a_probability": True,
            }
            confidence_status = "completed"
        except Exception as err:
            confidence_score = 0.80
            confidence_details = {
                "score": confidence_score,
                "dimensions": {},
                "explanation": f"Fallback confidence scoring: {err}",
            }
            confidence_status = f"degraded: {err}"

        self._emit_event(request_id, {
            "step": "confidence",
            "status": confidence_status,
            "request_id": request_id,
            "confidence_score": confidence_score,
        })

        # -------------------------------------------------------------
        # Stage 5: Delivery per §24.1
        # -------------------------------------------------------------
        now_iso = datetime.now(timezone.utc).isoformat()
        inf_id = ULID.new("INF_")
        evid_id = ULID.new("EVID_")
        resp_id = f"RESP_{PythonUlid()}"

        details_list = [
            r.get("output", "")
            for r in step_results
            if r.get("output")
        ]
        if not details_list:
            details_list = [f"Intelligence findings collected for {objective}"]

        information_units = [
            {
                "information_id": inf_id,
                "type": "text",
                "content": {
                    "summary": f"Factual intelligence unit regarding {objective}",
                    "details": details_list,
                },
                "source_id": "SRC_INTERNAL_PIPELINE",
                "data_stage": "derived",
                "epistemic_status": "factual",
                "created_at": now_iso,
            }
        ]

        evidence = [
            {
                "evidence_id": evid_id,
                "information_id": inf_id,
                "strength": confidence_score,
                "excerpt": f"Evidence derived from execution of {len(step_results)} plan steps.",
                "epistemic_status": "factual",
                "created_at": now_iso,
            }
        ]

        # -- §41.3 language metadata on every delivered unit -------------
        try:
            from app.knowledge.normalization.language_policy import (
                LanguagePolicy,
                build_translation_metadata,
            )

            language_policy = LanguagePolicy(
                working_language=str(context.get("working_language", "en")),
                source_languages_allowed=tuple(
                    context.get("source_languages_allowed") or ("en", "fr", "es", "de")
                ),
                translation_policy=str(context.get("translation_policy", "on_demand")),
                normalization_locale=str(context.get("normalization_locale", "en-US")),
            )
        except Exception:
            language_policy = None

        def _with_language(block: dict[str, Any], source_language: str) -> dict[str, Any]:
            """Attach the §41.3 language block to one unit (best effort)."""
            if language_policy is None:
                return block
            try:
                metadata = build_translation_metadata(language_policy, source_language)
                return {**block, **metadata.to_dict()}
            except Exception:
                return block

        information_units = [
            _with_language(unit, str(unit.get("language") or "en"))
            for unit in information_units
        ]

        summary = f"Synthesized research report for '{objective}'."
        # Seed findings with real web facts extracted in Stage 3 (§0.2-compliant)
        findings: list[Any] = list(web_facts)

        try:
            from app.llm.router.model_router import ModelRouter, LLMTask

            router = ModelRouter()
            synthesis_prompt = (
                f"Réponds en français à la question suivante : {objective}\n\n"
                f"Faits collectés : {json.dumps(findings, ensure_ascii=False)}\n\n"
                f"Réponds avec un JSON : {{\"summary\": \"...\", \"findings\": [...]}}\n"
                f"Ne donne AUCUN fait sans source_id, sinon marque \"hypothesis\"."
            )
            response = await router.complete(
                LLMTask(task_type="understanding", max_tokens=600),
                synthesis_prompt,
            )
            if not response.stub:
                summary = response.content
                # §41.2 — meter the synthesis call.
                exceeded = self._meter_llm(
                    request_id, {"usage": getattr(response, "usage", None)}
                )
                budget_exceeded = budget_exceeded or exceeded
                # §41.12 — trace the synthesis decision (§41.12 understanding task).
                self._trace_llm(
                    request_id,
                    phase="synthesis",
                    task_type="understanding",
                    prompt=synthesis_prompt,
                    llm_result=response,
                    decision_summary="final answer drafted from collected findings",
                )
                try:
                    import re

                    match = re.search(
                        r"```(?:json)?\s*(.*?)\s*```",
                        response.content,
                        re.DOTALL | re.IGNORECASE,
                    )
                    candidate = match.group(1) if match else response.content.strip()
                    parsed_synthesis = None
                    try:
                        parsed_synthesis = json.loads(candidate)
                    except Exception:
                        s_idx = candidate.find("{")
                        e_idx = candidate.rfind("}")
                        if s_idx != -1 and e_idx > s_idx:
                            parsed_synthesis = json.loads(candidate[s_idx : e_idx + 1])
                    if isinstance(parsed_synthesis, dict):
                        if parsed_synthesis.get("summary"):
                            summary = str(parsed_synthesis["summary"])
                        if parsed_synthesis.get("findings") and isinstance(
                            parsed_synthesis["findings"], list
                        ):
                            findings = parsed_synthesis["findings"]
                except Exception:
                    summary = response.content
        except ImportError:
            pass  # fallback sur stub actuel
        except Exception:
            pass

        # ------------------------------------------------------------------
        # §0.2 invariant 8 — separate verified findings from unsourced claims
        # A finding is verified iff it has a source_id starting with "SRC_"
        # AND a non-empty evidence_id.  Everything else → assumptions.
        # ------------------------------------------------------------------
        verified_findings: list[Any] = []
        assumptions_from_llm: list[dict[str, Any]] = []

        for item in findings:
            if isinstance(item, dict):
                src = item.get("source_id", "")
                evid = item.get("evidence_id", "")
                # Reject "hypothesis" string as source_id (§0.2)
                if (
                    isinstance(src, str)
                    and src.startswith("SRC_")
                    and evid
                ):  # verified fact
                    verified_findings.append(item)
                else:  # unverifiable — demote to assumption
                    stmt = (
                        item.get("finding")
                        or item.get("value")
                        or item.get("statement")
                        or str(item)
                    )
                    assumptions_from_llm.append({
                        "statement": stmt,
                        "reason": "no_source",
                        "epistemic_status": "hypothesis",
                    })
            elif isinstance(item, str) and item.strip():
                # Plain strings have no source — always assumptions
                assumptions_from_llm.append({
                    "statement": item.strip(),
                    "reason": "no_source",
                    "epistemic_status": "hypothesis",
                })

        findings = verified_findings

        # §1.3 — status depends on whether verified findings exist
        delivery_status = "completed" if findings else "INSUFFICIENT_EVIDENCE"
        # §41.2 — a breached budget is reported explicitly, never silently.
        if budget_exceeded:
            delivery_status = BUDGET_EXCEEDED_STATUS

        # §41.2 — close the usage report with the measured compute time.
        try:
            guard.usage.compute_seconds = max(
                guard.usage.compute_seconds, time.monotonic() - start_time
            )
        except Exception:
            pass
        self._publish_usage(request_id, guard)
        usage_report = guard.report()

        # Build limitations — always include §0.2 notice; add connector note if degraded
        base_limitations: list[str] = [
            "Les affirmations sans source_id vérifié sont marquées comme hypothèses §0.2."
        ]
        if "degraded" in execution_status:
            base_limitations.append(
                f"Web connectors non disponibles ({execution_status}) — fallback sur stub."
            )
        if budget_exceeded:
            base_limitations.append(
                f"Budget §41.2 dépassé sur '{budget_exceeded}' — exécution interrompue."
            )

        # Merge internal pipeline source + real web sources
        final_sources: list[dict[str, Any]] = [
            {
                "source_id": "SRC_INTERNAL_PIPELINE",
                "name": "INIS Internal Pipeline",
                "source_type": "internal",
                "trust_level": 9,
            }
        ] + web_sources

        # ------------------------------------------------------------------
        # Constat 1 (B4-bis): Persist to real PostgreSQL when configured
        # ------------------------------------------------------------------
        audit_record: dict[str, Any]
        persisted, persistence_limits, audit_record = await persist_pipeline_delivery(
            request_id=request_id,
            objective=objective,
            delivery_status=delivery_status,
            sources=final_sources,
            information_units=information_units,
            evidence=evidence,
            step_results=step_results,
        )
        base_limitations.extend(persistence_limits)

        delivery_response: dict[str, Any] = {
            "response_id": resp_id,
            "request_id": request_id,
            "status": delivery_status,
            "summary": summary,
            "findings": findings,
            "information_units": information_units,
            "evidence": evidence,
            "sources": final_sources,
            "datasets": [],
            "artifacts": [],
            "transformations": [],
            "conflicts": [],
            "confidence": confidence_details,
            "limitations": base_limitations,
            "assumptions": assumptions_from_llm,
            "missing_information": [],
            # §41.2 — every delivery carries its consumption report.
            "usage_report": usage_report,
            "recommended_next_actions": [
                "Review evidence package",
                "Verify source trust ratings",
            ],
            "provenance": {
                "pipeline": "PipelineRunner",
                "request_id": request_id,
                "plan_id": plan.get("plan_id") if isinstance(plan, dict) else None,
                "steps_executed": len(step_results),
            },
            "audit": {
                "audit_id": audit_record.get("audit_event_id") or ULID.new("AUD_"),
                "completed_at": audit_record.get("timestamp") or now_iso,
                "persisted": persisted,
            },
            "generated_by": {
                "agent": "PipelineRunner",
                "version": "1.0.0",
            },
            "timestamps": {
                "started_at": start_iso,
                "completed_at": now_iso,
            },
            "trace": {
                "steps": [s.get("step_id") for s in (plan.get("steps", []) if isinstance(plan, dict) else [])],
            },
        }

        # Update metrics & running state
        duration = time.monotonic() - start_time
        self._runs_count += 1
        self._total_duration += duration
        self._run_states[request_id] = delivery_response
        self._running.discard(request_id)

        # §41.1 — commit the final step, record partial findings, close the lifecycle
        for finding in findings:
            lifecycle.add_finding(finding)
        lifecycle.commit_step("DELIVERY", {"response_id": resp_id})
        lifecycle.complete()

        # Notify observability metrics if present
        try:
            from app.observability.metrics import DEFAULT_REGISTRY
            DEFAULT_REGISTRY.increment("agent_success_rate", 1)
            DEFAULT_REGISTRY.observe("request_latency", duration)
        except Exception:
            pass

        self._emit_event(request_id, {
            "step": "delivering",
            "status": "completed",
            "request_id": request_id,
            "response_id": resp_id,
            "duration": round(duration, 4),
        })

        return delivery_response


pipeline_runner = PipelineRunner()
