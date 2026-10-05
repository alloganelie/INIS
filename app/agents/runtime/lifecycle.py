"""Resumable lifecycle for long-running Information Requests (§41.1).

The spec requires three behaviours for long requests:

* **Progression explicite** — ``GET /v1/requests/{id}/progress`` reports
  ``steps_total``, ``steps_done``, ``current_step``, ``estimated_completion``
  and ``partial_findings_available`` from the *real* execution state.
* **Reprise** — an interrupted request exposes ``resumable``,
  ``last_committed_step``, ``last_committed_at`` and an **opaque**
  ``resume_token`` so it can continue from the last committed step.
* **Expiration gracieuse** — when the TTL expires before delivery the work
  already done is returned as ``PARTIAL_SUCCESS`` rather than silently lost.

Constraints honoured here:

* The resume token is **opaque** (HMAC-signed, base64url payload) so a caller
  cannot tamper with the state it carries.
* Committing a step is **idempotent**: re-committing the same step id after a
  crash does not double-count progress.
* No I/O. The lifecycle holds in-memory state and accepts an injected clock,
  which keeps it unit-testable and free of infrastructure dependencies.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from app.core.time import utc_now as _utc_now

#: Status returned when a request expires before full delivery (§41.1).
GRACEFUL_EXPIRY_STATUS = "PARTIAL_SUCCESS"

#: Default TTL for a resumable request, in seconds.
DEFAULT_TTL_SECONDS = 900

#: Nominal duration attributed to one plan step for ETA estimation.
SECONDS_PER_STEP = 5

#: Process-wide token secret. Combined with the request id it derives the
#: per-request signing key, so a token stays verifiable across execution
#: attempts of the same request (and across processes when
#: ``INIS_RESUME_SECRET`` pins the seed). Random per process by default.
_PROCESS_SECRET = os.environ.get("INIS_RESUME_SECRET", "").encode("utf-8") or secrets.token_bytes(32)


class InvalidResumeToken(ValueError):
    """Raised when a resume token is malformed, tampered with, or expired."""


def _iso_z(moment: datetime) -> str:
    """Render *moment* as an ISO-8601 UTC string ending in ``Z`` (§0.3)."""
    return moment.isoformat().replace("+00:00", "Z")


def _b64encode(raw: bytes) -> str:
    """URL-safe base64 without padding."""
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    """Decode URL-safe base64, restoring the stripped padding."""
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _is_jsonable(value: Any) -> bool:
    """Return whether *value* can be embedded in the JSON resume payload."""
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return False
    return True


@dataclass(frozen=True)
class Checkpoint:
    """The last durably committed step of a request."""

    step_id: str
    committed_at: str
    step_index: int

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON projection of this checkpoint."""
        return {
            "step_id": self.step_id,
            "committed_at": self.committed_at,
            "step_index": self.step_index,
        }


@dataclass(frozen=True)
class ProgressSnapshot:
    """The §41.1 progress projection of a request lifecycle."""

    request_id: str
    steps_total: int
    steps_done: int
    current_step: str | None
    estimated_completion: str | None
    partial_findings_available: bool
    status: str

    def to_dict(self) -> dict[str, Any]:
        """Return the exact payload served by ``GET /{id}/progress``."""
        return {
            "steps_total": self.steps_total,
            "steps_done": self.steps_done,
            "current_step": self.current_step,
            "estimated_completion": self.estimated_completion,
            "partial_findings_available": self.partial_findings_available,
        }


