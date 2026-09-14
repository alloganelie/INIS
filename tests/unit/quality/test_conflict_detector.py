"""Tests for conflict detection per INIS §14.4."""

import pytest

from app.domain.entities.conflict import Conflict
from app.domain.entities.information_unit import InformationUnit
from app.domain.value_objects.ulid import ULID
from app.quality.conflict import (
    assess_severity,
    classify_difference,
    detect_conflicts,
)


@pytest.fixture
def sample_units():
    """Create sample information units for testing."""
    return [
        InformationUnit(
            information_id=ULID.new("INF_"),
            type="text",
            content={"subject": "temperature", "predicate": "value", "value": 25.0},
            raw_reference={},
            source_id=ULID.new("SRC_"),
            document_id=ULID.new("DOC_"),
            dataset_id=None,
            location={},
            context={},
            language="en",
            unit=None,
            time={"value": "2024-01-01"},
            classification={},
            quality={"score": 0.8},
            confidence={"score": 0.9},
            provenance={"source": "sensor"},
            versions=["v1"],
            data_stage="raw",
        ),
        InformationUnit(
            information_id=ULID.new("INF_"),
            type="text",
            content={"subject": "temperature", "predicate": "value", "value": 27.0},
            raw_reference={},
            source_id=ULID.new("SRC_"),
            document_id=ULID.new("DOC_"),
            dataset_id=None,
            location={},
            context={},
            language="en",
            unit=None,
            time={"value": "2024-01-01"},
            classification={},
            quality={"score": 0.7},
            confidence={"score": 0.8},
            provenance={"source": "sensor"},
            versions=["v1"],
            data_stage="raw",
        ),
        InformationUnit(
            information_id=ULID.new("INF_"),
            type="text",
            content={"subject": "pressure", "predicate": "value", "value": 1013.0},
            raw_reference={},
            source_id=ULID.new("SRC_"),
            document_id=ULID.new("DOC_"),
            dataset_id=None,
            location={},
            context={},
            language="en",
            unit=None,
            time={"value": "2024-01-01"},
            classification={},
            quality={"score": 0.9},
            confidence={"score": 0.95},
            provenance={"source": "sensor"},
            versions=["v1"],
            data_stage="raw",
        ),
    ]


@pytest.mark.asyncio
async def test_detect_conflicts_with_differing_values(sample_units):
    """Test conflict detection when values differ for same subject-predicate."""
    conflicts = await detect_conflicts(sample_units[:2])

    assert len(conflicts) == 1
    assert conflicts[0].information_a == sample_units[0].information_id
    assert conflicts[0].information_b == sample_units[1].information_id
    assert conflicts[0].difference_type == "value"
    assert conflicts[0].resolution_status == "open"


@pytest.mark.asyncio
async def test_detect_conflicts_no_conflict_different_subjects(sample_units):
    """Test no conflict detected for different subjects."""
    conflicts = await detect_conflicts([sample_units[0], sample_units[2]])

    assert len(conflicts) == 0


@pytest.mark.asyncio
async def test_detect_conflicts_multiple_groups():
    """Test conflict detection across multiple subject-predicate groups."""
    units = [
        InformationUnit(
            information_id=ULID.new("INF_"),
            type="text",
            content={"subject": "temp", "predicate": "value", "value": 25.0},
            raw_reference={},
            source_id=ULID.new("SRC_"),
            document_id=ULID.new("DOC_"),
            dataset_id=None,
            location={},
            context={},
            language="en",
            unit=None,
            time={"value": "2024-01-01"},
            classification={},
            quality={"score": 0.8},
            confidence={"score": 0.9},
            provenance={"source": "sensor"},
            versions=["v1"],
            data_stage="raw",
        ),
        InformationUnit(
            information_id=ULID.new("INF_"),
            type="text",
            content={"subject": "temp", "predicate": "value", "value": 27.0},
            raw_reference={},
            source_id=ULID.new("SRC_"),
            document_id=ULID.new("DOC_"),
            dataset_id=None,
            location={},
            context={},
            language="en",
            unit=None,
            time={"value": "2024-01-01"},
            classification={},
            quality={"score": 0.7},
            confidence={"score": 0.8},
            provenance={"source": "sensor"},
            versions=["v1"],
            data_stage="raw",
        ),
        InformationUnit(
            information_id=ULID.new("INF_"),
            type="text",
            content={"subject": "pressure", "predicate": "value", "value": 1013.0},
            raw_reference={},
            source_id=ULID.new("SRC_"),
            document_id=ULID.new("DOC_"),
            dataset_id=None,
            location={},
            context={},
            language="en",
            unit=None,
            time={"value": "2024-01-01"},
            classification={},
            quality={"score": 0.9},
            confidence={"score": 0.95},
            provenance={"source": "sensor"},
            versions=["v1"],
            data_stage="raw",
        ),
        InformationUnit(
            information_id=ULID.new("INF_"),
            type="text",
            content={"subject": "pressure", "predicate": "value", "value": 1015.0},
            raw_reference={},
            source_id=ULID.new("SRC_"),
            document_id=ULID.new("DOC_"),
            dataset_id=None,
            location={},
            context={},
            language="en",
            unit=None,
            time={"value": "2024-01-01"},
            classification={},
            quality={"score": 0.85},
            confidence={"score": 0.88},
            provenance={"source": "sensor"},
            versions=["v1"],
            data_stage="raw",
        ),
    ]

    conflicts = await detect_conflicts(units)

    assert len(conflicts) == 2


