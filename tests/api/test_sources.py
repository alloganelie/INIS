"""Tests for Sources endpoints."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_create_source_success() -> None:
    """Ensure a valid Source can be created with a SRC_ ULID."""
    payload = {
        "name": "Official Statistical Office",
        "source_type": "rest_api",
        "url": "https://api.statistics.gov/v1",
        "description": "National open statistics API",
        "trust_level": 0.95,
    }
    response = client.post("/v1/sources", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["source_id"].startswith("SRC_")
    assert len(data["source_id"]) == len("SRC_") + 26
    assert data["name"] == payload["name"]
    assert data["source_type"] == payload["source_type"]
    assert data["status"] == "active"
    assert data["trust_level"] == 0.95


def test_get_source_by_id() -> None:
    """Ensure an existing Source can be retrieved by its ID."""
    payload = {
        "name": "Regulatory Registry",
        "source_type": "postgres",
    }
    create_res = client.post("/v1/sources", json=payload)
    assert create_res.status_code == 201
    source_id = create_res.json()["source_id"]

    get_res = client.get(f"/v1/sources/{source_id}")
    assert get_res.status_code == 200
    data = get_res.json()
    assert data["source_id"] == source_id
    assert data["name"] == payload["name"]


def test_get_source_not_found() -> None:
    """Ensure querying an unknown source ID returns 404."""
    response = client.get("/v1/sources/SRC_00000000000000000000000000")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_list_sources() -> None:
    """Ensure GET /v1/sources returns registered sources and supports filtering."""
    src1 = client.post("/v1/sources", json={"name": "Web Crawler Target", "source_type": "web_page"}).json()
    src2 = client.post("/v1/sources", json={"name": "Internal Data Warehouse", "source_type": "postgres"}).json()

    list_res = client.get("/v1/sources")
    assert list_res.status_code == 200
    data = list_res.json()
    assert "sources" in data or "items" in data
    source_ids = [s["source_id"] for s in data.get("sources", data.get("items", []))]
    assert src1["source_id"] in source_ids
    assert src2["source_id"] in source_ids

    # Test filtering by source_type
    filtered_res = client.get("/v1/sources?source_type=web_page")
    assert filtered_res.status_code == 200
    filtered_data = filtered_res.json()
    filtered_types = [s["source_type"] for s in filtered_data.get("sources", filtered_data.get("items", []))]
    assert all(st == "web_page" for st in filtered_types)


import pytest


@pytest.mark.asyncio
async def test_source_repository_direct_crud(tmp_path: any) -> None:
    """Ensure SourceRepository can create, get, and list sources in a database."""
    from sqlalchemy.ext.asyncio import create_async_engine
    from app.api.v1.sources.repository import SourceRepository

    db_file = tmp_path / "test_sources.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")

    # 1. Create
    data = {
        "name": "DB Source Alpha",
        "source_type": "rest_api",
        "url": "https://alpha.example.com",
        "metadata": {"tags": ["finance"]},
    }
    created = await SourceRepository.create(engine, data)
    assert created["source_id"].startswith("SRC_")
    assert created["name"] == "DB Source Alpha"
    assert created["metadata"] == {"tags": ["finance"]}

    # 2. Get
    fetched = await SourceRepository.get(engine, created["source_id"])
    assert fetched is not None
    assert fetched["source_id"] == created["source_id"]
    assert fetched["name"] == "DB Source Alpha"

    # Get non-existent
    assert await SourceRepository.get(engine, "SRC_NONEXISTENT") is None

    # 3. List
    all_sources = await SourceRepository.list(engine)
    assert len(all_sources) >= 1
    assert any(s["source_id"] == created["source_id"] for s in all_sources)

    # List with filter
    filtered = await SourceRepository.list(engine, source_type="rest_api")
    assert len(filtered) >= 1
    assert all(s["source_type"] == "rest_api" for s in filtered)

    await engine.dispose()


def test_sources_endpoints_with_database_engine(tmp_path: any, monkeypatch: any) -> None:
    """Ensure /v1/sources routes interact with the database when INIS_DATABASE_URL is set."""
    from app.api.v1.sources.repository import set_database_engine
    from sqlalchemy.ext.asyncio import create_async_engine

    db_file = tmp_path / "endpoint_sources.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)

    engine = create_async_engine(db_url)
    set_database_engine(engine)

    try:
        # POST
        payload = {
            "name": "Persisted DB Source",
            "source_type": "database",
            "url": "postgresql://localhost:5432/mydb",
            "metadata": {"env": "prod"},
        }
        create_res = client.post("/v1/sources", json=payload)
        assert create_res.status_code == 201
        created_data = create_res.json()
        src_id = created_data["source_id"]
        assert src_id.startswith("SRC_")

        # GET by ID
        get_res = client.get(f"/v1/sources/{src_id}")
        assert get_res.status_code == 200
        assert get_res.json()["name"] == "Persisted DB Source"

        # GET list
        list_res = client.get("/v1/sources")
        assert list_res.status_code == 200
        items = list_res.json().get("sources", list_res.json().get("items", []))
        assert any(s["source_id"] == src_id for s in items)
    finally:
        set_database_engine(None)

