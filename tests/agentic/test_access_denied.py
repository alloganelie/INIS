"""§33.3 scenario 7 — « permission refusée ».

A denied permission must be a hard ``False`` (deny) the pipeline turns into an
``ACCESS_DENIED`` outcome — no partial answer may leak through (§19.3, §5.2).
"""

from __future__ import annotations

import pytest

from app.messaging.protocol.envelope_builder import VALID_MESSAGE_TYPES
from app.tools.governance_tools import check_permission


@pytest.mark.asyncio
async def test_restricted_resource_is_denied() -> None:
    """Restricted classification short-circuits the decision to deny (§19.4)."""
    allowed = await check_permission(
        "agt_reader", {"type": "source", "classification": "restricted"}, "read"
    )
    assert allowed is False


@pytest.mark.asyncio
async def test_role_without_rbac_grant_is_denied() -> None:
    """Default RBAC map is empty: an unprivileged role gets no access (§19.3)."""
    allowed = await check_permission(
        "agt_reader", "information_unit", "write", role="viewer"
    )
    assert allowed is False


@pytest.mark.asyncio
async def test_control_plain_read_is_allowed() -> None:
    """Control: the same call without restrictions is allowed."""
    allowed = await check_permission("agt_reader", "source", "read")
    assert allowed is True


def test_access_denied_is_a_valid_v1_message_type() -> None:
    """A refusal travels as an ACCESS_DENIED envelope (§5.2)."""
    assert "ACCESS_DENIED" in VALID_MESSAGE_TYPES
