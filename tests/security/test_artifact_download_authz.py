"""§19.3 — télécharger un artefact exige une autorisation, pas seulement un ID.

Ce fichier prouve trois choses distinctes :

1. **la décision** (§19.3) : rôles artefact, traduction des périmètres, refus
   inconditionnel d'une ressource ``restricted``, conditions ABAC ;
2. **la route** : la même décision est appliquée par le vrai middleware, avant
   toute lecture quand l'authentification est configurée — donc un appelant non
   autorisé n'apprend rien, ni par l'URL, ni par le corps de la réponse, et la
   route de détail ne contourne pas celle de téléchargement ;
3. **la trace** : l'accord comme le refus laissent un événement §20, et le
   téléchargement autorisé fonctionne toujours (octets + nom de fichier).
"""

from __future__ import annotations

import importlib
import time
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.middleware.auth_middleware import (
    create_jwt_token,
    set_strict_auth_mode,
)
from app.domain.value_objects.ulid import ULID
from app.main import app
from app.security.authz.artifact_access import (
    ARTIFACT_ROLE_PERMISSIONS,
    AccessDecision,
    artifact_checker,
    authorize_artifact,
    role_for_scopes,
    subject_from_identity,
)

client = TestClient(app)

ARTIFACT_ID = "ART_2026_900001"
STORAGE_REF = "s3://inis-artifacts/colis.json"

#: Un identifiant plausible qui n'existe pas : la route doit répondre 404.
UNKNOWN_ARTIFACT_ID = "ART_2026_999999"

#: Le module (et non l'objet ``APIRouter``) : le paquet ``app.api.v1.artifacts``
#: réexporte ``router``, donc ``…artifacts.router`` en attribut pointe sur
#: l'``APIRouter``. Patcher les attributs du module exige de le charger ici.
artifacts_router = importlib.import_module("app.api.v1.artifacts.router")

#: A §24.2 record as the database holds it. ``classification`` is *not* a column
#: of the table; it is an optional attribute the delivery adds when it knows the
#: data is sensitive, which is exactly what §19.3's ABAC reads.
RECORD: dict[str, Any] = {
    "artifact_id": ARTIFACT_ID,
    "request_id": "REQ_01M3T00000000000000000000B2",
    "artifact_type": "dataset",
    "file_name": "colis.json",
    "mime_type": "application/json",
    "version": "1.0.0",
    "size_bytes": 11,
    "sha256": "a" * 64,
    "storage_ref": STORAGE_REF,
    "purpose": "livraison complète",
    "source_ids": ["SRC_01M3T00000000000000000000C3"],
    "dataset_ids": [],
    "transformation_ids": [],
    "quality_score": 0.9,
    "confidence_score": 0.8,
    "provenance_complete": True,
    "status": "available",
    "created_at": "2026-09-30T00:00:00+00:00",
}


class FakeStorage:
    """Object-store double returning the delivered bytes (§24.2)."""

    def __init__(self, payload: bytes = b"colis-bytes") -> None:
        self.payload = payload
        self.downloads: list[str] = []

    def download(self, key: str) -> bytes:
        """Return the stored bytes and remember the key that was read."""
        self.downloads.append(key)
        return self.payload


