"""Service-to-service authentication binding for the mTLS validator (§19.2).

Le plan L8 demande d'« exposer » le validateur « comme dépendance d'authn
service-à-service ». Ce fichier est cette exposition : **le seul** du paquet à
parler au monde web, pour que :mod:`app.security.certificates.validator` reste du
pur X.509, utilisable ailleurs (le canal inter-agents d'INIS est AMQP, pas HTTP).

D'où vient le certificat ? De l'extension **ASGI standard**
``extensions.tls.client_cert_chain`` — le serveur TLS termine le handshake,
vérifie le certificat client, puis transmet la chaîne au cadre applicatif. Nous
ne fabriquons **aucun en-tête** (``X-Client-Certificate`` et compagnie) :
inventer un en-tête serait inventer un contrat de terminaison TLS que la spec ne
définit pas, et un en-tête non signé n'est pas une identité.

⚠️ Limite mesurée de la pile actuelle : **uvicorn 0.27.0 n'expose pas** cette
extension (``client_cert`` est absent de tout le paquet installé) — aucune route
d'INIS ne peut donc recevoir le certificat aujourd'hui. Le validateur et cette
dépendance sont utilisables dès qu'un serveur conforme ASGI présente la chaîne ;
aucune route de ``app/api/`` n'est détournée pour simuler l'intégration.

L'échec est **fermé** : dépendance non configurée ⇒ 503, certificat absent ou
refusé ⇒ 401. Jamais de passage par défaut.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from fastapi import HTTPException, status
from fastapi import Request as FastAPIRequest

from app.core.errors import ValidationError
from app.security.certificates.validator import CertificateRejected, MTLSCertValidator

#: Motif renvoyé quand aucun validateur n'a été configuré (faute d'exploitation).
REASON_NOT_CONFIGURED: Final[str] = "agent_certificate_validator_not_configured"

#: Méthode d'authentification déclarée dans l'enveloppe §5.1.
MTLS_AUTH_METHOD: Final[str] = "mtls"


class AgentCertificateMissing(ValidationError):
    """Aucun certificat client n'a été présenté à la terminaison TLS."""


@dataclass(frozen=True)
class AgentAuthentication:
    """Le résultat d'une authentification service-à-service réussie."""

    agent_id: str
    auth_method: str = MTLS_AUTH_METHOD
    serial_number: int | None = None
    subject: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return the envelope-compatible projection (§5.1 ``security``)."""
        return {
            "auth_method": self.auth_method,
            "agent_id": self.agent_id,
            "serial_number": self.serial_number,
        }


_VALIDATOR: MTLSCertValidator | None = None


def set_agent_certificate_validator(validator: MTLSCertValidator | None) -> None:
    """Configure the validator used by :func:`require_agent_certificate`.

    Même convention de surcharge que ``set_security_validator``
    (``app/api/middleware/auth_middleware.py``) : le déploiement — ou un test —
    choisit ses ancres de confiance sans qu'aucun nom de variable d'environnement
    nouveau ne soit inventé.

    Args:
        validator: le validateur à utiliser, ou ``None`` pour revenir à l'état
            « non configuré », donc à un refus systématique.
    """
    global _VALIDATOR
    _VALIDATOR = validator


def get_agent_certificate_validator() -> MTLSCertValidator | None:
    """Return the configured validator, or ``None`` when mTLS is not set up."""
    return _VALIDATOR


def client_certificate_chain(source: Any) -> list[str] | None:
    """Return the client chain the ASGI server verified, or ``None``.

    Args:
        source: une ``Request`` Starlette/FastAPI, ou directement le scope ASGI.

    Returns:
        ``[feuillet, *émetteurs]`` en PEM, ou ``None`` si le serveur n'a rien
        transmis. Une liste vide vaut « rien » : un certificat est une preuve,
        une liste vide n'en est pas une.
    """
    scope = getattr(source, "scope", source)
    if not isinstance(scope, dict):
        return None
    extensions = scope.get("extensions") or {}
    tls = extensions.get("tls") or {}
    chain = tls.get("client_cert_chain")
    if not chain:
        return None
    return [item.decode("utf-8") if isinstance(item, bytes) else str(item) for item in chain]


def authenticate_agent(source: Any) -> AgentAuthentication:
    """Authenticate a service-to-service caller from its TLS client certificate.

    Args:
        source: une ``Request`` ou le scope ASGI portant l'extension TLS.

    Returns:
        L'identité vérifiée de l'agent émetteur.

    Raises:
        CertificateRejected: la dépendance n'est pas configurée, ou la chaîne est
            refusée (motif stable dans ``reason``).
        AgentCertificateMissing: aucun certificat n'a été présenté.
    """
    validator = get_agent_certificate_validator()
    if validator is None:
        raise CertificateRejected(REASON_NOT_CONFIGURED)
    chain = client_certificate_chain(source)
    if chain is None:
        raise AgentCertificateMissing("no client certificate presented")
    certificate = validator.validate(chain)
    return AgentAuthentication(
        agent_id=certificate.agent_id,
        serial_number=certificate.serial_number,
        subject=certificate.subject,
    )


def require_agent_certificate(request: FastAPIRequest) -> AgentAuthentication:
    """FastAPI dependency: authenticate the caller by its client certificate.

    À déclarer sur une route inter-agents :
    ``Depends(require_agent_certificate)``. L'identité est aussi posée sur
    ``request.state.agent_id`` pour les couches suivantes (même convention que le
    middleware §19).

    Raises:
        HTTPException: 503 si mTLS n'est pas configuré — faute d'exploitation,
            jamais un passage silencieux ; 401 si aucun certificat n'est présenté
            ou s'il est refusé.
    """
    try:
        authentication = authenticate_agent(request)
    except CertificateRejected as exc:
        if exc.reason == REASON_NOT_CONFIGURED:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="mTLS authentication is not configured",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"mTLS certificate rejected ({exc.reason})",
        ) from exc
    except AgentCertificateMissing as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Client certificate required",
        ) from exc
    request.state.agent_id = authentication.agent_id
    request.state.auth_method = authentication.auth_method
    return authentication
