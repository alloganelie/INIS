"""Validation result returned by the ``validate_schema`` tool (§21)."""

from pydantic import BaseModel, Field


class SchemaViolation(BaseModel):
    """One concrete schema violation observed on one record."""

    row_index: int = Field(ge=0)
    field: str
    expected: str
    observed: str


class ValidationResult(BaseModel):
    """Outcome of validating a dataset against an expected schema (§13.1)."""

    valid: bool = True
    checked_fields: int = Field(default=0, ge=0)
    checked_rows: int = Field(default=0, ge=0)
    violations: list[SchemaViolation] = Field(default_factory=list)

    @property
    def violation_count(self) -> int:
        """Return the number of recorded violations."""
        return len(self.violations)

    def summary(self) -> str:
        """Return a short, non-fabricated human summary of the result."""
        if self.valid:
            return f"schema valid for {self.checked_rows} rows"
        return f"{self.violation_count} schema violation(s) on {self.checked_rows} rows"