@pytest.fixture
def artifact_row(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Serve one artifact through the routes without a database."""
    from app.storage.repositories import artifact_repository as artifact_module

    monkeypatch.setattr(artifacts_router, "get_database_engine", lambda: object())

    async def fake_get(_engine: Any, artifact_id: str) -> dict[str, Any] | None:
        return dict(RECORD) if artifact_id == ARTIFACT_ID else None

    async def fake_list_for_request(
        _engine: Any, request_id: str, limit: int = 100
    ) -> list[dict[str, Any]]:
        return [dict(RECORD)] if request_id == RECORD["request_id"] else []

    async def fake_list_all(_engine: Any, limit: int = 100) -> list[dict[str, Any]]:
        return [dict(RECORD)]

    monkeypatch.setattr(artifact_module.ArtifactRepository, "get", fake_get)
    monkeypatch.setattr(
        artifact_module.ArtifactRepository, "list_for_request", fake_list_for_request
    )
    monkeypatch.setattr(artifact_module.ArtifactRepository, "list_all", fake_list_all)
    return dict(RECORD)


@pytest.fixture
def storage(monkeypatch: pytest.MonkeyPatch) -> FakeStorage:
    """Install the object-store double used by the download route."""
    fake = FakeStorage()
    monkeypatch.setattr(artifacts_router, "build_object_storage", lambda: fake)
    return fake


@pytest.fixture
def strict_auth() -> Any:
    """Turn authentication on with the middleware's own switch, then restore it."""
    set_strict_auth_mode(True)
    yield
    set_strict_auth_mode(None)


def auth_headers(*scopes: str, actor: str = "agent-under-test") -> dict[str, str]:
    """Return an ``Authorization`` header for a valid JWT carrying *scopes*."""
    token = create_jwt_token(
        {"sub": actor, "scopes": list(scopes), "exp": time.time() + 3600}
    )
    return {"Authorization": f"Bearer {token}"}


class TestTheRoutesRefuseWithoutPermission:
    """La même décision, appliquée par la vraie route et le vrai middleware."""

    def test_an_authorized_caller_downloads_the_file(
        self, artifact_row: dict[str, Any], storage: FakeStorage, strict_auth: Any
    ) -> None:
        """Le téléchargement autorisé fonctionne toujours, octets et nom compris."""
        response = client.get(
            f"/v1/artifacts/{ARTIFACT_ID}/download", headers=auth_headers("read")
        )

        assert response.status_code == 200
        assert response.content == b"colis-bytes"
        assert 'filename="colis.json"' in response.headers["content-disposition"]
        assert response.headers["content-type"].startswith("application/json")
        assert storage.downloads, "les octets viennent bien du stockage objet"

    def test_an_unauthorized_caller_is_refused_explicitly(
        self, artifact_row: dict[str, Any], storage: FakeStorage, strict_auth: Any
    ) -> None:
        """Refus explicite : 403, et **rien** d'autre."""
        response = client.get(
            f"/v1/artifacts/{ARTIFACT_ID}/download", headers=auth_headers("search")
        )

        assert response.status_code == 403
        assert response.json()["detail"].startswith("Access denied")
        assert storage.downloads == [], "un refus ne doit pas lire le stockage"

    def test_a_refusal_leaks_no_metadata(
        self, artifact_row: dict[str, Any], storage: FakeStorage, strict_auth: Any
    ) -> None:
        """Aucune fuite : ni identifiant, ni nom, ni empreinte, ni référence."""
        response = client.get(
            f"/v1/artifacts/{ARTIFACT_ID}/download", headers=auth_headers("search")
        )
        body = response.text

        for secret in (
            ARTIFACT_ID,
            RECORD["request_id"],
            RECORD["file_name"],
            RECORD["sha256"],
            STORAGE_REF,
            str(RECORD["size_bytes"]),
        ):
            assert secret not in body, f"la réponse refusée expose « {secret} »"
        assert "role" not in body.lower(), "la raison de politique reste dans l'audit"

    def test_the_detail_route_is_not_a_bypass(
        self, artifact_row: dict[str, Any], storage: FakeStorage, strict_auth: Any
    ) -> None:
        """Même interdiction pour les métadonnées : l'ID ne contourne pas l'URL."""
        detail = client.get(f"/v1/artifacts/{ARTIFACT_ID}", headers=auth_headers("search"))
        download = client.get(
            f"/v1/artifacts/{ARTIFACT_ID}/download", headers=auth_headers("search")
        )

        assert detail.status_code == download.status_code == 403
        assert detail.json() == download.json(), "un seul et même refus"

    def test_the_same_artifact_is_readable_by_an_authorized_caller(
        self, artifact_row: dict[str, Any], storage: FakeStorage, strict_auth: Any
    ) -> None:
        """Contre-preuve : ce qui est refusé à l'un est servi à l'autre."""
        response = client.get(f"/v1/artifacts/{ARTIFACT_ID}", headers=auth_headers("read"))

        assert response.status_code == 200
        assert response.json()["artifact_id"] == ARTIFACT_ID
        assert response.json()["file_name"] == "colis.json"

    def test_a_request_without_credentials_is_a_401(self, artifact_row: dict[str, Any], strict_auth: Any) -> None:
        """Sans identité, la question ne se pose même pas (§19.2)."""
        response = client.get(f"/v1/artifacts/{ARTIFACT_ID}/download")

        assert response.status_code == 401

    def test_the_list_does_not_show_what_cannot_be_read(
        self, artifact_row: dict[str, Any], storage: FakeStorage, strict_auth: Any
    ) -> None:
        """Une liste n'est pas une autorisation : elle est filtrée (§19.3)."""
        refused = client.get(
            f"/v1/artifacts?request_id={RECORD['request_id']}", headers=auth_headers("search")
        )
        allowed = client.get(
            f"/v1/artifacts?request_id={RECORD['request_id']}", headers=auth_headers("read")
        )

        assert refused.status_code == 403
        assert allowed.status_code == 200
        assert allowed.json()["total"] == 1

    def test_a_restricted_artifact_is_not_listed_for_a_reader(
        self,
        artifact_row: dict[str, Any],
        storage: FakeStorage,
        strict_auth: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Même lisible par son rôle, un artefact restreint ne doit pas apparaître."""
        monkeypatch.setitem(artifact_row, "classification", "restricted")

        def _deny_only_the_record(subject: Any, record: Any = None, **_kwargs: Any) -> Any:
            """Accorder le contrôle d'entrée, refuser la ligne elle-même."""
            if record is None:
                return AccessDecision(allowed=True, reason="Access granted")
            return AccessDecision(
                allowed=False, reason="Resource classification is restricted"
            )

        monkeypatch.setattr(artifacts_router, "authorize_artifact", _deny_only_the_record)
        response = client.get(
            f"/v1/artifacts?request_id={RECORD['request_id']}", headers=auth_headers("read")
        )

        assert response.status_code == 200
        assert response.json()["artifacts"] == []
        assert response.json()["total"] == 0

    def test_an_unknown_artifact_is_still_a_404_for_an_authorized_caller(
        self, artifact_row: dict[str, Any], storage: FakeStorage, strict_auth: Any
    ) -> None:
        """Le contrat existant ne change pas : un ID inconnu reste 404."""
        response = client.get(
            f"/v1/artifacts/{UNKNOWN_ARTIFACT_ID}", headers=auth_headers("read")
        )
        assert response.status_code == 404


class TestTheDecisionIsAudited:
    """§20 — l'accord et le refus sont tracés, avec leur raison."""

    def test_a_refusal_writes_an_audit_event(
        self,
        artifact_row: dict[str, Any],
        storage: FakeStorage,
        strict_auth: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Le refus est audité avec sa raison, pas seulement renvoyé au client."""
        written: list[dict[str, Any]] = []

        class _SpyWriter:
            def __init__(self, engine: Any = None) -> None:
                self._engine = engine

            async def write(self, event: dict, **_kwargs: Any) -> dict:
                written.append(dict(event))
                return dict(event)

        monkeypatch.setattr(artifacts_router, "AuditWriter", _SpyWriter)

        client.get(f"/v1/artifacts/{ARTIFACT_ID}/download", headers=auth_headers("search"))

        events = [event for event in written if event["result"] == "denied"]
        assert len(events) == 1, f"un refus = un événement (§20), obtenu : {written}"
        event = events[0]
        assert event["actor_id"] == "agent-under-test"
        assert event["action"] == "artifact.read"
        assert event["resource_type"] == "artifact"
        assert event["resource_id"] == ARTIFACT_ID
        assert event["result"] == "denied"
        assert "no artifact role" in event["reason"]

    def test_an_allowed_access_writes_an_audit_event(
        self,
        artifact_row: dict[str, Any],
        storage: FakeStorage,
        strict_auth: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Un accès accordé est audité aussi : l'audit n'est pas que les échecs."""
        written: list[dict[str, Any]] = []

        class _SpyWriter:
            def __init__(self, engine: Any = None) -> None:
                self._engine = engine

            async def write(self, event: dict, **_kwargs: Any) -> dict:
                written.append(dict(event))
                return dict(event)

        monkeypatch.setattr(artifacts_router, "AuditWriter", _SpyWriter)

        response = client.get(
            f"/v1/artifacts/{ARTIFACT_ID}/download", headers=auth_headers("read")
        )

        assert response.status_code == 200
        successes = [event for event in written if event["result"] == "success"]
        assert successes, f"aucun événement d'accord obtenu : {written}"
        assert successes[0]["reason"] == "Access granted"


class TestTheRealDatabase:
    """Les mêmes décisions, sur le **vrai** PostgreSQL (lignes et audit)."""

    @pytest.fixture(autouse=True)
    def _real_engine(self, db_url: str, monkeypatch: pytest.MonkeyPatch) -> Any:
        """Bind the routes to the migrated test database (one engine per loop)."""
        from app.storage.database.engine import set_default_engine
        from app.storage.database.session import reset_session_maker

        monkeypatch.setenv("INIS_DATABASE_URL", db_url)
        monkeypatch.setenv("INIS_NULL_POOL", "1")
        set_default_engine(None)
        reset_session_maker()
        yield
        set_default_engine(None)
        reset_session_maker()

    @pytest.fixture
    def stored_artifact(self, db_url: str) -> dict[str, Any]:
        """Insert one real §24.2 artifact row, in its own short-lived loop."""
        import asyncio

        from app.storage.database.engine import create_engine
        from app.storage.repositories.artifact_repository import ArtifactRepository

        record = {
            **RECORD,
            "artifact_id": f"ART_2026_9{uuid.uuid4().int % 99999:05d}",
            "request_id": ULID.new("REQ_"),
        }

        async def insert() -> None:
            engine = create_engine(db_url)
            try:
                await ArtifactRepository.create(engine, record)
            finally:
                await engine.dispose()

        asyncio.run(insert())
        return record

    def test_an_authorized_download_serves_the_stored_row_and_is_audited(
        self,
        stored_artifact: dict[str, Any],
        storage: FakeStorage,
        strict_auth: Any,
    ) -> None:
        """Autorisé : les octets sortent, et l'accord est en base (§20)."""
        response = client.get(
            f"/v1/artifacts/{stored_artifact['artifact_id']}/download",
            headers=auth_headers("read", actor="audited-reader"),
        )

        assert response.status_code == 200
        assert response.content == b"colis-bytes"
        assert self._audit_events("audited-reader")[-1]["result"] == "success"

    def test_a_refusal_on_a_real_row_is_audited_without_leak(
        self,
        stored_artifact: dict[str, Any],
        storage: FakeStorage,
        strict_auth: Any,
    ) -> None:
        """Refusé : 403 sans métadonnée, et le refus est lisible dans l'audit."""
        response = client.get(
            f"/v1/artifacts/{stored_artifact['artifact_id']}/download",
            headers=auth_headers("search", actor="audited-refuser"),
        )

        assert response.status_code == 403
        assert stored_artifact["artifact_id"] not in response.text
        events = self._audit_events("audited-refuser")
        assert events[-1]["result"] == "denied"
        assert events[-1]["resource_id"] == stored_artifact["artifact_id"]
        assert "no artifact role" in events[-1]["reason"]

    def test_an_unknown_artifact_on_the_real_schema_is_a_404(
        self, stored_artifact: dict[str, Any], storage: FakeStorage, strict_auth: Any
    ) -> None:
        """Le 404 du contrat reste un 404, même autorisé (§32)."""
        response = client.get(
            f"/v1/artifacts/{UNKNOWN_ARTIFACT_ID}/download", headers=auth_headers("read")
        )
        assert response.status_code == 404

    @staticmethod
    def _audit_events(actor_id: str) -> list[dict[str, Any]]:
        """Read back the §20 events the route wrote for *actor_id*."""
        import asyncio

        from app.governance.audit.audit_writer import AuditWriter
        from app.storage.database.engine import create_engine, get_default_engine

        async def read() -> list[dict[str, Any]]:
            engine = get_default_engine() or create_engine()
            return await AuditWriter.list_events_from_db(engine, actor_id)

        return asyncio.run(read())

class TestThePolicyDecision:
    """§19.3 — la décision elle-même, avant toute question de route."""

    def test_a_reader_may_read_a_public_artifact(self) -> None:

        subject = subject_from_identity("agent-a", ["read"])
        decision = authorize_artifact(subject, RECORD, require_role=True)
        assert decision.allowed is True

    def test_a_writer_and_an_admin_may_read_too(self) -> None:
        for scope in ("write", "admin"):
            subject = subject_from_identity("agent-a", [scope])
            assert authorize_artifact(subject, RECORD, require_role=True).allowed is True

    def test_an_identified_caller_without_role_is_refused(self) -> None:
        """Sans rôle artefact, l'appelant est refusé — et la raison le dit."""
        subject = subject_from_identity("agent-b", ["search"])
        decision = authorize_artifact(subject, RECORD, require_role=True)
        assert decision.allowed is False
        assert "no artifact role" in decision.reason
        assert "search" in decision.reason

    def test_a_role_without_the_read_permission_is_refused(self) -> None:
        """Le RBAC §19.3 porte la décision, pas seulement la présence d'un rôle."""
        subject = {"agent_id": "agent-c", "role": "artifact_writer"}
        restricted_checker = artifact_checker()
        restricted_checker.policy_evaluator.rbac_engine.add_role(
            "artifact_writer", {"write:artifact"}
        )
        decision = authorize_artifact(
            subject, RECORD, require_role=True, checker=restricted_checker
        )
        assert decision.allowed is False
        assert "Role 'artifact_writer' lacks permission" in decision.reason

    def test_a_restricted_artifact_is_refused_even_without_authentication(self) -> None:
        """Le classement prime : ``restricted`` n'est jamais lisible (§19.3)."""
        subject = subject_from_identity(None, None)
        restricted = {**RECORD, "classification": "restricted"}
        decision = authorize_artifact(subject, restricted)
        assert decision.allowed is False
        assert decision.reason == "Resource classification is restricted"

    def test_an_abac_condition_is_applied(self) -> None:
        """Une condition ABAC (« même requête ») est évaluée, pas contournée."""
        conditioned = {
            **RECORD,
            "conditions": {"request_id": {"operator": "equals", "value": RECORD["request_id"]}},
        }
        decided = authorize_artifact(subject_from_identity("agent-a", ["read"]), conditioned)
        assert decided.allowed is True

        other = {
            **RECORD,
            "conditions": {"request_id": {"operator": "equals", "value": "REQ_autre"}},
        }
        refused = authorize_artifact(subject_from_identity("agent-a", ["read"]), other)
        assert refused.allowed is False
        assert refused.reason == "Attribute-based conditions not satisfied"

    def test_the_roles_are_the_l9_3_ones_without_a_second_table(self) -> None:
        """La table de rôles vient du module, et les périmètres la traduisent."""
        assert set(ARTIFACT_ROLE_PERMISSIONS) == {
            "artifact_reader",
            "artifact_writer",
            "artifact_admin",
        }
        assert role_for_scopes(["read"]) == "artifact_reader"
        assert role_for_scopes(["write"]) == "artifact_writer"
        assert role_for_scopes(["admin"]) == "artifact_admin"
        assert role_for_scopes(["something-else"]) is None
        assert role_for_scopes(None) is None

    def test_the_decision_type_is_explicit(self) -> None:
        decision = AccessDecision(allowed=False, reason="parce que")
        assert decision.to_audit_reason() == "parce que"