def test_classify_difference_date():
    """Test classification of date differences."""
    unit_a = InformationUnit(
        information_id=ULID.new("INF_"),
        type="text",
        content={"subject": "temp", "predicate": "value", "value": 25.0},
        raw_reference={},
        source_id=ULID.new("SRC_"),
        document_id=ULID.new("DOC_"),
        dataset_id=None,
        location={},
        context={},
        language="en",
        unit=None,
        time={"value": "2024-01-01"},
        classification={},
        quality={"score": 0.8},
        confidence={"score": 0.9},
        provenance={"source": "sensor"},
        versions=["v1"],
        data_stage="raw",
    )
    unit_b = InformationUnit(
        information_id=ULID.new("INF_"),
        type="text",
        content={"subject": "temp", "predicate": "value", "value": 25.0},
        raw_reference={},
        source_id=ULID.new("SRC_"),
        document_id=ULID.new("DOC_"),
        dataset_id=None,
        location={},
        context={},
        language="en",
        unit=None,
        time={"value": "2024-01-02"},
        classification={},
        quality={"score": 0.8},
        confidence={"score": 0.9},
        provenance={"source": "sensor"},
        versions=["v1"],
        data_stage="raw",
    )

    result = classify_difference(unit_a, unit_b)
    assert result == "date"


def test_classify_difference_definition():
    """Test classification of definition differences."""
    unit_a = InformationUnit(
        information_id=ULID.new("INF_"),
        type="text",
        content={"subject": "temp", "predicate": "value", "value": 25.0},
        raw_reference={},
        source_id=ULID.new("SRC_"),
        document_id=ULID.new("DOC_"),
        dataset_id=None,
        location={},
        context={"definition": "Celsius"},
        language="en",
        unit=None,
        time={"value": "2024-01-01"},
        classification={},
        quality={"score": 0.8},
        confidence={"score": 0.9},
        provenance={"source": "sensor"},
        versions=["v1"],
        data_stage="raw",
    )
    unit_b = InformationUnit(
        information_id=ULID.new("INF_"),
        type="text",
        content={"subject": "temp", "predicate": "value", "value": 25.0},
        raw_reference={},
        source_id=ULID.new("SRC_"),
        document_id=ULID.new("DOC_"),
        dataset_id=None,
        location={},
        context={"definition": "Fahrenheit"},
        language="en",
        unit=None,
        time={"value": "2024-01-01"},
        classification={},
        quality={"score": 0.8},
        confidence={"score": 0.9},
        provenance={"source": "sensor"},
        versions=["v1"],
        data_stage="raw",
    )

    result = classify_difference(unit_a, unit_b)
    assert result == "definition"


def test_assess_severity_low():
    """Test severity assessment for low quality/confidence."""
    unit_a = InformationUnit(
        information_id=ULID.new("INF_"),
        type="text",
        content={"subject": "temp", "predicate": "value", "value": 25.0},
        raw_reference={},
        source_id=ULID.new("SRC_"),
        document_id=ULID.new("DOC_"),
        dataset_id=None,
        location={},
        context={},
        language="en",
        unit=None,
        time={"value": "2024-01-01"},
        classification={},
        quality={"score": 0.2},
        confidence={"score": 0.8},
        provenance={"source": "sensor"},
        versions=["v1"],
        data_stage="raw",
    )
    unit_b = InformationUnit(
        information_id=ULID.new("INF_"),
        type="text",
        content={"subject": "temp", "predicate": "value", "value": 27.0},
        raw_reference={},
        source_id=ULID.new("SRC_"),
        document_id=ULID.new("DOC_"),
        dataset_id=None,
        location={},
        context={},
        language="en",
        unit=None,
        time={"value": "2024-01-01"},
        classification={},
        quality={"score": 0.8},
        confidence={"score": 0.8},
        provenance={"source": "sensor"},
        versions=["v1"],
        data_stage="raw",
    )

    result = assess_severity(unit_a, unit_b)
    assert result == "low"


def test_assess_severity_high():
    """Test severity assessment for high quality/confidence."""
    unit_a = InformationUnit(
        information_id=ULID.new("INF_"),
        type="text",
        content={"subject": "temp", "predicate": "value", "value": 25.0},
        raw_reference={},
        source_id=ULID.new("SRC_"),
        document_id=ULID.new("DOC_"),
        dataset_id=None,
        location={},
        context={},
        language="en",
        unit=None,
        time={"value": "2024-01-01"},
        classification={},
        quality={"score": 0.9},
        confidence={"score": 0.95},
        provenance={"source": "sensor"},
        versions=["v1"],
        data_stage="raw",
    )
    unit_b = InformationUnit(
        information_id=ULID.new("INF_"),
        type="text",
        content={"subject": "temp", "predicate": "value", "value": 27.0},
        raw_reference={},
        source_id=ULID.new("SRC_"),
        document_id=ULID.new("DOC_"),
        dataset_id=None,
        location={},
        context={},
        language="en",
        unit=None,
        time={"value": "2024-01-01"},
        classification={},
        quality={"score": 0.85},
        confidence={"score": 0.9},
        provenance={"source": "sensor"},
        versions=["v1"],
        data_stage="raw",
    )

    result = assess_severity(unit_a, unit_b)
    assert result == "high"
