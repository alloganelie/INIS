"""Changelog router exposing machine-readable API history per §41.15."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/changelog", tags=["system"])

# Canonical path for the machine-readable changelog.
_CHANGELOG_PATH = Path(__file__).resolve().parents[5] / "docs" / "changelog.json"

# Fallback used when docs/changelog.json is absent or unreadable.
_FALLBACK: dict[str, Any] = {
    "current_version": "0.1.0",
    "history": [
        {
            "version": "0.1.0",
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


@router.get(
    "",
    response_model=ChangelogResponse,
    summary="Get the machine-readable API changelog",
)
def get_changelog() -> ChangelogResponse:
    """Return the changelog loaded from docs/changelog.json (fallback built-in)."""
    data = _load_changelog()
    return ChangelogResponse(
        current_version=data.get("current_version", "0.1.0"),
        history=[ChangelogEntry(**e) for e in data.get("history", [])],
    )
