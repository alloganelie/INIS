"""§20/§17.1 — « mémoire utilisée » doit être auditable.

Un run qui réutilise une unité d'un run précédent change ce qu'il livre : sans
événement d'audit, on ne peut ni expliquer ni reproduire la décision « cette
information était déjà en mémoire ». Le payload est construit par une fonction
pure (:func:`app.knowledge.memory.memory_audit_payload`) pour rester testable
sans base — et il doit être accepté par l'``AuditWriter`` tel quel, sinon la
trace disparaît au moment de l'écriture.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.domain.entities.memory_result import MemoryResult
from app.governance.audit.audit_writer import AuditWriter
from app.knowledge.memory import memory_audit_payload

REQUEST_ID = "REQ_01M3Q0000000000000000000A1"
UNIT_ID = "INF_01M3Q0000000000000000000A2"


def _sufficient() -> dict[str, Any]:
    """Return the ``MemoryResult.to_dict()`` projection of a successful reuse."""
    return MemoryResult(
        sufficient=True,
        items=(),
        reason=None,
        question="Quelle est la capitale de la France ?",
    ).to_dict() | {"information_ids": [UNIT_ID]}


def _insufficient() -> dict[str, Any]:
    """Return the projection of a lookup that found nothing reusable."""
    return MemoryResult(
        sufficient=False,
        items=(),
        reason="no candidate found",
        question="Quelle est la capitale de la France ?",
    ).to_dict()


class TestThePayloadSaysWhatHappened:
    """§0.2 — l'événement distingue « réutilisé » de « rien de réutilisable »."""

    def test_a_reuse_is_a_success(self) -> None:
        payload = memory_audit_payload(REQUEST_ID, _sufficient(), mode="hybrid")

        assert payload["action"] == "memory_lookup"
        assert payload["resource_type"] == "information_unit"
        assert payload["resource_id"] == UNIT_ID
        assert payload["request_id"] == REQUEST_ID
        assert payload["result"] == "success"

    def test_a_miss_is_degraded_and_carries_the_reason(self) -> None:
        payload = memory_audit_payload(REQUEST_ID, _insufficient(), mode="hybrid")

        assert payload["result"] == "degraded"
        assert "no candidate found" in payload["reason"]

    @pytest.mark.parametrize("mode", ["hybrid", "lexical_only", "unavailable"])
    def test_the_real_mode_is_recorded(self, mode: str) -> None:
        """Une réponse lexicale ne doit pas ressembler à une réponse hybride."""
        payload = memory_audit_payload(REQUEST_ID, _sufficient(), mode=mode)

        assert mode in payload["reason"]

    def test_a_lookup_for_unknown_request_falls_back_to_the_request_id(self) -> None:
        note = MemoryResult(sufficient=False, reason="rien").to_dict()

        payload = memory_audit_payload(REQUEST_ID, note, mode="unavailable")

        assert payload["resource_id"] == REQUEST_ID

    def test_a_missing_note_is_still_a_valid_event(self) -> None:
        """Le pipeline peut appeler la fonction sans note : l'événement reste vrai."""
        payload = memory_audit_payload(REQUEST_ID, None, mode="hybrid")

        assert payload["result"] == "degraded"
        assert payload["request_id"] == REQUEST_ID


class _FakeResult:
    """Minimal result set returned by the fake connection."""

    def mappings(self) -> _FakeResult:
        return self

    def all(self) -> list[dict]:
        return []

    def first(self) -> dict | None:
        return None


class _FakeConnection:
    """Records the INSERT parameters the writer hands over."""

    def __init__(self) -> None:
        self.executions: list[dict[str, Any]] = []

    async def execute(self, statement: Any, parameters: dict | None = None) -> _FakeResult:
        if parameters is not None:
            self.executions.append(dict(parameters))
        return _FakeResult()


class _FakeContext:
    def __init__(self, connection: _FakeConnection) -> None:
        self._connection = connection

    async def __aenter__(self) -> _FakeConnection:
        return self._connection

    async def __aexit__(self, *_: object) -> None:
        return None


class _FakeEngine:
    def __init__(self, connection: _FakeConnection) -> None:
        self._connection = connection

    def begin(self) -> _FakeContext:
        return _FakeContext(self._connection)


class TestTheWriterAcceptsItAsItIs:
    """§20.1 — un payload refusé à l'écriture est une trace perdue."""

    async def test_the_event_is_written_with_its_action_and_result(self) -> None:
        connection = _FakeConnection()
        writer = AuditWriter(_FakeEngine(connection))
        payload = memory_audit_payload(REQUEST_ID, _sufficient(), mode="hybrid")

        stored = await writer.write(payload)

        assert stored["audit_event_id"].startswith("AUD_")
        assert connection.executions[-1]["action"] == "memory_lookup"
        assert connection.executions[-1]["result"] == "success"
        assert connection.executions[-1]["request_id"] == REQUEST_ID

    async def test_a_miss_is_persisted_as_degraded(self) -> None:
        connection = _FakeConnection()
        writer = AuditWriter(_FakeEngine(connection))

        await writer.write(memory_audit_payload(REQUEST_ID, _insufficient(), mode="lexical_only"))

        assert connection.executions[-1]["result"] == "degraded"
        assert "lexical_only" in connection.executions[-1]["reason"]
class TestThePayloadCarriesTheEarlyStopDecision:
    """§17.1/§8.4 — l'arrêt de l'acquisition est un fait auditable."""

    def _stopped(self) -> dict[str, Any]:
        """Return the note of a lookup that stopped the acquisition."""
        return _sufficient() | {
            "stopped_acquisition": True,
            "criteria": [
                "provenance_complete",
                "freshness_acceptable",
                "policy_allows_reuse",
            ],
            "withheld_reason": None,
            "mode": "hybrid",
        }

    def test_a_stopped_acquisition_says_so_and_names_its_criteria(self) -> None:
        payload = memory_audit_payload(REQUEST_ID, self._stopped(), mode="hybrid")

        assert payload["result"] == "success"
        assert "acquisition arrêtée" in payload["reason"]
        assert "provenance_complete" in payload["reason"]
        assert UNIT_ID in payload["reason"]

    def test_the_event_is_still_accepted_by_the_writer(self) -> None:
        """La trace ne doit pas disparaître au moment de l'écriture (§20)."""
        payload = memory_audit_payload(REQUEST_ID, self._stopped(), mode="hybrid")
        writer = AuditWriter()
        assert writer is not None
        assert payload["action"] == "memory_lookup"
        assert payload["request_id"] == REQUEST_ID

    def test_a_withheld_stop_says_why_the_acquisition_continued(self) -> None:
        note = _sufficient() | {
            "stopped_acquisition": False,
            "withheld_reason": "recherche « lexical_only » : la suffisance §17.1 n'est pas conclue",
            "mode": "lexical_only",
        }
        payload = memory_audit_payload(REQUEST_ID, note, mode="lexical_only")

        assert "acquisition maintenue" in payload["reason"]
        assert "lexical_only" in payload["reason"]

    def test_an_insufficient_lookup_still_reports_a_degraded_result(self) -> None:
        payload = memory_audit_payload(REQUEST_ID, _insufficient(), mode="hybrid")
        assert payload["result"] == "degraded"
        assert "acquisition" not in payload["reason"], (
            "un run qui acquiert normalement n'a pas à parler d'arrêt"
        )

