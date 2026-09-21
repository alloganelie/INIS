"""Tests for the LLM prompt builders (§22.3 templates)."""

from app.llm.prompts import (
    build_classification,
    build_confidence_signal,
    build_conflict_detection,
    build_planning,
    build_understanding,
)


class TestPrompts:
    """5 tests, one per prompt builder."""

    def test_understanding_embeds_objective(self) -> None:
        """Understanding prompt carries the objective and JSON contract."""
        prompt = build_understanding(
            objective="Assess Q2 outlook",
            question="What is the outlook?",
            context={"region": "FR"},
        )
        assert "Assess Q2 outlook" in prompt
        assert "What is the outlook?" in prompt
        assert '"intent"' in prompt
        assert "§22.3" in prompt

    def test_classification_lists_candidate_labels(self) -> None:
        """Classification prompt enforces the closed label set."""
        prompt = build_classification(
            content="GDP grew 1.2%",
            candidate_labels=["factual", "hypothesis", "uncertainty"],
        )
        assert '"factual"' in prompt and '"hypothesis"' in prompt
        assert "GDP grew 1.2%" in prompt
        assert '"label"' in prompt

    def test_planning_lists_tools_and_limits(self) -> None:
        """Planning prompt lists tools, max steps and the plan shape."""
        prompt = build_planning(
            objective="Gather evidence",
            available_tools=["web_search", "vector_search"],
            max_steps=4,
        )
        assert "web_search" in prompt and "vector_search" in prompt
        assert "4" in prompt
        assert '"steps"' in prompt

    def test_confidence_signal_uses_0_1_scale(self) -> None:
        """Confidence prompt asks for a 0-1 signal, not a probability."""
        prompt = build_confidence_signal(
            claim="Rates held steady",
            supporting_evidence=["Central bank statement"],
            contradicting_evidence=["Market rumor"],
        )
        assert "Rates held steady" in prompt
        assert "Central bank statement" in prompt
        assert "Market rumor" in prompt
        assert "not a" in prompt and "probability" in prompt

    def test_conflict_detection_compares_both_items(self) -> None:
        """Conflict prompt includes both items and the verdict shape."""
        prompt = build_conflict_detection(
            item_a="GDP grew 1.2% (INSEE)",
            item_b="GDP fell 0.3% (survey)",
        )
        assert "INSEE" in prompt and "survey" in prompt
        assert '"conflict"' in prompt
        assert '"difference_type"' in prompt