class RequestLifecycle:
    """Track the resumable execution state of one Information Request (§41.1)."""

    def __init__(
        self,
        request_id: str,
        *,
        steps_total: int,
        plan: list[str] | None = None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        token_secret: bytes | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if steps_total < 1:
            raise ValueError("steps_total must be >= 1")
        if ttl_seconds < 1:
            raise ValueError("ttl_seconds must be >= 1")

        self.request_id = request_id
        self.steps_total = steps_total
        self.plan = list(plan or [])
        self.ttl_seconds = ttl_seconds
        self._clock = clock or _utc_now
        # Derive a per-request key from the process secret so a token issued by
        # one attempt stays verifiable by the next attempt of the same request.
        self._token_secret = token_secret or hashlib.sha256(
            _PROCESS_SECRET + request_id.encode("utf-8")
        ).digest()

        self._started_at = self.now()
        self._checkpoint: Checkpoint | None = None
        # §28 step names: a request always exposes a human-readable step.
        self._current_step: str | None = "RECEIVING"
        self._findings: list[dict[str, Any]] = []
        self._step_results: dict[str, Any] = {}
        self._status = "RECEIVING"
        self._completed = False

    # -- clock ---------------------------------------------------------

    def now(self) -> datetime:
        """Return the lifecycle clock (injectable for deterministic tests)."""
        return self._clock()

    def expires_at(self) -> str:
        """Return the ISO-8601 UTC instant at which the request TTL expires."""
        return _iso_z(self._started_at + timedelta(seconds=self.ttl_seconds))

    def is_expired(self) -> bool:
        """Return whether the TTL elapsed before the request completed."""
        if self._completed:
            return False
        return self.now() >= self._started_at + timedelta(seconds=self.ttl_seconds)

    def force_expiry(self) -> None:
        """Expire this request immediately (used by the explicit expiry endpoint)."""
        self._started_at = self.now() - timedelta(seconds=self.ttl_seconds + 1)

    # -- execution -----------------------------------------------------

    def set_step(self, step_id: str | None) -> None:
        """Record the step currently being executed."""
        self._current_step = step_id
        if self._status == "RECEIVING":
            self._status = "IN_PROGRESS"

    def commit_step(self, step_id: str, result: Any = None) -> Checkpoint:
        """Durably commit a completed step (idempotent per ``step_id``)."""
        if self._checkpoint is not None and self._checkpoint.step_id == step_id:
            # Replaying the same step after a crash must not double-count.
            return self._checkpoint
        index = self._step_index(step_id)
        if result is not None and _is_jsonable(result):
            self._step_results[step_id] = result
        self._checkpoint = Checkpoint(
            step_id=step_id,
            committed_at=_iso_z(self.now()),
            step_index=index,
        )
        self._status = "IN_PROGRESS"
        return self._checkpoint

    def add_finding(self, finding: dict[str, Any]) -> None:
        """Record a partial finding produced before delivery (§41.1)."""
        self._findings.append(dict(finding))

    def complete(self) -> None:
        """Mark the request as fully delivered."""
        self._status = "COMPLETED"
        self._completed = True
        # §41.1 always exposes a human-readable current_step.
        self._current_step = "DELIVERY"

    def partial_findings(self) -> list[dict[str, Any]]:
        """Return a copy of the findings gathered so far."""
        return [dict(finding) for finding in self._findings]

    @property
    def status(self) -> str:
        """Return the current lifecycle status."""
        return self._status

    @property
    def is_completed(self) -> bool:
        """Return whether the request reached full delivery."""
        return self._completed

    def steps_done(self) -> int:
        """Return the number of durably committed steps."""
        return self._checkpoint.step_index if self._checkpoint else 0

    def _step_index(self, step_id: str) -> int:
        """Return the 1-based position of *step_id* within the plan."""
        if step_id in self.plan:
            return self.plan.index(step_id) + 1
        return min(self.steps_done() + 1, self.steps_total)

    # -- projections ---------------------------------------------------

    def progress(self) -> ProgressSnapshot:
        """Return the §41.1 progress projection."""
        remaining = max(self.steps_total - self.steps_done(), 0)
        estimated = (
            _iso_z(self._started_at + timedelta(seconds=remaining * SECONDS_PER_STEP))
            if remaining
            else None
        )
        return ProgressSnapshot(
            request_id=self.request_id,
            steps_total=self.steps_total,
            steps_done=self.steps_done(),
            current_step=self._current_step,
            estimated_completion=estimated,
            partial_findings_available=bool(self._findings),
            status=self._status,
        )

    def resume_state(self) -> dict[str, Any]:
        """Return the §41.1 resume projection, including an opaque token."""
        checkpoint = self._checkpoint
        return {
            "resumable": checkpoint is not None and not self._completed,
            "last_committed_step": checkpoint.step_id if checkpoint else None,
            "last_committed_at": checkpoint.committed_at if checkpoint else None,
            "resume_token": self.issue_resume_token(),
        }

    # -- opaque resume token -------------------------------------------

    def issue_resume_token(self) -> str:
        """Return an opaque, HMAC-signed token carrying the committed state."""
        payload = {
            "request_id": self.request_id,
            "step_id": self._checkpoint.step_id if self._checkpoint else "",
            "step_index": self.steps_done(),
            "results": self._step_results,
            "exp": int((self._started_at + timedelta(seconds=self.ttl_seconds)).timestamp()),
        }
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        signature = hmac.new(self._token_secret, body, hashlib.sha256).digest()
        return f"{_b64encode(body)}.{_b64encode(signature)}"

    def verify_resume_token(self, token: str) -> dict[str, Any]:
        """Validate an opaque token and return its payload.

        Raises:
            InvalidResumeToken: if the token is malformed, has a bad
                signature, targets another request, or has expired.
        """
        if not isinstance(token, str) or token.count(".") != 1:
            raise InvalidResumeToken("resume token must be '<payload>.<signature>'")

        body_part, signature_part = token.split(".", 1)
        try:
            body = _b64decode(body_part)
            signature = _b64decode(signature_part)
        except (ValueError, TypeError) as exc:
            raise InvalidResumeToken("resume token is not valid base64url") from exc

        expected = hmac.new(self._token_secret, body, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise InvalidResumeToken("resume token signature mismatch")

        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InvalidResumeToken("resume token payload is not valid JSON") from exc

        if not isinstance(payload, dict):
            raise InvalidResumeToken("resume token payload must be an object")
        if payload.get("request_id") != self.request_id:
            raise InvalidResumeToken("resume token belongs to another request")
        if int(payload.get("exp", 0)) < int(self.now().timestamp()):
            raise InvalidResumeToken("resume token has expired")
        return payload

    def restore_from_token(self, token: str) -> Checkpoint | None:
        """Restore the committed step carried by *token*.

        Returns the restored checkpoint, or ``None`` when the token refers to a
        request that had not committed any step yet.
        """
        payload = self.verify_resume_token(token)
        step_id = str(payload.get("step_id") or "")
        if not step_id:
            return None
        self._step_results.update(payload.get("results") or {})
        self._checkpoint = Checkpoint(
            step_id=step_id,
            committed_at=_iso_z(self.now()),
            step_index=int(payload.get("step_index", 0)),
        )
        self._started_at = self.now()
        self._status = "RESUMED"
        self._current_step = "RESUMED"
        return self._checkpoint

    # -- graceful expiry (§41.1) ---------------------------------------

    def expire_gracefully(self) -> dict[str, Any]:
        """Deliver the partial work instead of losing it when the TTL elapsed."""
        checkpoint = self._checkpoint
        self._status = GRACEFUL_EXPIRY_STATUS
        return {
            "request_id": self.request_id,
            "status": GRACEFUL_EXPIRY_STATUS,
            "steps_total": self.steps_total,
            "steps_done": self.steps_done(),
            "last_committed_step": checkpoint.step_id if checkpoint else None,
            "last_committed_at": checkpoint.committed_at if checkpoint else None,
            "findings": self.partial_findings(),
            "resumable": checkpoint is not None,
            "resume_token": self.issue_resume_token(),
            "expired_at": _iso_z(self.now()),
        }
