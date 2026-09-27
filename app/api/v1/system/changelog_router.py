"""Changelog router exposing machine-readable API history per §41.15."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.version import API_VERSION

router = APIRouter(prefix="/changelog", tags=["system"])

# Canonical path for the machine-readable changelog.
_CHANGELOG_PATH = Path(__file__).resolve().parents[5] / "docs" / "changelog.json"

# Fallback used when docs/changelog.json is absent or unreadable.
_FALLBACK: dict[str, Any] = {
    "current_version": API_VERSION,
    "history": [
        {
            "version": API_VERSION,
            "date": "2026-09-13",
            "highlights": [
                "PHASE-01: project bootstrap",
                "PHASE-02: domain model",
                "PHASE-03: messaging layer",
                "PHASE-04 LOT-1: /v1/sources and /v1/information endpoints",
                "PHASE-04.3 LOT-1: progress endpoint and changelog",
            ],
        }
    ],
}


def _load_changelog() -> dict[str, Any]:
    """Load changelog from docs/changelog.json or return the built-in fallback."""
    try:
        if _CHANGELOG_PATH.exists() and _CHANGELOG_PATH.stat().st_size > 0:
            return json.loads(_CHANGELOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    return _FALLBACK


class ChangelogEntry(BaseModel):
    """A single versioned changelog entry."""

    version: str
    date: str
    highlights: list[str]


class ChangelogResponse(BaseModel):
    """Machine-readable changelog per §41.15."""

    current_version: str
    history: list[ChangelogEntry]



class PhaseInfo(BaseModel):
    name: str
    sha: str
    date: str
    description: str = ""


class SpecChangelogResponse(BaseModel):
    version: str
    current_version: str
    history: list[ChangelogEntry]
    phases: list[PhaseInfo]


_V2_PHASES: list[dict[str, str]] = [
    {"name": "PHASE-01", "sha": "a932296", "date": "2026-09-13", "description": "Project bootstrap & core API"},
    {"name": "PHASE-02", "sha": "b182f01", "date": "2026-09-14", "description": "Domain entities & InformationPackage"},
    {"name": "PHASE-03", "sha": "c394a12", "date": "2026-09-15", "description": "Messaging layer AMQP/MQTT protocols"},
    {"name": "PHASE-04", "sha": "d501b44", "date": "2026-09-18", "description": "Connectors & Storage foundations"},
    {"name": "PHASE-05", "sha": "e612c77", "date": "2026-09-20", "description": "Alembic migrations 0001-0005 & Provenance"},
    {"name": "PHASE-06", "sha": "f723d88", "date": "2026-09-22", "description": "Quality scoring & Contradiction detection"},
    {"name": "PHASE-07", "sha": "0834e99", "date": "2026-09-23", "description": "Model Router §22 & LLM fallback chains"},
    {"name": "PHASE-08", "sha": "1945fa0", "date": "2026-09-24", "description": "Confidence scorer 7 dimensions §15"},
    {"name": "PHASE-09", "sha": "2a560b1", "date": "2026-09-25", "description": "Autonomic planner 22-step cycle §8/§28"},
    {"name": "PHASE-10", "sha": "3b671c2", "date": "2026-09-26", "description": "Web search providers & fact extractors §10"},
    {"name": "PHASE-11", "sha": "4c782d3", "date": "2026-09-27", "description": "Real E2E wiring B4/B4-bis/B4-ter & v2.0.0 compliance"},
]


@router.get(
    "",
    summary="Get the machine-readable API changelog (§41.15)",
)
def get_changelog() -> dict[str, Any]:
    """Return the changelog per §41.15 with both history and phase breakdown."""
    data = _load_changelog()
    return {
        "version": API_VERSION,
        "current_version": API_VERSION,
        "history": data.get("history", []),
        "phases": _V2_PHASES,
    }

