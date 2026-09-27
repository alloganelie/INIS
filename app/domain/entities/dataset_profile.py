"""Dataset profile returned by the ``profile_dataset`` tool (§21, §13)."""

from pydantic import BaseModel, Field


class DatasetProfile(BaseModel):
    """Descriptive statistics computed from a dataset's own values only.

    Every field is a *measurement* of the dataset: nothing is inferred or
    imputed, so an empty column stays ``None`` instead of receiving a
    placeholder value (§1.2, §0.2).
    """

    dataset_id: str | None = None
    row_count: int = Field(default=0, ge=0)
    column_count: int = Field(default=0, ge=0)
    columns: list[str] = Field(default_factory=list)
    null_counts: dict[str, int] = Field(default_factory=dict)
    distinct_counts: dict[str, int] = Field(default_factory=dict)
    type_counts: dict[str, dict[str, int]] = Field(default_factory=dict)
    numeric_stats: dict[str, dict[str, float]] = Field(default_factory=dict)
    duplicate_row_count: int = Field(default=0, ge=0)

    @property
    def completeness(self) -> float:
        """Return the fraction of non-null cells, ``1.0`` for an empty dataset."""
        if self.row_count == 0 or self.column_count == 0:
            return 1.0
        missing = sum(self.null_counts.values())
        total = self.row_count * self.column_count
        return max(0.0, 1.0 - (missing / total))
