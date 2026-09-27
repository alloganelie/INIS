"""Protocol versioning & backward compatibility (§41.11).

Implements the four mandatory rules:

* unknown fields are silently ignored (forward tolerance — the validator
  only checks known keys);
* missing fields fall back to their default (backward tolerance);
* an incompatible **major** version is rejected with an error carrying
  ``version_supported``;
* the version is negotiated at ``AGENT_REGISTER``: the agent declares its
  supported versions and the intersection is chosen.

The ``protocol_compatibility`` ``[CONFIG]`` block is the single source of
truth used by the envelope builder, the validator and the register
handler.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

#: ``major.minor`` — the only accepted protocol version shape.
_VERSION_RE = re.compile(r"^(\d+)\.(\d+)$")


def parse_version(version: Any) -> tuple[int, int]:
    """Return ``(major, minor)`` for a protocol version string.

    Raises:
        ValueError: when *version* is not a ``major.minor`` string.
    """
    if not isinstance(version, str):
        raise ValueError(f"protocol version must be a string, got: {version!r}")
    match = _VERSION_RE.match(version)
    if match is None:
        raise ValueError(f"malformed protocol version: {version!r}")
    return int(match.group(1)), int(match.group(2))


@dataclass(frozen=True)
class ProtocolCompatibility:
    """The §41.11 ``protocol_compatibility`` ``[CONFIG]`` block."""

    supported_versions: tuple[str, ...] = ("1.0", "1.1")
    preferred_version: str = "1.0"
    min_version: str = "1.0"

    def __post_init__(self) -> None:
        if not self.supported_versions:
            raise ValueError("supported_versions must not be empty")
        parsed = [parse_version(v) for v in self.supported_versions]
        if len(set(parsed)) != len(parsed):
            raise ValueError("supported_versions must be unique")
        if self.preferred_version not in self.supported_versions:
            raise ValueError("preferred_version must be in supported_versions")
        if self.min_version not in self.supported_versions:
            raise ValueError("min_version must be in supported_versions")

    def supports(self, version: Any) -> bool:
        """Return whether *version* is exactly one of the supported ones."""
        return isinstance(version, str) and version in self.supported_versions

    def is_compatible(self, version: Any) -> bool:
        """Apply the §41.11 tolerance window to an incoming version.

        Any well-formed version whose **major** lies between the major of
        ``min_version`` and the highest supported major is accepted: newer
        minors of the same major are tolerated (forward), older minors are
        tolerated (backward). Other majors are incompatible.
        """
        try:
            major, _ = parse_version(version)
        except ValueError:
            return False
        min_major, _ = parse_version(self.min_version)
        max_major = max(parse_version(v)[0] for v in self.supported_versions)
        return min_major <= major <= max_major

    def negotiate(self, agent_versions: Iterable[str] | None) -> str | None:
        """Return the version agreed upon at ``AGENT_REGISTER`` (§41.11).

        The intersection of both sides is used, preferring our
        ``preferred_version`` then the newest common version; ``None``
        means no common version (registration must be rejected).
        """
        if not agent_versions:
            return None
        declared = set(agent_versions)
        common = [v for v in self.supported_versions if v in declared]
        if not common:
            return None
        if self.preferred_version in common:
            return self.preferred_version
        return max(common, key=parse_version)

    def to_dict(self) -> dict[str, Any]:
        """Return the exact §41.11 ``protocol_compatibility`` block."""
        return {
            "protocol_compatibility": {
                "supported_versions": list(self.supported_versions),
                "preferred_version": self.preferred_version,
                "min_version": self.min_version,
            }
        }


#: Process-wide compatibility policy (§41.11 ``[CONFIG]``).
PROTOCOL_COMPATIBILITY = ProtocolCompatibility()

#: Version stamped on outgoing envelopes by the builder.
DEFAULT_PROTOCOL_VERSION = PROTOCOL_COMPATIBILITY.preferred_version
