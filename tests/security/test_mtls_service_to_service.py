"""§19.2 — intégration service-à-service : handshake TLS réel + dépendance d'authn.

Ce fichier prouve deux choses distinctes, et dit exactement où s'arrête chacune :

1. **Handshake réel** — un client présente un vrai certificat à un serveur TLS
   configuré en ``CERT_REQUIRED`` ; OpenSSL vérifie la chaîne et refuse un client
   sans certificat. C'est « mTLS » au sens du transport, et c'est mesuré ici, pas
   simulé.
2. **Dépendance d'authn** — la chaîne issue de ce handshake est remise à
   ``require_agent_certificate`` par l'extension **ASGI standard**
   ``extensions.tls.client_cert_chain``, et la dépendance décide (200 / 401 / 503).

⚠️ Ce qui n'est **pas** fait, et pourquoi : aucune route d'``app/api/`` n'est
modifiée. Le plan demande d'*exposer* la dépendance ; la spec ne définit aucun point
d'entrée réseau inter-agents (le canal agent-à-agent d'INIS est AMQP, §5), et
**uvicorn 0.27.0 n'expose pas** l'extension TLS — mesuré : ``client_cert`` est absent
de tout le paquet installé. Brancher une route exigerait soit un autre serveur, soit
un en-tête non signé, c'est-à-dire une invention. Le point reste donc ouvert et il est
écrit comme tel dans le plan de conformité.
"""

from __future__ import annotations

import asyncio
import json
import ssl
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import ExtendedKeyUsageOID
from fastapi import Depends, FastAPI, Request

from app.security.certificates.dependency import (
    AgentAuthentication,
    require_agent_certificate,
    set_agent_certificate_validator,
)
from app.security.certificates.validator import MTLSCertValidator
from tests.security import pki

#: Attente maximale pour savoir si le serveur a accepté un certificat client.
#: En cas de refus (aucun certificat), l'attente est payée en entier — d'où une
#: valeur courte : le serveur ferme la connexion immédiatement.
REFUSAL_TIMEOUT_SECONDS = 2.0


@dataclass(frozen=True)
class TlsMaterial:
    """Chemins et PEM d'une PKI jetable écrite sur disque (TLS exige des fichiers)."""

    ca_cert: Path
    ca_pem: str
    server_cert: Path
    server_key: Path
    client_cert: Path
    client_key: Path
    client_pem: str


@pytest.fixture
def material(tmp_path: Path) -> TlsMaterial:
    """CA + certificat serveur (SAN ``localhost``) + certificat client agent."""
    authority = pki.make_ca("INIS-Test-CA")
    server = pki.make_client(
        authority,
        "localhost",
        eku=(ExtendedKeyUsageOID.SERVER_AUTH,),
        san=("localhost", "IP:127.0.0.1"),
    )
    client = pki.make_client(authority, "AGENT_AGT_TLS")
    ca_cert = pki.write_pem(tmp_path / "ca.crt", authority.pem)
    return TlsMaterial(
        ca_cert=ca_cert,
        ca_pem=authority.pem,
        server_cert=pki.write_pem(tmp_path / "server.crt", server.pem),
        server_key=pki.write_pem(tmp_path / "server.key", server.key_pem),
        client_cert=pki.write_pem(tmp_path / "client.crt", client.pem),
        client_key=pki.write_pem(tmp_path / "client.key", client.key_pem),
        client_pem=client.pem,
    )


def _pem_from_der(der: bytes) -> str:
    """Convert the DER certificate a TLS socket exposes into PEM text."""
    return (
        x509.load_der_x509_certificate(der)
        .public_bytes(serialization.Encoding.PEM)
        .decode("ascii")
    )


async def _client_certificate_seen(
    material: TlsMaterial, *, present_certificate: bool = True
) -> str | None:
    """Run one real TLS handshake; return the client certificate the server *accepted*.

    Le serveur est en ``CERT_REQUIRED`` contre la CA de test : le certificat n'arrive
    côté serveur que si OpenSSL l'a accepté. Le client vérifie aussi l'identité du
    serveur (SAN ``localhost``) : les deux sens sont éprouvés.

    Returns:
        Le PEM du certificat client tel que le serveur l'a lu, ou ``None`` si le
        serveur n'a **rien** accepté.

    Note:
        En TLS 1.3, le certificat client circule *après* le handshake initial : un
        client sans certificat peut donc voir sa connexion s'établir puis se faire
        fermer par le serveur. C'est pourquoi cette fonction teste l'issue **côté
        serveur** (« un certificat a-t-il été accepté ? ») plutôt que de supposer que
        ``open_connection`` lèvera.
    """
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(material.server_cert, material.server_key)
    server_context.load_verify_locations(material.ca_cert)
    server_context.verify_mode = ssl.CERT_REQUIRED
    seen: list[str] = []
    ready = asyncio.Event()

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Record the peer certificate, then close — the handshake is the subject."""
        ssl_object = writer.get_extra_info("ssl_object")
        seen.append(_pem_from_der(ssl_object.getpeercert(binary_form=True)))
        ready.set()
        writer.close()

    server = await asyncio.start_server(handler, "127.0.0.1", 0, ssl=server_context)
    port = server.sockets[0].getsockname()[1]
    client_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    client_context.load_verify_locations(material.ca_cert)
    if present_certificate:
        client_context.load_cert_chain(material.client_cert, material.client_key)
    try:
        _, writer = await asyncio.open_connection(
            "127.0.0.1", port, ssl=client_context, server_hostname="localhost"
        )
        writer.close()
        try:
            await asyncio.wait_for(ready.wait(), timeout=REFUSAL_TIMEOUT_SECONDS)
        except (TimeoutError, ssl.SSLError):
            return None
    except ssl.SSLError:
        return None
    finally:
        server.close()
        await server.wait_closed()
    return seen[0] if seen else None


class TestTheTlsHandshakeIsReal:
    """Le transport fait son travail : la chaîne arrive réellement côté serveur."""

    def test_a_presented_client_certificate_reaches_the_server(
        self, material: TlsMaterial
    ) -> None:
        """Le certificat lu par le serveur est celui présenté par le client."""
        assert (
            asyncio.run(_client_certificate_seen(material)) == material.client_pem
        )

    def test_the_chain_from_the_handshake_is_accepted_by_our_validator(
        self, material: TlsMaterial
    ) -> None:
        """La chaîne issue du handshake réel passe notre propre vérification.

        C'est le raccord entre les deux moitiés : OpenSSL a accepté le client, et
        notre validateur, à partir de ce que le transport a transmis, en tire la même
        identité. Aucun ``CN`` n'est écrit à la main dans ce test.
        """
        received = asyncio.run(_client_certificate_seen(material))
        assert received is not None, "le handshake aurait dû livrer un certificat"
        validator = MTLSCertValidator(trusted_cas=[material.ca_pem])
        assert validator.validate([received]).agent_id == "AGENT_AGT_TLS"

    def test_a_client_without_certificate_is_not_accepted(
        self, material: TlsMaterial
    ) -> None:
        """Contre-preuve : ``CERT_REQUIRED`` n'est pas décoratif."""
        assert (
            asyncio.run(
                _client_certificate_seen(material, present_certificate=False)
            )
            is None
        )


