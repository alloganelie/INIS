"""Domain entity representing a structured dataset obtained from a source."""

from pydantic import BaseModel, Field


class Dataset(BaseModel):
    """A stored dataset with its source provenance and schema."""

    dataset_id: str
    source_id: str
    dataset_schema: dict
    row_count: int = Field(ge=0)
    storage_ref: str
