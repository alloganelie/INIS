"""§24.2/§18.2 — l'empreinte annoncée décrit les octets servis, et un artefact
supprimé n'est plus téléchargeable.

Deux promesses du plan L1 qui n'étaient pas tenues :

* le téléchargement ne posait **aucun** en-tête d'intégrité : un client ne
  pouvait pas vérifier que les octets reçus étaient ceux annoncés par le §24.2 ;
* un artefact `status="deleted"` (ou supprimé logiquement, décision ``0016``)
  restait téléchargeable par qui connaissait son identifiant.

Les deux passent par le système existant : la garde §19.3 auditée
(`_require_read_access`), la même projection d'artefact, la même route. Rien de
parallèle n'est introduit.
"""

from __future__ import annotations

import hashlib

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

ARTIFACT_ID = "ART_2026_910001"
REQUEST_ID = "REQ_01M3T0000000000000000000001"
STORAGE_REF = "s3://inis-artifacts/colis.csv"

#: Les octets servis et l'empreinte publiée qui les décrit — la cohérence que le
#: téléchargement vérifie avant de répondre (§24.2).
PAYLOAD = b"a,b\n1,2\n"
PAYLOAD_SHA256 = hashlib.sha256(PAYLOAD).hexdigest()

#: Le corps d'un refus pour artefact supprimé, de façon stable et sans métadonnée.
DELETED_DETAIL = "Artifact is gone"

RECORD: dict = {
    "artifact_id": ARTIFACT_ID,
    "request_id": REQUEST_ID,
    "artifact_type": "dataset",
    "file_name": "colis.csv",
    "mime_type": "text/csv",
    "version": "1.0.0",
    "size_bytes": len(PAYLOAD),
    "sha256": PAYLOAD_SHA256,
    "storage_ref": STORAGE_REF,
    "purpose": "livraison",
    "source_ids": ["SRC_01M3T0000000000000000000001"],
    "dataset_ids": [],
    "transformation_ids": [],
    "quality_score": 0.9,
    "confidence_score": 0.8,
    "provenance_complete": True,
    "status": "available",
    "created_at": "2026-09-30T00:00:00+00:00",
    "deleted_at": None,
}


class RecordingStorage:
    """Object-store double whose bytes can be tampered with on purpose."""

    def __init__(self, payload: bytes = PAYLOAD) -> None:
        self.payload = payload
        self.downloads: list[str] = []

    def download(self, key: str) -> bytes:
        """Return (possibly corrupted) bytes and remember the read."""
        self.downloads.append(key)
        return self.payload


@pytest.fixture
def storage(monkeypatch: pytest.MonkeyPatch) -> RecordingStorage:
    """Install the object-store double on the download route."""
    import importlib

    router_module = importlib.import_module("app.api.v1.artifacts.router")
    double = RecordingStorage()
    monkeypatch.setattr(router_module, "build_object_storage", lambda: double)
    return double


