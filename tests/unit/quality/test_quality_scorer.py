"""Tests for quality scoring per INIS §13.3."""

import pytest

from app.quality.score import DEFAULT_WEIGHTS, score, weighted_mean


def test_weighted_mean_default_weights():
    """Test weighted mean calculation with default weights."""
    results = {
        "completeness": 0.8,
        "validity": 0.9,
        "consistency": 0.7,
        "uniqueness": 0.85,
        "type_conformity": 0.9,
        "freshness": 0.75,
        "provenance_completeness": 0.8,
    }

    result = weighted_mean(results)
    expected = (
        0.8 * 0.15 +
        0.9 * 0.15 +
        0.7 * 0.15 +
        0.85 * 0.10 +
        0.9 * 0.10 +
        0.75 * 0.15 +
        0.8 * 0.20
    )

    assert abs(result - expected) < 0.001


def test_weighted_mean_custom_weights():
    """Test weighted mean calculation with custom weights."""
    results = {
        "completeness": 0.8,
        "validity": 0.9,
    }
    custom_weights = {
        "completeness": 0.6,
        "validity": 0.4,
    }

    result = weighted_mean(results, custom_weights)
    expected = 0.8 * 0.6 + 0.9 * 0.4

    assert abs(result - expected) < 0.001


def test_weighted_mean_partial_metrics():
    """Test weighted mean when only some metrics are present."""
    results = {
        "completeness": 0.8,
        "validity": 0.9,
    }

    result = weighted_mean(results)
    expected = (0.8 * 0.15 + 0.9 * 0.15) / (0.15 + 0.15)

    assert abs(result - expected) < 0.001


def test_weighted_mean_empty_results():
    """Test weighted mean with empty results."""
    result = weighted_mean({})
    assert result == 0.0


def test_score_function():
    """Test score function wrapper."""
    results = {
        "completeness": 0.8,
        "validity": 0.9,
        "consistency": 0.7,
    }

    result = score(results)
    expected = (
        0.8 * 0.15 +
        0.9 * 0.15 +
        0.7 * 0.15
    ) / (0.15 + 0.15 + 0.15)

    assert abs(result - expected) < 0.001


def test_default_weights_structure():
    """Test that default weights have expected structure."""
    assert "completeness" in DEFAULT_WEIGHTS
    assert "validity" in DEFAULT_WEIGHTS
    assert "consistency" in DEFAULT_WEIGHTS
    assert "uniqueness" in DEFAULT_WEIGHTS
    assert "type_conformity" in DEFAULT_WEIGHTS
    assert "freshness" in DEFAULT_WEIGHTS
    assert "provenance_completeness" in DEFAULT_WEIGHTS

    total_weight = sum(DEFAULT_WEIGHTS.values())
    assert abs(total_weight - 1.0) < 0.001


def test_weighted_mean_perfect_scores():
    """Test weighted mean with all perfect scores."""
    results = {
        "completeness": 1.0,
        "validity": 1.0,
        "consistency": 1.0,
        "uniqueness": 1.0,
        "type_conformity": 1.0,
        "freshness": 1.0,
        "provenance_completeness": 1.0,
    }

    result = weighted_mean(results)
    assert result == 1.0


def test_weighted_mean_zero_scores():
    """Test weighted mean with all zero scores."""
    results = {
        "completeness": 0.0,
        "validity": 0.0,
        "consistency": 0.0,
    }

    result = weighted_mean(results)
    assert result == 0.0
