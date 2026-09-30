"""Unit tests for the §8/§22 plan parser.

The LLM is allowed to answer with raw JSON, a fenced ```json block or JSON
embedded in prose; anything else must raise a ``ValidationError`` instead of
producing a half-parsed plan.
"""

from __future__ import annotations

import json

import pytest

from app.core.errors import ValidationError
from app.llm.parsers.plan_parser import parse_plan


class TestAcceptedPlanPayloads:
    """§22 — the three shapes an LLM answer may take."""

    def test_raw_json_object(self) -> None:
        """A bare JSON object is parsed as-is."""
        plan = parse_plan(json.dumps({"steps": [{"description": "search the web"}]}))
        assert plan["steps"][0]["description"] == "search the web"

    def test_fenced_json_block(self) -> None:
        """```json fences are stripped before parsing."""
        content = '```json\n{"steps": [{"description": "read the page"}]}\n```'
        assert parse_plan(content)["steps"][0]["description"] == "read the page"

    def test_fence_without_language_tag(self) -> None:
        """``` without a language tag is accepted too."""
        assert parse_plan('```\n{"steps": [{"description": "x"}]}\n```')["steps"] == [
            {"order": 1, "tool": "", "description": "x", "expected_output": ""}
        ]

    def test_json_embedded_in_prose(self) -> None:
        """Explanatory text around the JSON object is tolerated."""
        content = 'Voici le plan: {"steps": [{"description": "y"}]} — fin.'
        assert parse_plan(content)["steps"][0]["description"] == "y"


class TestStepNormalization:
    """§8 — every step exposes order, tool, description, expected_output."""

    def test_order_is_derived_from_position(self) -> None:
        """When the LLM omits ``order``, the list position is used (1-based)."""
        plan = parse_plan(json.dumps({"steps": [{"description": "a"}, {"description": "b"}]}))
        assert [step["order"] for step in plan["steps"]] == [1, 2]

    def test_explicit_order_wins(self) -> None:
        """An explicit ``order`` value is preserved."""
        plan = parse_plan(json.dumps({"steps": [{"description": "a", "order": 7}]}))
        assert plan["steps"][0]["order"] == 7

    def test_action_is_accepted_as_description_alias(self) -> None:
        """``action`` is the documented alias when ``description`` is absent."""
        plan = parse_plan(json.dumps({"steps": [{"action": "search"}]}))
        assert plan["steps"][0]["description"] == "search"

    def test_a_declared_action_is_kept_as_an_action(self) -> None:
        """§8.4 — the parser reports the declared ``action`` as an action."""
        step = parse_plan(
            json.dumps(
                {"steps": [{"action": "collect_information", "description": "chercher"}]}
            )
        )["steps"][0]

        assert step["action"] == "collect_information"
        assert step["description"] == "chercher"

    def test_prose_never_becomes_an_action(self) -> None:
        """A step that declares no action carries none: the validator refuses it."""
        step = parse_plan(json.dumps({"steps": [{"description": "lire le fichier"}]}))[
            "steps"
        ][0]

        assert "action" not in step
        assert step["description"] == "lire le fichier"

    def test_missing_optional_fields_become_empty_strings(self) -> None:
        """``tool`` and ``expected_output`` default to ``""`` (never None)."""
        step = parse_plan(json.dumps({"steps": [{"description": "a"}]}))["steps"][0]
        assert step["tool"] == ""
        assert step["expected_output"] == ""

    def test_tool_and_expected_output_are_kept(self) -> None:
        """Declared tool / expected output survive parsing."""
        step = parse_plan(
            json.dumps(
                {
                    "steps": [
                        {
                            "description": "d",
                            "tool": "web_search",
                            "expected_output": "candidates",
                        }
                    ]
                }
            )
        )["steps"][0]
        assert step["tool"] == "web_search"
        assert step["expected_output"] == "candidates"


class TestRejectedPayloads:
    """§0.2 — no plan is better than a silently truncated plan."""

    @pytest.mark.parametrize("content", ["", "   ", "\n"])
    def test_empty_content(self, content: str) -> None:
        """Empty content is an explicit validation error."""
        with pytest.raises(ValidationError, match="non-empty string"):
            parse_plan(content)

    def test_no_json_object(self) -> None:
        """Pure prose without any JSON object is refused."""
        with pytest.raises(ValidationError, match="no JSON object found"):
            parse_plan("I cannot build a plan for that request.")

    def test_malformed_json(self) -> None:
        """Broken JSON is reported as an invalid plan."""
        with pytest.raises(ValidationError, match="invalid JSON plan"):
            parse_plan('{"steps": [{"description": "a"},]}')

    @pytest.mark.parametrize("payload", [[], "text", 42, {"plan": []}])
    def test_plan_without_steps_list(self, payload: object) -> None:
        """A payload without a ``steps`` list is refused."""
        with pytest.raises(ValidationError, match="steps list"):
            parse_plan(json.dumps(payload))

    def test_empty_steps_list(self) -> None:
        """An empty plan cannot be executed."""
        with pytest.raises(ValidationError, match="at least one step"):
            parse_plan(json.dumps({"steps": []}))

    def test_step_without_description(self) -> None:
        """A step must state what it does."""
        with pytest.raises(ValidationError, match="needs a description"):
            parse_plan(json.dumps({"steps": [{"tool": "web_search"}]}))

    def test_non_object_step(self) -> None:
        """Steps must be objects, not bare strings."""
        with pytest.raises(ValidationError, match="must be an object"):
            parse_plan(json.dumps({"steps": ["search"]}))

