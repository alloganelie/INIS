"""§41.4 — une source authentifiée va réellement chercher son secret dans le vault.

La chaîne prouvée ici est celle que le plan L8.3 réclamait :

    RESTConnector → vault (§41.4) → en-tête d'authentification → endpoint REST → réponse

Rien n'est simulé aux deux extrémités : le vault est un vrai backend d'INIS
(``EnvVault`` lisant ``INIS_CRED_<REF>``, et ``FileVault`` chiffré sur disque), et
l'endpoint REST est un **vrai serveur HTTP local** qui **exige** le secret — il
répond 401 sans lui. Un ``httpx.MockTransport`` ne pourrait pas prouver cela : il
accepterait n'importe quel en-tête.

Ce que ce fichier établit, et ce qu'il n'établit pas :

* ✅ le secret est **lu dans le vault** au moment de l'appel (et une rotation est
  prise en compte sans reconstruire le connecteur) ;
* ✅ le secret est **réellement utilisé** pour l'authentification HTTP ;
* ✅ absent / référence invalide / vault illisible donnent un refus **explicite**,
  avant toute requête ;
* ✅ le secret n'apparaît ni dans les logs, ni dans les erreurs, ni dans le
  ``repr`` de l'adaptateur, ni dans le bloc ``[CONFIG]`` ;
* ✅ PostgreSQL n'est pas régressé : le DSN vient du vault et ne fuit pas ;
* ❌ non couvert : un coffre *externe* (HashiCorp Vault, AWS Secrets Manager) —
  le contrat §41.4 exige « un vault externe » et INIS l'implémente derrière le
  protocole ``CredentialVault`` par ``EnvVault``/``FileVault`` ; brancher un
  client HashiCorp réel est une décision de déploiement, pas un câblage de
  connecteur.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.connectors.api.auth.vault_auth_handler import (
    VaultAuthHandler,
    rest_connector_for_source,
)
from app.connectors.base import Query
from app.connectors.database.postgres_connector import PostgresConnector, masked_location
from app.core.errors import InfrastructureError, ValidationError
from app.security.vault.credential_vault import (
    EnvVault,
    FileVault,
    SourceCredential,
    VaultError,
)
from app.storage.database.engine import create_engine
from app.tools.database.credentials import dsn_from_vault

#: Valeur réellement stockée dans le vault pendant ce test — jamais dans le code
#: de production, seulement ici pour pouvoir affirmer qu'elle fuit ou non.
API_KEY_SECRET = "sk-live-5UP3R-53CR3T-POUR-LE-TEST"
BASIC_PASSWORD = "mot-de-passe-du-vault"
CREDENTIAL_REF = "rest_demo"
SOURCE_ID = "SRC_01M3Q0000000000000000000AA"
VAULT_KEY_ENV = "INIS_VAULT_KEY"


class _RequireApiKey(BaseHTTPRequestHandler):
    """Un vrai endpoint REST qui refuse tout appel sans le bon en-tête (§41.4)."""

    expected_header: tuple[str, str] = ("X-API-Key", API_KEY_SECRET)
    seen_headers: ClassVar[list[dict[str, str]]] = []
    seen_paths: ClassVar[list[str]] = []

    def do_GET(self) -> None:
        """Serve ``/search``, ``/items/<id>`` and ``/health``; 401 otherwise."""
        type(self).seen_paths.append(self.path)
        type(self).seen_headers.append(dict(self.headers.items()))
        if self.path.startswith("/health"):
            self._send(200, {"status": "ok"})
            return
        name, value = self.expected_header
        if self.headers.get(name) != value:
            self._send(401, {"error": "unauthorized"})
            return
        if self.path.startswith("/search"):
            self._send(
                200,
                {"items": [{"id": "1", "title": "Rapport", "url": f"http://{self.headers['Host']}/items/1"}]},
            )
            return
        if self.path.startswith("/items/"):
            self._send(200, {"id": self.path.rsplit("/", 1)[-1], "value": 42})
            return
        self._send(404, {"error": "not found"})

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        """Write one JSON response."""
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: Any) -> None:
        """Silence the default stderr logging (a test never logs)."""


@pytest.fixture
def rest_endpoint() -> Iterator[str]:
    """Start a real HTTP endpoint that requires the vault's API key."""
    _RequireApiKey.seen_headers = []
    _RequireApiKey.seen_paths = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _RequireApiKey)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
def environment_vault(monkeypatch: pytest.MonkeyPatch) -> EnvVault:
    """A real ``EnvVault`` holding the API key under ``CREDENTIAL_REF``."""
    monkeypatch.delenv(VAULT_KEY_ENV, raising=False)
    monkeypatch.setenv(
        f"INIS_CRED_{CREDENTIAL_REF.upper()}",
        json.dumps({"api_key": API_KEY_SECRET, "header": "X-API-Key"}),
    )
    return EnvVault()


