"""Real X.509 client-certificate validation for §19.2 (inter-agent mTLS).

Le contrat est mince — « mTLS pour inter-agents » — donc ce module ne fabrique
aucune exigence : il établit ce que « mTLS » signifie, avec des certificats
réels, et refuse ce qu'il ne peut pas établir. Voir
:mod:`app.security.certificates` pour la liste exacte des cinq vérifications et
pour ce que ce module ne fait **pas**.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from cryptography import x509
from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes
from cryptography.x509.oid import ExtensionOID, NameOID

from app.core.errors import InfrastructureError, ValidationError

#: Espace de nommage des identités d'agent, hérité de l'implémentation d'origine
#: (`app/security/authn/mtls_validator.py`) : le `CN` du certificat client est
#: l'`agent_id` et doit être nommé. La spec ne définit pas ce format ; on réutilise
#: la convention déjà acceptée par les tests plutôt que d'en introduire une autre.
AGENT_IDENTITY_NAMESPACE = "AGENT_"

#: Motifs de refus — codes stables, jamais construits à partir de l'entrée.
REASON_MALFORMED = "certificate_missing_or_malformed"
REASON_EXPIRED = "certificate_expired"
REASON_NOT_YET_VALID = "certificate_not_yet_valid"
REASON_UNTRUSTED = "certificate_chain_untrusted"
REASON_REVOKED = "certificate_revoked"
REASON_IDENTITY = "certificate_identity_unusable"
REASON_USAGE = "certificate_usage_not_client_auth"
REASON_ISSUER_NOT_CA = "certificate_issuer_not_a_ca"
REASON_NO_TRUST_ANCHOR = "no_trust_anchor_configured"

#: Profondeur maximale de remontée de chaîne : borne le travail sur une entrée
#: hostile (une chaîne circulaire de 10 000 certificats ne doit pas boucler).
MAX_CHAIN_DEPTH = 8


class CertificateRejected(ValidationError):
    """Un certificat client a été refusé (§19.2).

    Le motif est un **code stable** (``REASON_*``) : le message ne contient ni
    le certificat, ni son sujet, ni son numéro de série. Un message d'erreur
    n'est pas un canal d'exfiltration.
    """

    def __init__(self, reason: str) -> None:
        """Record the stable rejection reason and build the fixed message."""
        self.reason = reason
        super().__init__(f"mTLS certificate rejected: {reason}")


@dataclass(frozen=True)
class AgentCertificate:
    """Le résultat d'une validation réussie : de quoi authentifier un agent."""

    agent_id: str
    subject: str
    serial_number: int
    not_valid_before: datetime
    not_valid_after: datetime
    chain_length: int

    def as_dict(self) -> dict[str, Any]:
        """Return the audit-friendly projection (no key material)."""
        return {
            "agent_id": self.agent_id,
            "subject": self.subject,
            "serial_number": self.serial_number,
            "not_valid_before": self.not_valid_before.isoformat(),
            "not_valid_after": self.not_valid_after.isoformat(),
            "chain_length": self.chain_length,
        }


#: Un certificat peut être fourni brut (objet) ou en PEM (chaîne ou octets).
CertificateInput = str | bytes | x509.Certificate
#: L'entrée de la chaîne : le feuillet d'abord, puis ses émetteurs (convention
#: de l'extension ASGI ``tls.client_cert_chain``).
ChainInput = CertificateInput | Sequence[CertificateInput]


def _load_certificate(material: CertificateInput) -> x509.Certificate:
    """Parse one certificate, accepting an already-parsed object."""
    if isinstance(material, x509.Certificate):
        return material
    raw = material.encode("utf-8") if isinstance(material, str) else material
    if not raw:
        raise CertificateRejected(REASON_MALFORMED)
    try:
        return x509.load_pem_x509_certificate(raw)
    except Exception:  # noqa: BLE001 - toute erreur de parsing est un refus
        raise CertificateRejected(REASON_MALFORMED) from None


def _load_chain(material: ChainInput) -> list[x509.Certificate]:
    """Return ``[leaf, *issuers]`` from PEM bundle, PEM list, or objects."""
    if isinstance(material, (str, bytes, x509.Certificate)):
        if isinstance(material, (str, bytes)):
            raw = material.encode("utf-8") if isinstance(material, str) else material
            try:
                bundle = x509.load_pem_x509_certificates(raw)
            except Exception:  # noqa: BLE001
                bundle = []
            if len(bundle) > 1:
                return list(bundle)
        return [_load_certificate(material)]
    chain = list(material)
    if not chain:
        raise CertificateRejected(REASON_MALFORMED)
    return [_load_certificate(item) for item in chain]


