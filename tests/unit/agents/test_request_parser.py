"""Tests for plain-text request parsing."""

import pytest

from app.agents.understanding.request_parser import RequestParser
from app.core.errors import ValidationError


def test_parse_builds_structured_request_with_canonical_identifier() -> None:
    request = RequestParser().parse("Find current vaccination coverage in Benin")

    assert request.request_id.startswith("REQ_")
    assert request.objective == "Find current vaccination coverage in Benin"
    assert request.request_type == "research"


def test_parse_normalizes_whitespace_and_keeps_context_isolated() -> None:
    context = {"country": "Benin"}

    request = RequestParser().parse("  Find\n vaccination   coverage  ", context=context)
    context["country"] = "Changed"

    assert request.objective == "Find vaccination coverage"
    assert request.context == {"country": "Benin"}


def test_parse_rejects_empty_text() -> None:
    with pytest.raises(ValidationError, match="non-empty objective"):
        RequestParser().parse(" \n\t ")
