"""Classification parser: turn an LLM response into a label verdict."""

from __future__ import annotations

import json
import re
from typing import Any

from app.core.errors import ValidationError

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


def parse_classification(content: str) -> dict[str, Any]:
    """Parse LLM content into a ``{"label", "confidence"}`` verdict.

    Accepts a JSON object with a ``label`` key and falls back to a bare
    single-word label.

    Args:
        content: Raw LLM response.

    Returns:
        Dict with ``label`` (str) and ``confidence`` (float | None).

    Raises:
        ValidationError: If no label can be extracted.
    """
    if not content or not content.strip():
        raise ValidationError("classification_parser: content must be a non-empty string")
    stripped = content.strip()
    match = _FENCE_RE.search(stripped)
    candidate = match.group(1).strip() if match else stripped
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict) and data.get("label"):
        confidence = data.get("confidence")
        return {
            "label": str(data["label"]).strip(),
            "confidence": float(confidence) if confidence is not None else None,
        }
    if re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_\- ]{0,63}", candidate):
        return {"label": candidate.strip(), "confidence": None}
    raise ValidationError("classification_parser: no label found in LLM content")