@pytest.fixture
def file_vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FileVault:
    """A real encrypted ``FileVault`` holding the same secret."""
    vault = FileVault(tmp_path / "vault.json", master_key="cle-de-test-l83")
    vault.set(CREDENTIAL_REF, {"api_key": API_KEY_SECRET, "header": "X-API-Key"})
    monkeypatch.delenv("INIS_VAULT_FILE", raising=False)
    return vault


def _api_key_credential(reference: str = CREDENTIAL_REF) -> SourceCredential:
    """Return the §41.4 ``[CONFIG]`` block of an ``api_key`` REST source."""
    return SourceCredential(
        source_id=SOURCE_ID, auth_type="api_key", credential_ref=reference
    )


def asyncio_run(coroutine: Any) -> Any:
    """Run one coroutine from a synchronous test (the suite's usual pattern)."""
    return asyncio.run(coroutine)


async def _retrieve_first(base_url: str, vault: Any) -> Any:
    """Discover then retrieve through a vault-authenticated connector."""
    connector = rest_connector_for_source(
        _api_key_credential(), base_url=base_url, vault=vault
    )
    candidates = await connector.discover(Query(query_string="x"))
    return await connector.retrieve(candidates[0])


class TestTheSecretComesFromTheVault:
    """Le connecteur ne détient pas le secret : il le lit quand il en a besoin."""

    def test_the_vault_entry_becomes_the_auth_header(self, environment_vault: EnvVault) -> None:
        """La valeur de l'entrée du vault devient l'en-tête, et rien n'est stocké."""
        credential = _api_key_credential()
        handler = VaultAuthHandler(credential, vault=environment_vault)

        headers, params = handler.apply({"Accept": "application/json"})

        assert headers == {"Accept": "application/json", "X-API-Key": API_KEY_SECRET}
        assert params == {}
        # Le bloc [CONFIG] ne porte que la référence : aucun secret en configuration.
        assert credential.to_dict()["credential_ref"] == CREDENTIAL_REF
        assert API_KEY_SECRET not in json.dumps(credential.to_dict())

    def test_the_connector_uses_the_secret_against_a_real_endpoint(
        self, rest_endpoint: str, environment_vault: EnvVault
    ) -> None:
        """Un vrai endpoint exigeant la clé répond 200 : le secret a bien servi."""
        connector = rest_connector_for_source(
            _api_key_credential(), base_url=rest_endpoint, vault=environment_vault
        )

        candidates = asyncio_run(connector.discover(Query(query_string="rapport")))

        assert [candidate.source_id for candidate in candidates] == ["1"]
        sent = [request.get("X-API-Key") for request in _RequireApiKey.seen_headers]
        assert sent == [API_KEY_SECRET], "le connecteur doit envoyer la clé du vault"

    def test_the_same_chain_works_with_the_encrypted_file_vault(
        self, rest_endpoint: str, file_vault: FileVault
    ) -> None:
        """Le backend chiffré d'INIS emprunte exactement le même chemin."""
        raw = asyncio_run(
            _retrieve_first(rest_endpoint, file_vault)
        )

        assert json.loads(raw.data)["value"] == 42
        assert raw.metadata["data_stage"] == "raw"

    def test_a_rotated_secret_is_used_without_rebuilding_the_connector(
        self, rest_endpoint: str, environment_vault: EnvVault, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Rotation : la valeur est relue à l'appel, pas figée à la construction."""
        connector = rest_connector_for_source(
            _api_key_credential(), base_url=rest_endpoint, vault=environment_vault
        )
        assert asyncio_run(connector.discover(Query(query_string="x")))
        assert _RequireApiKey.seen_headers[-1]["X-API-Key"] == API_KEY_SECRET

        rotated = "sk-live-ROTATED-0002"
        monkeypatch.setenv(
            f"INIS_CRED_{CREDENTIAL_REF.upper()}",
            json.dumps({"api_key": rotated, "header": "X-API-Key"}),
        )
        _RequireApiKey.expected_header = ("X-API-Key", rotated)
        try:
            assert asyncio_run(connector.discover(Query(query_string="x")))
            assert _RequireApiKey.seen_headers[-1]["X-API-Key"] == rotated
        finally:
            _RequireApiKey.expected_header = ("X-API-Key", API_KEY_SECRET)


class TestAMissingOrUnreadableSecret:
    """Sans secret exploitable : refus explicite, et aucune requête émise."""

    def test_an_absent_entry_refuses_before_any_request(
        self, rest_endpoint: str, environment_vault: EnvVault
    ) -> None:
        """Une entrée absente est nommée, et le service n'est jamais appelé."""
        connector = rest_connector_for_source(
            _api_key_credential("entree_absente"),
            base_url=rest_endpoint,
            vault=environment_vault,
        )

        with pytest.raises(InfrastructureError) as caught:
            asyncio_run(connector.discover(Query(query_string="x")))

        assert "entree_absente" in str(caught.value)
        assert _RequireApiKey.seen_paths == [], "aucune requête ne doit partir"

    def test_a_reference_that_carries_a_dsn_is_refused(self) -> None:
        """Une référence qui porterait un DSN est refusée par son nom (§41.4)."""
        credential = SourceCredential(
            source_id=SOURCE_ID,
            auth_type="basic",
            credential_ref="postgresql://user:motdepasse@hote/base",
        )

        with pytest.raises(ValidationError) as caught:
            rest_connector_for_source(credential, base_url="https://exemple.test")

        message = str(caught.value)
        assert "credential_ref" in message
        assert "motdepasse" not in message, "le refus ne recopie pas la référence"

    def test_an_entry_that_is_not_json_is_reported(
        self,
        rest_endpoint: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Un bloc vault illisible est une erreur d'exploitation, pas un 401."""
        monkeypatch.setenv(f"INIS_CRED_{CREDENTIAL_REF.upper()}", "pas-du-json")
        connector = rest_connector_for_source(
            _api_key_credential(), base_url=rest_endpoint, vault=EnvVault()
        )

        with pytest.raises(InfrastructureError):
            asyncio_run(connector.discover(Query(query_string="x")))

    def test_a_corrupt_vault_file_fails_at_wiring_time(
        self, rest_endpoint: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Un coffre illisible échoue explicitement, au câblage, sans secret inventé."""
        vault_file = tmp_path / "corrompu.json"
        vault_file.write_text("{{{ pas du json", encoding="utf-8")
        monkeypatch.setenv("INIS_VAULT_FILE", str(vault_file))
        monkeypatch.setenv(VAULT_KEY_ENV, "cle-de-test-l83")

        with pytest.raises(VaultError):
            rest_connector_for_source(
                _api_key_credential(), base_url=rest_endpoint
            )


class TestNoSecretLeaks:
    """Le secret sert à signer la requête et n'apparaît nulle part ailleurs."""

    def test_the_secret_never_appears_in_logs(
        self,
        rest_endpoint: str,
        environment_vault: EnvVault,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Aucune ligne de log, à aucun niveau, ne contient le secret."""
        connector = rest_connector_for_source(
            _api_key_credential(), base_url=rest_endpoint, vault=environment_vault
        )

        with caplog.at_level(logging.DEBUG):
            asyncio_run(connector.discover(Query(query_string="x")))

        assert API_KEY_SECRET not in caplog.text
        assert connector._auth_handler is not None

    def test_a_rejected_secret_never_appears_in_the_error(
        self,
        rest_endpoint: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Un 401 remonte sans recopier la valeur refusée ni celle attendue."""
        wrong = "sk-live-MAUVAISE-CLE"
        monkeypatch.setenv(
            f"INIS_CRED_{CREDENTIAL_REF.upper()}",
            json.dumps({"api_key": wrong, "header": "X-API-Key"}),
        )
        connector = rest_connector_for_source(
            _api_key_credential(), base_url=rest_endpoint, vault=EnvVault()
        )

        with pytest.raises(InfrastructureError) as caught:
            asyncio_run(connector.discover(Query(query_string="x")))

        message = str(caught.value)
        assert "401" in message, "l'échec d'authentification doit être dit"
        assert wrong not in message
        assert API_KEY_SECRET not in message

    def test_the_handler_carries_only_the_reference(
        self, environment_vault: EnvVault
    ) -> None:
        """Le ``repr`` de l'adaptateur est journalisable tel quel."""
        handler = VaultAuthHandler(_api_key_credential(), vault=environment_vault)

        assert CREDENTIAL_REF in repr(handler)
        assert API_KEY_SECRET not in repr(handler)
        assert API_KEY_SECRET not in str(handler.credential.to_dict())

    def test_a_basic_credential_is_built_from_the_vault(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Le couple utilisateur/mot de passe du vault devient un en-tête Basic."""
        monkeypatch.setenv(
            f"INIS_CRED_{CREDENTIAL_REF.upper()}",
            json.dumps({"username": "inis-bot", "password": BASIC_PASSWORD}),
        )
        credential = SourceCredential(
            source_id=SOURCE_ID, auth_type="basic", credential_ref=CREDENTIAL_REF
        )

        headers, _ = VaultAuthHandler(credential, vault=EnvVault()).apply()

        expected = base64.b64encode(f"inis-bot:{BASIC_PASSWORD}".encode()).decode("ascii")
        assert headers == {"Authorization": f"Basic {expected}"}


class TestPostgresIsNotRegressed:
    """Le côté PostgreSQL était déjà câblé au vault : on le vérifie, on n'y touche pas."""

    def test_the_dsn_comes_from_the_vault_and_connects(
        self, db_url: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Le DSN est lu dans le vault, puis ouvre réellement une session."""
        monkeypatch.setenv("INIS_CRED_ANALYTICS_L83", json.dumps({"dsn": db_url}))

        dsn = dsn_from_vault("ANALYTICS_L83")

        assert dsn == db_url
        assert asyncio_run(_select_one(dsn)) == 1

    def test_the_password_never_appears_in_a_connector_error(
        self, db_url: str
    ) -> None:
        """Un mot de passe refusé par le serveur ne remonte pas dans l'erreur.

        Le connecteur n'enveloppe pas (encore) les erreurs de connexion du pilote :
        le type remonté est celui d'asyncpg. La propriété testée ici est celle du
        §41.4 — l'absence du secret —, pas le type de l'exception.
        """
        password = "mot-de-passe-refuse-par-le-serveur"
        broken = _with_password(db_url, password)
        connector = PostgresConnector(broken)

        with pytest.raises(Exception) as caught:
            asyncio_run(_discover(connector))

        assert password not in str(caught.value)
        assert password not in repr(caught.value)

    def test_a_candidate_never_carries_the_connection_secret(
        self, db_url: str
    ) -> None:
        """Un candidat est une sortie : le mot de passe n'y est jamais recopié (§41.4).

        Le DSN du conteneur de test porte le même mot de passe que son utilisateur
        et sa base ; la propriété vérifiée est donc la *forme* de la sortie — le
        champ mot de passe du DSN est masqué — et non la simple absence d'une
        sous-chaîne (voir ``test_the_masking_removes_distinctive_passwords``).
        """
        table = "l83_probe_candidates"
        asyncio_run(_create_probe_table(db_url, table))

        candidates = asyncio_run(PostgresConnector(db_url).discover(Query(query_string=table)))

        assert [candidate.metadata["table"] for candidate in candidates] == [table]
        location = candidates[0].location
        assert location == make_url(db_url).render_as_string(hide_password=True)
        assert "***" in location
        assert f":{_password_of(db_url)}@" not in location

    def test_the_masking_removes_distinctive_passwords(self) -> None:
        """Sur un mot de passe distinctif, aucune sous-chaîne ne subsiste."""
        masked = masked_location(
            "postgresql+asyncpg://inis:mot-de-passe-distinctif-42@hote.internal:5432/base"
        )

        assert "mot-de-passe-distinctif-42" not in masked
        assert "inis:" in masked and "hote.internal:5432" in masked

    def test_a_dsn_cannot_be_used_as_a_credential_ref(self) -> None:
        """La règle §41.4 vaut aussi pour PostgreSQL : la requête nomme, jamais le DSN."""
        with pytest.raises(ValidationError) as caught:
            dsn_from_vault("postgresql://user:motdepasse@hote/base")

        assert "motdepasse" not in str(caught.value)


async def _select_one(dsn: str) -> int:
    """Open one real session on *dsn* and return ``SELECT 1``."""
    engine = create_engine(dsn)
    try:
        async with engine.connect() as connection:
            return int((await connection.execute(text("SELECT 1"))).scalar_one())
    finally:
        await engine.dispose()


async def _discover(connector: PostgresConnector) -> Any:
    """Trigger a real connection attempt through the connector."""
    return await connector.discover(Query(query_string="quelconque"))


def _with_password(dsn: str, password: str) -> str:
    """Return *dsn* with its password replaced (a wrong-password probe)."""
    scheme, rest = dsn.split("://", 1)
    credentials, tail = rest.split("@", 1)
    user = credentials.split(":", 1)[0]
    return f"{scheme}://{user}:{password}@{tail}"


def _password_of(dsn: str) -> str:
    """Return the password embedded in *dsn* (the secret under test)."""
    credentials = dsn.split("://", 1)[1].split("@", 1)[0]
    _, _, password = credentials.partition(":")
    assert password, f"le DSN de test doit porter un mot de passe : {dsn!r}"
    return password


async def _create_probe_table(dsn: str, table: str) -> None:
    """Create the throwaway table the candidate test looks for."""
    engine = create_engine(dsn)
    try:
        async with engine.begin() as connection:
            await connection.execute(text(f"CREATE TABLE IF NOT EXISTS {table} (id integer)"))
    finally:
        await engine.dispose()
