"""Deterministic §12.1 transformation builders (§12.1, §33.2)."""

from __future__ import annotations

from typing import Any

from app.domain.entities.transformation import Transformation
from app.domain.value_objects.ulid import ULID


def make_transformation(
    *,
    input_ids: list[str] | None = None,
    output_ids: list[str] | None = None,
    **overrides: Any,
) -> Transformation:
    """Return a valid §12.1 :class:`~app.domain.entities.transformation.Transformation`.

    Args:
        input_ids: The resources consumed by the step.
        output_ids: The resources produced; a fresh ``INF_`` ULID when omitted
            so a default transformation is a genuine success.
        **overrides: Any ``Transformation`` field, e.g.
            ``result="failure", output_ids=[], justification="source unreachable"``
            for the §25.1 failing case.
    """
    values: dict[str, Any] = {
        "transformation_id": ULID.new("TRF_"),
        "input_ids": input_ids or [ULID.new("INF_")],
        "output_ids": output_ids if output_ids is not None else [ULID.new("INF_")],
        "operator": "normalize",
        "tool": "app.knowledge.normalization.normalizer.normalize",
        "tool_version": "1.0.0",
        "parameters": {"locale": "en-US"},
        "result": "success",
        "justification": "Locale normalization applied to the extracted text.",
    }
    values.update(overrides)
    return Transformation(**values)

