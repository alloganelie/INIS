"""§41.4 — brancher une source REST authentifiée sur le vault d'INIS.

Le vault d'INIS sait déjà produire les en-têtes HTTP d'une source
(``CredentialResolver.auth_headers`` : ``api_key``, ``Bearer``, ``Basic``), mais
personne ne l'appelait : ``RESTConnector`` attend un objet d'authentification qui
**détient** le secret (``ApiKeyHandler(api_key=…)``), si bien qu'un appelant devait
avoir lu le secret lui-même. Ce module est le seul manquant : un adaptateur qui
applique le vault au moment de la requête.

Il n'introduit aucun mécanisme nouveau — ni coffre, ni format, ni en-tête
propriétaire — et ne modifie pas ``RESTConnector`` : :class:`VaultAuthHandler`
satisfait le protocole que le connecteur accepte déjà.

Deux propriétés à préserver, et testées :

* **aucun secret en configuration** — l'objet ne retient que la *référence*
  (``SourceCredential``) ; la valeur est lue dans le vault à chaque appel, donc
  une rotation est prise en compte sans redémarrage ;
* **aucune fuite** — ce module ne journalise rien, ne met rien dans ses
  exceptions et n'expose rien dans son ``repr`` : les messages d'erreur nomment
  l'entrée du vault, jamais son contenu (§41.4).
"""

from __future__ import annotations

from typing import Any

from app.connectors.api.rest_connector import RESTConnector
from app.core.errors import InfrastructureError
from app.security.vault.credential_vault import (
    CredentialNotFound,
    CredentialResolver,
    CredentialVault,
    SourceCredential,
    VaultError,
)
from app.tools.database.credentials import assert_credential_ref, default_vault

__all__ = [
    "VaultAuthHandler",
    "rest_connector_for_source",
]


class VaultAuthHandler:
    """Authentifie les appels du ``RESTConnector`` à partir du vault (§41.4).

    Le protocole attendu par le connecteur est ``apply(headers, params)`` : le
    handler enrichit les en-têtes, le connecteur fait l'appel HTTP.
    """

    def __init__(
        self,
        credential: SourceCredential,
        *,
        resolver: CredentialResolver | None = None,
        vault: CredentialVault | None = None,
    ) -> None:
        """Bind the handler to one §41.4 credential.

        Args:
            credential: le bloc ``[CONFIG]`` de la source (contient la **référence**,
                jamais la valeur).
            resolver: résolveur déjà construit ; sinon construit depuis *vault*.
            vault: vault à lire ; le vault du déploiement (§41.4) par défaut.
        """
        self._credential = credential
        self._resolver = resolver or CredentialResolver(vault or default_vault())

    @property
    def credential(self) -> SourceCredential:
        """Return the bound §41.4 credential (a reference, no secret)."""
        return self._credential

    def apply(
        self,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
    ) -> tuple[dict[str, str], dict[str, str]]:
        """Return ``(headers, params)`` with the vault-derived auth headers set.

        Raises:
            InfrastructureError: quand l'entrée du vault est absente ou illisible.
                Le message nomme **l'entrée** ; il ne contient jamais la valeur — y
                compris lorsque le connecteur réenveloppe l'erreur.
        """
        new_headers = dict(headers or {})
        new_params = dict(params or {})
        try:
            auth_headers = self._resolver.auth_headers(self._credential)
        except CredentialNotFound as exc:
            raise InfrastructureError(
                "identifiants absents du vault pour la source "
                f"'{self._credential.source_id}' (§41.4) : l'entrée "
                f"'{self._credential.credential_ref}' n'existe pas ; aucune "
                "requête n'est émise sans secret."
            ) from exc
        except VaultError as exc:
            raise InfrastructureError(
                "vault illisible pour la source "
                f"'{self._credential.source_id}' (§41.4) : {exc}"
            ) from exc
        new_headers.update(auth_headers)
        return new_headers, new_params

    def __repr__(self) -> str:
        """Return a log-safe representation: the reference, never the secret."""
        return (
            f"VaultAuthHandler(source_id={self._credential.source_id!r}, "
            f"auth_type={self._credential.auth_type!r}, "
            f"credential_ref={self._credential.credential_ref!r})"
        )


def rest_connector_for_source(
    credential: SourceCredential,
    *,
    base_url: str,
    vault: CredentialVault | None = None,
    resolver: CredentialResolver | None = None,
    client: Any | None = None,
    timeout_seconds: float = 10.0,
) -> RESTConnector:
    """Return a ``RESTConnector`` whose authentication comes from the vault.

    C'est le câblage que le plan réclamait : une source REST nommée par son
    ``credential_ref`` (§41.4) obtient ses en-têtes du vault au moment de l'appel,
    sans qu'aucun secret ne soit écrit dans la configuration du connecteur.

    Args:
        credential: le bloc ``[CONFIG]`` §41.4 de la source.
        base_url: racine du service REST appelé.
        vault: vault à lire ; le vault du déploiement par défaut.
        resolver: résolveur déjà construit (prioritaire sur *vault*).
        client: client ``httpx`` injecté (les tests s'en servent).
        timeout_seconds: délai par appel HTTP.

    Returns:
        Un ``RESTConnector`` authentifié par le vault.

    Raises:
        ValidationError: quand la ``credential_ref`` n'est pas un simple nom
            d'entrée (un DSN ou une valeur de secret y est refusé).
    """
    if credential.auth_type != "none":
        # Une référence qui porterait un DSN ou un secret est refusée par son nom.
        assert_credential_ref(credential.credential_ref)
    return RESTConnector(
        base_url=base_url,
        auth_handler=VaultAuthHandler(credential, resolver=resolver, vault=vault),
        client=client,
        timeout_seconds=timeout_seconds,
    )
