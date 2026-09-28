"""API test for health version, build, and migration metadata per §41.14."""

from __future__ import annotations

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_includes_migration_metadata():
    res = client.get("/v1/health")
    assert res.status_code == 200
    data = res.json()
    assert "migrations" in data
    m = data["migrations"]
    assert "latest_available" in m
    assert m["latest_available"] == "0010"
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
