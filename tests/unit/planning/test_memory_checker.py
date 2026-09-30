"""§17.1 — memory reuse is a three-filter decision, not a cache hit.

§17 lets INIS answer a question it already answered, but only from material that
is complete, fresh enough, and allowed by policy. The tests below exercise those
three filters directly, plus the promise that a refusal is explained: a
``sufficient=False`` result must say *why* nothing could be reused, otherwise
the caller cannot tell a stale cache from an empty one.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest

from app.domain.entities.memory_result import MemoryCandidate, MemoryResult
from app.domain.value_objects.ulid import ULID
from app.planning.memory_checker import (
    MemoryRequirements,
    freshness_acceptable,
    memory_lookup,
    policy_allows_reuse,
)

DEFAULT_QUESTION = "Quelle est la capitale de la France ?"


def _candidate(**overrides: object) -> MemoryCandidate:
    """Return a fresh, fully traceable candidate unless overridden."""
    values: dict[str, object] = {
        "information_id": ULID.new("INF_"),
        "content": {"text": "Paris est la capitale de la France."},
        "source_id": ULID.new("SRC_"),
        "provenance": {"extracted_from": "https://fr.wikipedia.org/wiki/Paris"},
        "source_freshness": datetime.now(UTC) - timedelta(hours=1),
    }
    values.update(overrides)
    return MemoryCandidate(**values)  # type: ignore[arg-type]


def _search_returning(*candidates: MemoryCandidate):
    """Return an injected §17.1 search callable over *candidates*."""

    async def _search(question: str, requirements: MemoryRequirements) -> Sequence[MemoryCandidate]:
        assert question == DEFAULT_QUESTION
        return candidates

    return _search


class TestMemoryLookupFilters:
    """§17.1 — the filters, in the order the specification applies them."""

    async def test_fresh_traceable_candidate_is_reused(self) -> None:
        """A complete, fresh candidate answers the question from memory."""
        candidate = _candidate()

        result = await memory_lookup(DEFAULT_QUESTION, search=_search_returning(candidate))

        assert result.sufficient is True
        assert result.items == (candidate,)
        assert result.reason is None

    async def test_candidate_without_provenance_is_skipped(self) -> None:
        """§0.2 — an untraceable unit may never be reused."""
        untraceable = _candidate(provenance={})
        usable = _candidate()

        result = await memory_lookup(
            DEFAULT_QUESTION, search=_search_returning(untraceable, usable)
        )

        assert result.sufficient is True
        assert result.items == (usable,)

    async def test_stale_candidate_is_refused_and_explained(self) -> None:
        """§41.5 for reuse: material older than the threshold is not served."""
        stale = _candidate(source_freshness=datetime.now(UTC) - timedelta(hours=48))

        result = await memory_lookup(DEFAULT_QUESTION, search=_search_returning(stale))

        assert result.sufficient is False
        assert result.items == ()
        assert result.reason is not None and "stale" in result.reason

    async def test_candidate_of_unknown_age_is_not_reused(self) -> None:
        """An entry with no freshness metadata cannot be proven fresh."""
        unknown = _candidate(source_freshness=None)

        result = await memory_lookup(DEFAULT_QUESTION, search=_search_returning(unknown))

        assert result.sufficient is False

    async def test_soft_deleted_candidate_is_never_reused(self) -> None:
        """§18.2 — a deleted record stays deleted, whatever the policy says."""
        deleted = _candidate(deleted=True, policy_allows_reuse=True)

        result = await memory_lookup(DEFAULT_QUESTION, search=_search_returning(deleted))

        assert result.sufficient is False
        assert result.reason is not None and "policy" in result.reason

    async def test_unknown_memory_is_reported_as_such(self) -> None:
        """No candidate at all is a different answer from a rejected candidate."""
        result = await memory_lookup(DEFAULT_QUESTION, search=_search_returning())

        assert result.sufficient is False
        assert result.reason == "no candidate found"

    async def test_empty_question_is_refused(self) -> None:
        """A lookup needs a question; silence must not be answered from memory."""
        with pytest.raises(ValueError):
            await memory_lookup("", search=_search_returning())


class TestMemoryPolicies:
    """§17.1 — the two helpers are usable and testable on their own."""

    def test_freshness_threshold_zero_disables_the_filter(self) -> None:
        """§41.5 semantics: a zero threshold accepts any freshness."""
        stale = _candidate(source_freshness=datetime.now(UTC) - timedelta(days=365))

        assert freshness_acceptable(stale, MemoryRequirements(freshness_threshold_hours=0))
        assert not freshness_acceptable(stale, MemoryRequirements(freshness_threshold_hours=24))

    def test_policy_flag_is_honoured(self) -> None:
        """``policy_allows_reuse`` is the explicit §17.1 policy gate."""
        assert policy_allows_reuse(_candidate()) is True
        assert policy_allows_reuse(_candidate(policy_allows_reuse=False)) is False

    def test_result_projection_lists_the_reused_units(self) -> None:
        """The delivery payload exposes which units answered the question."""
        candidate = _candidate()
        result = MemoryResult(
            sufficient=True, items=(candidate,), question=DEFAULT_QUESTION
        )

        assert result.to_dict() == {
            "sufficient": True,
            "question": DEFAULT_QUESTION,
            "reason": None,
            "information_ids": [candidate.information_id],
        }