def _agent_route_app() -> FastAPI:
    """A minimal app mounting the dependency the way a real route would."""
    app = FastAPI()

    @app.get("/agent")
    def whoami(
        request: Request,
        identity: Annotated[AgentAuthentication, Depends(require_agent_certificate)],
    ) -> dict[str, Any]:
        """Return the authenticated identity and what it put on the request state."""
        return {
            "identity": identity.as_dict(),
            "state_agent_id": getattr(request.state, "agent_id", None),
        }

    return app


def _call_agent_route(
    app: FastAPI, *, chain: Sequence[str] | None
) -> tuple[int, dict[str, Any]]:
    """Drive the ASGI app with (or without) the standard TLS extension."""
    path = "/agent"
    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "https",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "client": ("127.0.0.1", 40000),
        "server": ("testserver", 443),
    }
    if chain is not None:
        scope["extensions"] = {"tls": {"client_cert_chain": list(chain)}}
    messages: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        """A bodyless request: the identity decision needs no payload."""
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        """Collect the ASGI response without an HTTP client in the way."""
        messages.append(message)

    asyncio.run(app(scope, receive, send))
    status_line = next(m for m in messages if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return int(status_line["status"]), json.loads(body or b"{}")


@pytest.fixture
def configured_validator(material: TlsMaterial) -> Iterator[None]:
    """Trust exactly the test CA for the duration of one test, then forget it."""
    set_agent_certificate_validator(
        MTLSCertValidator(trusted_cas=[material.ca_pem])
    )
    yield
    set_agent_certificate_validator(None)


class TestTheAuthenticationDependency:
    """La dépendance décide à partir d'une chaîne réellement présentée."""

    def test_the_agent_is_authenticated_from_the_handshake_chain(
        self, material: TlsMaterial, configured_validator: None
    ) -> None:
        """De bout en bout : handshake réel → dépendance → identité d'agent.

        Le certificat utilisé ici n'est pas fabriqué pour l'occasion : il vient du
        handshake TLS de :meth:`TestTheTlsHandshakeIsReal`. Si le transport ou le
        validateur cessait de fonctionner, ce test tomberait.
        """
        chain = asyncio.run(_client_certificate_seen(material))
        assert chain is not None
        status_code, payload = _call_agent_route(_agent_route_app(), chain=[chain])
        assert status_code == 200
        assert payload["identity"]["agent_id"] == "AGENT_AGT_TLS"
        assert payload["identity"]["auth_method"] == "mtls"
        assert payload["state_agent_id"] == "AGENT_AGT_TLS"

    def test_a_rejected_certificate_yields_401(
        self, material: TlsMaterial, configured_validator: None
    ) -> None:
        """Un certificat hors chaîne de confiance est refusé, avec son motif."""
        intruder = pki.make_client(pki.make_ca("Intruder-CA"), "AGENT_AGT_INTRUDER")
        status_code, payload = _call_agent_route(
            _agent_route_app(), chain=[intruder.pem]
        )
        assert status_code == 401
        assert "certificate_chain_untrusted" in payload["detail"]

    def test_an_absent_certificate_yields_401(self, configured_validator: None) -> None:
        """Sans extension TLS, aucun certificat n'a été présenté : refus."""
        status_code, payload = _call_agent_route(_agent_route_app(), chain=None)
        assert status_code == 401
        assert payload["detail"] == "Client certificate required"

    def test_an_empty_extension_is_not_a_certificate(
        self, configured_validator: None
    ) -> None:
        """Une liste vide n'est pas une preuve (contre-preuve du test précédent)."""
        status_code, _ = _call_agent_route(_agent_route_app(), chain=[])
        assert status_code == 401

    def test_unconfigured_mtls_yields_503(self, material: TlsMaterial) -> None:
        """Fail closed : mTLS non configuré ⇒ 503, jamais un passage silencieux."""
        set_agent_certificate_validator(None)
        chain = asyncio.run(_client_certificate_seen(material))
        assert chain is not None
        status_code, payload = _call_agent_route(_agent_route_app(), chain=[chain])
        assert status_code == 503
        assert payload["detail"] == "mTLS authentication is not configured"
