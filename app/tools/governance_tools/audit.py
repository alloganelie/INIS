"""``write_audit_event`` internal tool per §21 (§20 audit trail).

The heavy lifting stays in :class:`~app.governance.audit.audit_writer.AuditWriter`,
which validates the §20.1 contract and persists in memory or to the configured
asynchronous engine. The tool adds the §21 input guards and the spec-mandated
``-> None`` signature.
"""

from __future__ import annotations

from typing import Any, Mapping

from app.core.errors import ValidationError
from app.governance.audit.audit_writer import AuditWriter

__all__ = ["write_audit_event"]


async def write_audit_event(
    event: Mapping[str, Any],
    *,
    writer: AuditWriter | None = None,
    engine: Any | None = None,
    session: Any | None = None,
) -> None:
    """Persist *event* to the audit trail (§21 signature).

    Args:
        event: Audit event following the §20.1 contract.
        writer: Injected audit writer; a fresh one is built from *engine*
            when omitted.
        engine: Optional async engine for durable writes (§20).
        session: Optional active ``AsyncSession`` to join (§20).

    Raises:
        ValidationError: If *event* is not a non-empty mapping or a required
            §20.1 field is missing.
    """
    if not isinstance(event, Mapping) or not event:
        raise ValidationError("audit event must be a non-empty mapping (§20.1)")
    active = writer if writer is not None else AuditWriter(engine)
    await active.write(dict(event), session=session)
