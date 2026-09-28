"""§41.15 — the API version is declared once and agrees everywhere.

The version used to be hardcoded in three modules plus two data files; any
bump could silently miss one of them. These tests fail as soon as one surface
drifts from ``app.core.version.API_VERSION``.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

from app.core.version import API_VERSION
from app.main import API_VERSION as MAIN_API_VERSION
from app.main import app

_ROOT = Path(__file__).resolve().parents[3]


def test_api_version_is_2_0_0() -> None:
    """The released API version is the v2 semver and is a well-formed string."""
    assert API_VERSION == "2.0.0"
    assert API_VERSION.count(".") == 2


def test_main_uses_core_version() -> None:
    """``app.main`` re-exports the core constant and feeds the FastAPI app."""
    assert MAIN_API_VERSION is API_VERSION
    assert app.version == API_VERSION


def test_changelog_router_uses_core_version() -> None:
    """``/v1/changelog`` reports the core version, not a local literal."""
    from fastapi.testclient import TestClient

    from app.api.v1.system import changelog_router as module

    assert module._FALLBACK["current_version"] == API_VERSION
    body = TestClient(app).get("/v1/changelog").json()
    assert body["version"] == API_VERSION
    assert body["current_version"] == API_VERSION


def test_pyproject_matches_api_version() -> None:
    """``pyproject.toml`` and ``docs/changelog.json`` carry the same version."""
    pyproject = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["version"] == API_VERSION

    changelog = json.loads((_ROOT / "docs" / "changelog.json").read_text(encoding="utf-8"))
    assert changelog["current_version"] == API_VERSION
    assert changelog["history"][0]["version"] == API_VERSION
