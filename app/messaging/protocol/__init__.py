"""INIS Messaging Protocol — Envelope building, validation, idempotency, versioning."""

from app.messaging.protocol.envelope_builder import EnvelopeBuilder
from app.messaging.protocol.envelope_validator import validate
from app.messaging.protocol.idempotency_guard import IdempotencyGuard
from app.messaging.protocol.versioning import PROTOCOL_COMPATIBILITY
from app.messaging.protocol.versioning import ProtocolCompatibility

__all__ = [
    "EnvelopeBuilder",
    "validate",
    "IdempotencyGuard",
    "PROTOCOL_COMPATIBILITY",
    "ProtocolCompatibility",
]