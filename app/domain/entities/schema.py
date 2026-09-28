"""Schema value object returned by the ``inspect_schema`` tool (§21)."""

from pydantic import BaseModel, Field


class Schema(BaseModel):
    """Column names and observed types of a dataset, as declared by its source."""

    fields: dict[str, str] = Field(default_factory=dict)
    record_count: int = Field(default=0, ge=0)
    sample: list[dict] = Field(default_factory=list)

    @property
    def field_count(self) -> int:
        """Return the number of described columns."""
        return len(self.fields)

    @property
    def field_names(self) -> list[str]:
        """Return the ordered column names, preserving first-seen order."""
        return list(self.fields)