class MTLSCertValidator:
    """Vérifie un certificat client X.509 et en extrait l'identité d'agent.

    La configuration (ancres de confiance, révocation) vient du déploiement :
    la spec ne définit aucune PKI, donc l'objet ne devine rien — tout ce qu'il
    ne peut pas établir est refusé.
    """

    def __init__(
        self,
        trusted_cas: ChainInput | None = None,
        *,
        revoked_serials: Collection[int] = (),
        crl: Any | None = None,
        clock: Callable[[], datetime] | None = None,
        require_agent_namespace: bool = True,
    ) -> None:
        """Configure the validator.

        Args:
            trusted_cas: certificat(s) d'ancre de confiance (PEM, objet, liste).
                Vide ⇒ **tout est refusé** (échec fermé), jamais accepté.
            revoked_serials: numéros de série explicitement révoqués.
            crl: une ou plusieurs CRL (PEM/DER/objet) fournies par le déploiement.
            clock: horloge injectable — les tests génèrent de vrais certificats
                expirés plutôt que de mentir sur l'heure.
            require_agent_namespace: exige le préfixe ``AGENT_`` sur le ``CN``.

        Raises:
            InfrastructureError: ancre ou CRL illisible — une faute
                d'exploitation, distincte d'un certificat client refusé.
        """
        self._trust_anchors = _load_anchors(trusted_cas)
        self._revoked_serials = frozenset(int(serial) for serial in revoked_serials)
        self._crls = _load_crls(crl)
        self._clock = clock or (lambda: datetime.now(UTC))
        self._require_namespace = require_agent_namespace

    @property
    def trust_anchor_count(self) -> int:
        """Return how many trust anchors the deployment configured."""
        return len(self._trust_anchors)

    def validate(self, client_certificate: ChainInput) -> AgentCertificate:
        """Verify *client_certificate* and return the authenticated agent.

        Args:
            client_certificate: le feuillet, ou ``[feuillet, *émetteurs]`` — la
                convention de l'extension ASGI ``tls.client_cert_chain``.

        Returns:
            L'identité vérifiée, jamais un objet partiel.

        Raises:
            CertificateRejected: motif stable, sans contenu de certificat.
        """
        chain = _load_chain(client_certificate)
        leaf, intermediates = chain[0], chain[1:]
        moment = self._clock()

        self._assert_validity(leaf, moment)
        self._assert_client_usage(leaf)
        self._assert_not_revoked(leaf)
        depth = self._assert_trusted(leaf, intermediates, moment)
        agent_id = self._identity(leaf)
        return AgentCertificate(
            agent_id=agent_id,
            subject=leaf.subject.rfc4514_string(),
            serial_number=leaf.serial_number,
            not_valid_before=leaf.not_valid_before_utc,
            not_valid_after=leaf.not_valid_after_utc,
            chain_length=depth,
        )

    # -- vérifications ---------------------------------------------------

    @staticmethod
    def _assert_validity(certificate: x509.Certificate, moment: datetime) -> None:
        """Refuse un certificat hors de sa fenêtre de validité."""
        if moment < certificate.not_valid_before_utc:
            raise CertificateRejected(REASON_NOT_YET_VALID)
        if moment > certificate.not_valid_after_utc:
            raise CertificateRejected(REASON_EXPIRED)

    @staticmethod
    def _assert_client_usage(certificate: x509.Certificate) -> None:
        """Refuse un certificat qui se déclare inutilisable pour un client.

        Un certificat **sans** extension ``extendedKeyUsage`` n'exprime aucune
        restriction : il passe. Un certificat qui en déclare une doit autoriser
        ``clientAuth`` (ou ``anyExtendedKeyUsage``), sinon un certificat serveur
        servirait d'identité client.
        """
        try:
            usage = certificate.extensions.get_extension_for_oid(
                ExtensionOID.EXTENDED_KEY_USAGE
            ).value
        except x509.ExtensionNotFound:
            return
        allowed = {
            x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH,
            x509.oid.ExtendedKeyUsageOID.ANY_EXTENDED_KEY_USAGE,
        }
        if not any(oid in allowed for oid in usage):
            raise CertificateRejected(REASON_USAGE)

    def _assert_not_revoked(self, certificate: x509.Certificate) -> None:
        """Refuse un certificat révoqué (liste explicite ou CRL fournie)."""
        serial = certificate.serial_number
        if serial in self._revoked_serials:
            raise CertificateRejected(REASON_REVOKED)
        for crl in self._crls:
            if crl.get_revoked_certificate_by_serial_number(serial) is not None:
                raise CertificateRejected(REASON_REVOKED)

    def _assert_trusted(
        self,
        leaf: x509.Certificate,
        intermediates: Sequence[x509.Certificate],
        moment: datetime,
    ) -> int:
        """Remonte les signatures jusqu'à une ancre et retourne la profondeur.

        Chaque saut est une **vérification de signature** (et de la qualité de CA
        de l'émetteur), pas une comparaison de noms. La validité temporelle de
        chaque élément traversé est vérifiée : une chaîne dont l'intermédiaire a
        expiré est refusée.
        """
        if not self._trust_anchors:
            raise CertificateRejected(REASON_NO_TRUST_ANCHOR)
        current = leaf
        walked = [leaf.fingerprint(hashes.SHA256())]
        for _ in range(MAX_CHAIN_DEPTH):
            for anchor in self._trust_anchors:
                if self._issued_by(current, anchor):
                    self._assert_certificate_authority(anchor)
                    return len(walked) + 1
            successor = None
            for candidate in intermediates:
                fingerprint = candidate.fingerprint(hashes.SHA256())
                if fingerprint in walked:
                    continue
                if self._issued_by(current, candidate):
                    successor = candidate
                    walked.append(fingerprint)
                    break
            if successor is None:
                raise CertificateRejected(REASON_UNTRUSTED)
            self._assert_validity(successor, moment)
            self._assert_certificate_authority(successor)
            current = successor
        raise CertificateRejected(REASON_UNTRUSTED)

    @staticmethod
    def _assert_certificate_authority(certificate: x509.Certificate) -> None:
        """Refuse un émetteur qui n'est pas un CA.

        ⚠️ Mesuré, pas supposé : ``verify_directly_issued_by`` vérifie le nom de
        l'émetteur et la **signature**, mais *pas* que l'émetteur a le droit de
        signer. Un certificat ``basicConstraints CA:false`` peut donc signer un
        feuillet et être accepté si l'on ne vérifie rien de plus — trouvé par une
        sonde pendant l'écriture de ce module. La contrainte est donc imposée ici,
        explicitement, sur **chaque** émetteur traversé (intermédiaires *et*
        ancres) : un certificat sans ``basicConstraints`` ou avec ``CA:false``
        n'est pas une autorité.
        """
        try:
            constraints = certificate.extensions.get_extension_for_oid(
                ExtensionOID.BASIC_CONSTRAINTS
            ).value
        except x509.ExtensionNotFound:
            raise CertificateRejected(REASON_ISSUER_NOT_CA) from None
        if not constraints.ca:
            raise CertificateRejected(REASON_ISSUER_NOT_CA)

    @staticmethod
    def _issued_by(child: x509.Certificate, issuer: x509.Certificate) -> bool:
        """Return whether *issuer* really signed *child*.

        Vérifie le nom de l'émetteur puis la **signature cryptographique**
        (``verify_directly_issued_by``). La qualité de CA de l'émetteur n'est pas
        de son ressort : elle est imposée par
        :meth:`_assert_certificate_authority`. Tout échec — mauvaise signature,
        algorithme non supporté — vaut « non approuvé ».
        """
        if child.issuer != issuer.subject:
            return False
        try:
            child.verify_directly_issued_by(issuer)
        except (InvalidSignature, UnsupportedAlgorithm, ValueError, TypeError):
            return False
        return True

    def _identity(self, certificate: x509.Certificate) -> str:
        """Extrait l'``agent_id`` du ``CN``, ou refuse."""
        common_names = certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        if len(common_names) != 1:
            raise CertificateRejected(REASON_IDENTITY)
        value = common_names[0].value
        if not isinstance(value, str) or not value.strip():
            raise CertificateRejected(REASON_IDENTITY)
        if self._require_namespace and not value.startswith(AGENT_IDENTITY_NAMESPACE):
            raise CertificateRejected(REASON_IDENTITY)
        return value


