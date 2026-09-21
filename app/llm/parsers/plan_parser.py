"""Plan parser: turn an LLM planning response into a structured plan."""

from __future__ import annotations

import json
import re
from typing import Any

from app.core.errors import ValidationError

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


def _extract_json(content: str) -> Any:
    """Extract the JSON payload from raw or fenced LLM content."""
    match = _FENCE_RE.search(content)
    candidate = match.group(1) if match else content
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end <= start:
            raise ValidationError("plan_parser: no JSON object found in LLM content")
        try:
            return json.loads(candidate[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ValidationError(f"plan_parser: invalid JSON plan: {exc}") from exc


def parse_plan(content: str) -> dict[str, Any]:
    """Parse LLM content into a plan dict with an ordered ``steps`` list.

    Args:
        content: Raw LLM response (JSON, possibly fenced or embedded).

    Returns:
        Dict with a ``steps`` list; each step has order, tool, description.

    Raises:
        ValidationError: If no valid plan with steps can be extracted.
    """
    if not content or not content.strip():
        raise ValidationError("plan_parser: content must be a non-empty string")
    data = _extract_json(content)
    if not isinstance(data, dict) or not isinstance(data.get("steps"), list):
        raise ValidationError("plan_parser: plan must be a JSON object with a steps list")
    steps: list[dict[str, Any]] = []
    for order, raw_step in enumerate(data["steps"], start=1):
        if not isinstance(raw_step, dict):
            raise ValidationError(f"plan_parser: step {order} must be an object")
        description = raw_step.get("description") or raw_step.get("action")
        if not description:
            raise ValidationError(f"plan_parser: step {order} needs a description")
        steps.append(
            {
                "order": int(raw_step.get("order", order)),
                "tool": str(raw_step.get("tool", "")),
                "description": str(description),
                "expected_output": str(raw_step.get("expected_output", "")),
            }
        )
    if not steps:
        raise ValidationError("plan_parser: plan must contain at least one step")
    return {"steps": steps}
