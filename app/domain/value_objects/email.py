"""Validated email address value object."""

import re
from dataclasses import dataclass


_EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)


@dataclass(frozen=True)
class Email:
    """An email address validated with a simplified RFC 5322 pattern."""

    value: str

    def __post_init__(self) -> None:
        """Reject values that are not valid email addresses."""
        if not isinstance(self.value, str) or not _EMAIL_PATTERN.fullmatch(self.value):
            raise ValueError("email must be a valid email address")

    def __str__(self) -> str:
        """Return the serializable email address value."""
        return self.value