@pytest.fixture
def artifact(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Serve one artifact through the routes, without a database."""
    import importlib

    from app.storage.repositories import artifact_repository as artifact_module

    router_module = importlib.import_module("app.api.v1.artifacts.router")
    monkeypatch.setattr(router_module, "get_database_engine", lambda: object())

    async def fake_get(_engine, artifact_id: str):
        return dict(RECORD) if artifact_id == ARTIFACT_ID else None

    async def fake_list_for_request(_engine, request_id: str, limit: int = 100):
        return [dict(RECORD)] if request_id == REQUEST_ID else []

    async def fake_list_all(_engine, limit: int = 100):
        return [dict(RECORD)]

    monkeypatch.setattr(artifact_module.ArtifactRepository, "get", fake_get)
    monkeypatch.setattr(
        artifact_module.ArtifactRepository, "list_for_request", fake_list_for_request
    )
    monkeypatch.setattr(artifact_module.ArtifactRepository, "list_all", fake_list_all)
    return dict(RECORD)


def _mark_deleted(monkeypatch: pytest.MonkeyPatch, *, status: str, deleted_at: str | None) -> None:
    """Mark the served record as deleted, one way or the other."""
    monkeypatch.setitem(RECORD, "status", status)
    monkeypatch.setitem(RECORD, "deleted_at", deleted_at)


class TestTheIntegrityHeadersDescribeTheServedBytes:
    """§24.2 — l'empreinte annoncée est celle des octets effectivement servis."""

    def test_the_checksum_is_the_digest_of_the_returned_bytes(
        self, artifact: dict, storage: RecordingStorage
    ) -> None:
        response = client.get(f"/v1/artifacts/{ARTIFACT_ID}/download")

        assert response.status_code == 200
        assert response.content == PAYLOAD
        assert response.headers["x-checksum-sha256"] == hashlib.sha256(response.content).hexdigest()
        assert response.headers["x-checksum-sha256"] == PAYLOAD_SHA256
        assert response.headers["etag"] == f'"{PAYLOAD_SHA256}"'

    def test_the_headers_are_stable_across_calls(
        self, artifact: dict, storage: RecordingStorage
    ) -> None:
        first = client.get(f"/v1/artifacts/{ARTIFACT_ID}/download")
        second = client.get(f"/v1/artifacts/{ARTIFACT_ID}/download")

        assert first.headers["etag"] == second.headers["etag"]
        assert first.headers["x-checksum-sha256"] == second.headers["x-checksum-sha256"]

    def test_a_matching_condition_returns_304_without_a_body(
        self, artifact: dict, storage: RecordingStorage
    ) -> None:
        head = client.get(f"/v1/artifacts/{ARTIFACT_ID}/download")

        second = client.get(
            f"/v1/artifacts/{ARTIFACT_ID}/download",
            headers={"If-None-Match": head.headers["etag"]},
        )

        assert second.status_code == 304
        assert second.content == b""
        assert second.headers["etag"] == head.headers["etag"]
        assert second.headers["x-checksum-sha256"] == PAYLOAD_SHA256

    def test_a_different_condition_returns_the_file(
        self, artifact: dict, storage: RecordingStorage
    ) -> None:
        response = client.get(
            f"/v1/artifacts/{ARTIFACT_ID}/download", headers={"If-None-Match": '"autre"'}
        )

        assert response.status_code == 200
        assert response.content == PAYLOAD

    def test_bytes_that_do_not_match_the_published_digest_are_refused(
        self, artifact: dict, storage: RecordingStorage
    ) -> None:
        """Un objet corrompu n'est pas servi sous l'empreinte publiée (§37)."""
        storage.payload = b"octets-remplaces"

        response = client.get(f"/v1/artifacts/{ARTIFACT_ID}/download")

        assert response.status_code == 502
        assert "do not match the digest" in response.json()["detail"]
        assert "etag" not in response.headers, "aucune empreinte n'est annoncée sur un refus"
        assert "x-checksum-sha256" not in response.headers
        # Et la corruption n'est pas « corrigée » en douce : les octets servis sont
        # ceux du stockage, et l'empreinte publiée reste celle du record.
        assert PAYLOAD_SHA256 not in response.text

    def test_a_corrupted_object_cannot_answer_304(
        self, artifact: dict, storage: RecordingStorage
    ) -> None:
        """Une empreinte différente ne peut pas valider une condition périmée."""
        head = client.get(f"/v1/artifacts/{ARTIFACT_ID}/download")
        storage.payload = b"octets-remplaces"

        response = client.get(
            f"/v1/artifacts/{ARTIFACT_ID}/download",
            headers={"If-None-Match": head.headers["etag"]},
        )

        assert response.status_code == 502, "un contenu changé ne doit jamais répondre 304"


class TestADeletedArtifactIsNotDownloadable:
    """§18.2 / décision ``0016`` — supprimé veut dire non téléchargeable."""

    def test_a_deleted_status_refuses_the_download(
        self, artifact: dict, storage: RecordingStorage, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Le refus tombe **avant** toute lecture du stockage."""
        _mark_deleted(monkeypatch, status="deleted", deleted_at=None)

        response = client.get(f"/v1/artifacts/{ARTIFACT_ID}/download")

        assert response.status_code == 410
        assert DELETED_DETAIL in response.json()["detail"]
        assert storage.downloads == [], "un artefact supprimé ne doit pas être lu"
        assert ARTIFACT_ID not in response.text and "colis.csv" not in response.text

    def test_a_soft_deleted_artifact_is_refused_too(
        self, artifact: dict, storage: RecordingStorage, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """La suppression logique (0016) vaut refus, même si le statut est intact."""
        _mark_deleted(monkeypatch, status="available", deleted_at="2026-09-30T12:00:00+00:00")

        response = client.get(f"/v1/artifacts/{ARTIFACT_ID}/download")

        assert response.status_code == 410
        assert storage.downloads == []

    def test_the_detail_route_does_not_bypass_the_refusal(
        self, artifact: dict, storage: RecordingStorage, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Ni les métadonnées, ni l'URL de l'ID ne contournent le refus."""
        _mark_deleted(monkeypatch, status="deleted", deleted_at=None)

        detail = client.get(f"/v1/artifacts/{ARTIFACT_ID}")
        download = client.get(f"/v1/artifacts/{ARTIFACT_ID}/download")

        assert detail.status_code == download.status_code == 410
        assert detail.json() == download.json()

    def test_a_deleted_artifact_is_not_listed(
        self, artifact: dict, storage: RecordingStorage, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Une liste n'expose pas ce qui n'est plus téléchargeable."""
        _mark_deleted(monkeypatch, status="deleted", deleted_at=None)

        response = client.get(f"/v1/artifacts?request_id={REQUEST_ID}")

        assert response.status_code == 200
        assert response.json() == {"artifacts": [], "total": 0}

    def test_neither_the_history_nor_the_lineage_is_readable(
        self, artifact: dict, storage: RecordingStorage, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Une version ou un lignage ne doivent pas non plus exposer un supprimé."""
        _mark_deleted(monkeypatch, status="deleted", deleted_at=None)

        versions = client.get(f"/v1/artifacts/{ARTIFACT_ID}/versions")
        lineage = client.get(f"/v1/artifacts/{ARTIFACT_ID}/lineage")

        assert versions.status_code == lineage.status_code == 410

    def test_the_refusal_is_audited_with_its_reason(
        self,
        artifact: dict,
        storage: RecordingStorage,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """La raison exacte (« status=deleted ») vit dans l'audit, pas dans la réponse."""
        import importlib

        router_module = importlib.import_module("app.api.v1.artifacts.router")
        _mark_deleted(monkeypatch, status="deleted", deleted_at=None)
        written: list[dict] = []

        class _SpyWriter:
            def __init__(self, engine=None) -> None:
                self._engine = engine

            async def write(self, event: dict, **_kwargs) -> dict:
                written.append(dict(event))
                return dict(event)

        monkeypatch.setattr(router_module, "AuditWriter", _SpyWriter)
        # Le refus d'autorisation s'écrit d'abord (allow) : on isole le refus de
        # suppression en le cherchant par sa raison.
        client.get(f"/v1/artifacts/{ARTIFACT_ID}/download")

        denied = [event for event in written if event["result"] == "denied"]
        assert denied, f"aucun refus audité : {written}"
        assert "deleted" in denied[-1]["reason"]
        assert denied[-1]["resource_id"] == ARTIFACT_ID
        assert denied[-1]["action"] == "artifact.read"

    def test_a_live_artifact_is_still_downloadable_after_the_check(
        self, artifact: dict, storage: RecordingStorage
    ) -> None:
        """Contre-preuve : ce qui n'est pas supprimé reste servi."""
        response = client.get(f"/v1/artifacts/{ARTIFACT_ID}/download")

        assert response.status_code == 200
        assert response.content == PAYLOAD


class TestAuthorizationErrorsCarryNoIntegrityHeaders:
    """§19.3 — un refus d'autorisation n'annonce aucune empreinte."""

    @pytest.fixture(autouse=True)
    def _auth_on(self) -> None:
        from app.api.middleware.auth_middleware import set_strict_auth_mode

        set_strict_auth_mode(True)
        yield
        set_strict_auth_mode(None)

    def test_a_refused_caller_gets_no_etag_and_a_constant_body(
        self, artifact: dict, storage: RecordingStorage
    ) -> None:
        import time

        from app.api.middleware.auth_middleware import create_jwt_token

        token = create_jwt_token(
            {"sub": "agent-sans-role", "scopes": ["search"], "exp": time.time() + 3600}
        )
        response = client.get(
            f"/v1/artifacts/{ARTIFACT_ID}/download",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 403
        assert "etag" not in response.headers
        assert "x-checksum-sha256" not in response.headers
        assert PAYLOAD_SHA256 not in response.text
        assert storage.downloads == []
