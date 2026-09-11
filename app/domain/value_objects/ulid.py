"""Prefixed, lexicographically sortable INIS identifiers."""

from ulid import ULID as PythonUlid

from app.core.constants import ULID_PREFIXES


class ULID:
    """Create and validate prefixed ULID identifiers required by INIS."""

    @staticmethod
    def new(prefix: str) -> str:
        """Return a new identifier using one of the approved INIS prefixes."""
        if prefix not in ULID_PREFIXES:
            raise ValueError(f"Unsupported ULID prefix: {prefix}")
        return f"{prefix}{PythonUlid()}"

    @staticmethod
    def is_valid(value: str) -> bool:
        """Return whether *value* has an approved prefix and valid ULID suffix."""
        if not isinstance(value, str):
            return False

        for prefix in ULID_PREFIXES:
            if not value.startswith(prefix):
                continue

            suffix = value.removeprefix(prefix)
            if len(suffix) != 26:
                return False

            try:
                PythonUlid.from_str(suffix)
            except ValueError:
                return False
            return True

        return False
