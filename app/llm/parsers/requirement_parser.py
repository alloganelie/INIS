"""Requirement parser: turn an LLM response into structured requirements."""

from __future__ import annotations

import json
import re
from typing import Any

from app.core.errors import ValidationError

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)
_BULLET_RE = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+(.+?)\s*$")


def _try_json(content: str) -> Any | None:
    """Return parsed JSON when present, else None."""
    match = _FENCE_RE.search(content)
    candidate = match.group(1) if match else content.strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


def parse_requirements(content: str) -> list[dict[str, Any]]:
    """Parse LLM content into a list of requirement dicts.

    Accepts a JSON list (or ``{"requirements": [...]}``) and falls back to
    bullet/numbered lines. Each requirement carries a ``description``.

    Args:
        content: Raw LLM response.

    Returns:
        Non-empty list of ``{"description": str}`` dicts.

    Raises:
        ValidationError: If no requirement can be extracted.
    """
    if not content or not content.strip():
        raise ValidationError("requirement_parser: content must be a non-empty string")
    data = _try_json(content)
    items: list[Any] = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict) and isinstance(data.get("requirements"), list):
        items = data["requirements"]
    elif data is None:
        items = [
            match.group(1)
            for line in content.splitlines()
            if (match := _BULLET_RE.match(line))
        ]
    else:
        raise ValidationError("requirement_parser: unsupported JSON shape")
    requirements: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict) and item.get("description"):
            requirements.append({"description": str(item["description"])})
        elif isinstance(item, str) and item.strip():
            requirements.append({"description": item.strip()})
    if not requirements:
        raise ValidationError("requirement_parser: no requirements found")
    return requirements