def _as_sequence(material: Any) -> list[Any]:
    """Return *material* as a list, without splitting a PEM string into chars."""
    if isinstance(material, Sequence) and not isinstance(material, (str, bytes)):
        return list(material)
    return [material]


def _load_anchors(material: ChainInput | None) -> list[x509.Certificate]:
    """Return the configured trust anchors, or an empty list.

    Raises:
        InfrastructureError: un matériau fourni n'est pas un certificat — faute
            de configuration, distincte d'un certificat client refusé.
    """
    if material is None:
        return []
    anchors: list[x509.Certificate] = []
    for candidate in _as_sequence(material):
        if isinstance(candidate, x509.Certificate):
            anchors.append(candidate)
            continue
        raw = candidate.encode("utf-8") if isinstance(candidate, str) else candidate
        try:
            anchors.extend(x509.load_pem_x509_certificates(raw))
        except Exception as exc:
            raise InfrastructureError(
                "trusted_cas must hold PEM X.509 certificates"
            ) from exc
    return anchors


def _load_crls(material: Any | None) -> list[x509.CertificateRevocationList]:
    """Return the configured CRLs (PEM, DER or objects).

    Raises:
        InfrastructureError: une CRL déclarée n'est pas lisible.
    """
    if material is None:
        return []
    crls: list[x509.CertificateRevocationList] = []
    for candidate in _as_sequence(material):
        if isinstance(candidate, x509.CertificateRevocationList):
            crls.append(candidate)
            continue
        raw = candidate.encode("utf-8") if isinstance(candidate, str) else candidate
        try:
            if raw.lstrip().startswith(b"-----"):
                crls.append(x509.load_pem_x509_crl(raw))
            else:
                crls.append(x509.load_der_x509_crl(raw))
        except Exception as exc:
            raise InfrastructureError(
                "crl must hold PEM or DER revocation list material"
            ) from exc
    return crls

