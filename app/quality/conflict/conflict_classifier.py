"""Conflict difference classification per INIS §14.4."""

from typing import Literal

from app.domain.entities.information_unit import InformationUnit


def classify_difference(a: InformationUnit, b: InformationUnit) -> Literal["value", "definition", "date", "methodology", "scope"]:
    """Classify the type of difference between two information units.

    Args:
        a: First information unit
        b: Second information unit

    Returns:
        Difference type: value, definition, date, methodology, or scope
    """
    a_time = a.time
    b_time = b.time

    a_context = a.context
    b_context = b.context

    if a_time.get("value") != b_time.get("value"):
        return "date"

    if a_context.get("definition") != b_context.get("definition"):
        return "definition"

    if a_context.get("methodology") != b_context.get("methodology"):
        return "methodology"

    if a_context.get("scope") != b_context.get("scope"):
        return "scope"

    return "value"
