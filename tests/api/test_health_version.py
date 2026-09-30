"""API test for health version, build, and migration metadata per §41.14."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

#: The endpoint reports the highest migration on disk; the expectation is read
#: from the same place so adding a migration never makes this test a liar.
LATEST_MIGRATION = max(
    f.stem.split("_")[0]
    for f in Path("migrations/versions").glob("*.py")
    if not f.name.startswith("__")
)


def test_health_includes_migration_metadata():
    res = client.get("/v1/health")
    assert res.status_code == 200
    data = res.json()
    assert "migrations" in data
    m = data["migrations"]
    assert "latest_available" in m
    assert m["latest_available"] == LATEST_MIGRATION
    assert "applied" in m


def test_health_includes_build_info(monkeypatch):
    monkeypatch.setenv("INIS_GIT_SHA", "abcdef123456")
    monkeypatch.setenv("INIS_BUILT_AT", "2026-09-27T12:00:00Z")
    res = client.get("/v1/health")
    assert res.status_code == 200
    b = res.json()["build"]
    assert b["git_sha"] == "abcdef123456"
    assert b["built_at"] == "2026-09-27T12:00:00Z"


def test_health_ready_includes_migrations_and_build():
    res = client.get("/v1/health/ready")
    assert res.status_code == 200
    data = res.json()
    assert "migrations" in data
    assert "build" in data
