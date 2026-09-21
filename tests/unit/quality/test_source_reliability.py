"""Tests for SourceReliabilityScorer per §10.2."""

import pytest

from app.quality.source_reliability import SourceReliabilityScorer


@pytest.fixture
def scorer():
    """Create a SourceReliabilityScorer instance for testing."""
    return SourceReliabilityScorer()


def test_gov_domain_score(scorer):
    """Test government domain scoring (0.95)."""
    assert scorer.score("https://www.data.gouv.fr") == 0.95
    assert scorer.score("https://www.census.gov") == 0.95
    assert scorer.score("https://www.gov.uk") == 0.95


def test_edu_domain_score(scorer):
    """Test educational domain scoring (0.9)."""
    assert scorer.score("https://www.harvard.edu") == 0.9
    assert scorer.score("https://www.ox.ac.uk") == 0.9
    assert scorer.score("https://www.mit.edu") == 0.9


def test_wikipedia_score(scorer):
    """Test Wikipedia scoring (0.85)."""
    assert scorer.score("https://en.wikipedia.org/wiki/Test") == 0.85
    assert scorer.score("https://fr.wikipedia.org/wiki/Test") == 0.85


def test_social_media_score(scorer):
    """Test social media scoring (0.3)."""
    assert scorer.score("https://twitter.com/user") == 0.3
    assert scorer.score("https://www.facebook.com/page") == 0.3
    assert scorer.score("https://www.reddit.com/r/test") == 0.3


def test_unknown_domain_neutral(scorer):
    """Test unknown domain gets neutral score (0.5)."""
    assert scorer.score("https://www.unknown-domain.io") == 0.5
    assert scorer.score("https://random-website.xyz") == 0.5
    assert scorer.score("") == 0.5
