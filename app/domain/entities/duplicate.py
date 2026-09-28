"""Duplicate group returned by the ``detect_duplicates`` tool (§21, §13)."""

from pydantic import BaseModel, Field


class Duplicate(BaseModel):
    """A set of dataset rows sharing an identical value set.

    ``key`` holds the values that made the rows equal and ``row_indexes`` the
    zero-based positions of every occurrence in the source dataset, so the
    caller can point back to the original rows instead of guessing (§14.1).
    """

    key: dict = Field(default_factory=dict)
    row_indexes: list[int] = Field(default_factory=list)

    @property
    def occurrence_count(self) -> int:
        """Return how many rows share this identical value set."""
        return len(self.row_indexes)
