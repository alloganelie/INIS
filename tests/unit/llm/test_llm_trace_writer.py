"""Unit tests for the §41.12 LLM decision trace writer."""

import pytest

from app.core.errors import ValidationError
from app.llm.tracing.llm_trace_writer import (
    LLM_DECISION_TRACE_TABLE,
    REQUIRED_FIELDS,
    TASK_TYPES,
    LLMTraceWriter,
)
from app.llm.tracing.prompt_hasher import hash_prompt, verify_prompt


def _trace(**overrides):
    trace = LLMTraceWriter.build_trace(
        request_id="REQ_01TEST",
        step_id="STEP_01TEST",
        task_type="planning",
        model_used="claude-sonnet",
        prompt="plan the research",
        input_tokens=120,
        output_tokens=48,
        latency_ms=742,
        decision_summary="3 steps planned",
        alternatives_considered=["single step"],
        confidence_in_decision=0.8,
    )
    trace.update(overrides)
    return trace


def test_build_trace_hashes_the_prompt() -> None:
    trace = LLMTraceWriter.build_trace(
        request_id="REQ_1",
        step_id="STEP_1",
        task_type="understanding",
        model_used="claude-sonnet",
        prompt="données confidentielles",
    )
    assert trace["prompt_hash"] == hash_prompt("données confidentielles")
    assert "confidentielles" not in repr(trace)


def test_build_trace_generates_ulid_and_timestamp() -> None:
    trace = _trace()
    assert trace["llm_decision_id"]
    assert trace["timestamp"].tzinfo is not None
    assert trace["alternatives_considered"] == ["single step"]


def test_write_stores_a_complete_trace() -> None:
    writer = LLMTraceWriter()
    stored = writer.write(_trace())
    assert stored["task_type"] == "planning"
    assert stored["latency_ms"] == 742
    assert len(writer.list_traces()) == 1


def test_write_accepts_every_required_task_type() -> None:
    writer = LLMTraceWriter()
    for task_type in sorted(TASK_TYPES):
        writer.write(_trace(task_type=task_type))
    assert [t["task_type"] for t in writer.list_traces()] == sorted(TASK_TYPES)


@pytest.mark.parametrize("missing", sorted(REQUIRED_FIELDS))
def test_write_rejects_missing_required_field(missing: str) -> None:
    trace = _trace()
    trace.pop(missing)
    with pytest.raises(ValidationError, match="missing fields"):
        LLMTraceWriter().write(trace)


def test_write_rejects_unknown_task_type() -> None:
    with pytest.raises(ValidationError, match="Invalid task_type"):
        LLMTraceWriter().write(_trace(task_type="summarize"))


def test_write_rejects_clear_text_prompt_hash() -> None:
    with pytest.raises(ValidationError, match="sha256 hex digest"):
        LLMTraceWriter().write(_trace(prompt_hash="plan the research"))


@pytest.mark.parametrize("score", [-0.1, 1.5, "high"])
def test_write_rejects_out_of_range_confidence(score) -> None:
    with pytest.raises(ValidationError, match="confidence_in_decision"):
        LLMTraceWriter().write(_trace(confidence_in_decision=score))


def test_list_traces_returns_copies_oldest_first() -> None:
    writer = LLMTraceWriter()
    writer.write(_trace(decision_summary="first"))
    writer.write(_trace(decision_summary="second"))
    traces = writer.list_traces()
    assert [t["decision_summary"] for t in traces] == ["first", "second"]
    traces[0]["decision_summary"] = "mutated"
    assert writer.list_traces()[0]["decision_summary"] == "first"


def test_clear_drops_in_memory_traces() -> None:
    writer = LLMTraceWriter()
    writer.write(_trace())
    writer.clear()
    assert writer.list_traces() == []


def test_persist_requires_an_engine() -> None:
    with pytest.raises(ValidationError, match="requires an engine"):
        LLMTraceWriter().persist()


def test_write_persists_rows_to_bound_engine() -> None:
    from sqlalchemy import create_engine, select

    engine = create_engine("sqlite://")
    writer = LLMTraceWriter(engine=engine)
    writer.write(_trace())
    writer.write(_trace(task_type="classification"))

    with engine.connect() as connection:
        rows = connection.execute(select(LLM_DECISION_TRACE_TABLE)).mappings().all()

    assert len(rows) == 2
    assert rows[0]["request_id"] == "REQ_01TEST"
    assert rows[0]["alternatives_considered"] == '["single step"]'
    assert verify_prompt("plan the research", rows[0]["prompt_hash"]) is True


def test_persist_is_idempotent_per_row_id() -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.exc import IntegrityError

    engine = create_engine("sqlite://")
    writer = LLMTraceWriter()
    writer.write(_trace())
    assert writer.persist(engine) == 1
    with pytest.raises(IntegrityError):
        writer.persist(engine)  # same primary key twice
