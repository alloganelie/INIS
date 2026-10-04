"""§19.2 — le certificat client est réellement **vérifié**, pas seulement lu.

Ce fichier est la preuve citée par le plan de conformité pour l'item L8 « validateur
mTLS ». Chaque cas utilise de **vrais** certificats signés (``tests/security/pki.py``,
``cryptography``) : rien n'est simulé par un dictionnaire, sinon le test ne pourrait
pas distinguer « la signature est valide » de « le champ ``CN`` contient le bon mot ».

La question à laquelle ce fichier répond est celle-ci : *si un attaquant écrit le bon
nom d'agent dans un certificat qu'il a fabriqué lui-même, le validateur s'en
aperçoit-il ?* Trois tests de :class:`TestTheSignatureIsReallyVerified` y répondent.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import timedelta
from pathlib import Path

import pytest
from cryptography.x509.oid import ExtendedKeyUsageOID

from app.core.errors import InfrastructureError
from app.security.certificates.validator import (
    REASON_EXPIRED,
    REASON_IDENTITY,
    REASON_ISSUER_NOT_CA,
    REASON_MALFORMED,
    REASON_NO_TRUST_ANCHOR,
    REASON_NOT_YET_VALID,
    REASON_REVOKED,
    REASON_UNTRUSTED,
    REASON_USAGE,
    CertificateRejected,
    MTLSCertValidator,
)
from tests.security import pki
from tests.security.pki import TestCertificate

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATE_CERTS = REPO_ROOT / "scripts" / "generate_certs.sh"


@pytest.fixture(scope="module")
def authority() -> TestCertificate:
    """The trust anchor configured on the validator under test."""
    return pki.make_ca("INIS-Test-CA")


@pytest.fixture(scope="module")
def foreign_authority() -> TestCertificate:
    """A CA the deployment never trusted."""
    return pki.make_ca("Foreign-CA")


@pytest.fixture
def validator(authority: TestCertificate) -> MTLSCertValidator:
    """A validator trusting exactly :func:`authority`."""
    return MTLSCertValidator(trusted_cas=[authority.pem])


class TestAValidCertificateIsAccepted:
    """Le cas nominal : sans lui, tout le reste ne prouverait que des refus."""

    def test_the_agent_identity_comes_from_the_verified_certificate(
        self, validator: MTLSCertValidator, authority: TestCertificate
    ) -> None:
        """A CA-signed client certificate yields its CN as the agent id."""
        client = pki.make_client(authority, "AGENT_AGT_0001")
        authenticated = validator.validate([client.pem])
        assert authenticated.agent_id == "AGENT_AGT_0001"
        assert authenticated.chain_length == 2
        assert authenticated.serial_number == client.certificate.serial_number

    def test_a_pem_bundle_works_as_well_as_a_chain_list(
        self, validator: MTLSCertValidator, authority: TestCertificate
    ) -> None:
        """The ASGI extension gives a list; a file gives a bundle — both work."""
        client = pki.make_client(authority, "AGENT_AGT_0002")
        as_list = validator.validate([client.pem]).agent_id
        as_bundle = validator.validate(client.pem).agent_id
        assert as_list == as_bundle == "AGENT_AGT_0002"

    def test_a_two_level_chain_is_walked(
        self, validator: MTLSCertValidator, authority: TestCertificate
    ) -> None:
        """CA → intermediate CA → leaf is accepted, and the depth is reported."""
        intermediate = pki.build_certificate(
            subject_common_name="INIS-Test-Intermediate",
            subject_key=pki.new_key(),
            issuer_name=authority.certificate.subject,
            issuer_key=authority.key,
            is_ca=True,
            eku=None,
        )
        leaf = pki.make_client(intermediate, "AGENT_AGT_DEEP")
        authenticated = validator.validate([leaf.pem, intermediate.pem])
        assert authenticated.agent_id == "AGENT_AGT_DEEP"
        assert authenticated.chain_length == 3


class TestTheSignatureIsReallyVerified:
    """Le cœur de la preuve : des métadonnées justes ne suffisent pas."""

    def test_a_certificate_signed_by_someone_else_claiming_our_ca_is_refused(
        self, validator: MTLSCertValidator, authority: TestCertificate
    ) -> None:
        """Same issuer *name* and same CN, but the signature is not the CA's.

        C'est le scénario exact qu'une implémentation « CN seulement » acceptait :
        le nom de l'autorité est écrit dans le certificat, mais la signature a été
        faite par une autre clé.
        """
        forged = pki.build_certificate(
            subject_common_name="AGENT_AGT_0001",
            subject_key=pki.new_key(),
            issuer_name=authority.certificate.subject,
            issuer_key=pki.make_ca("Attacker").key,
        )
        with pytest.raises(CertificateRejected) as caught:
            validator.validate([forged.pem])
        assert caught.value.reason == REASON_UNTRUSTED

    def test_a_certificate_signed_by_an_untrusted_ca_is_refused(
        self, validator: MTLSCertValidator, foreign_authority: TestCertificate
    ) -> None:
        """A perfectly valid certificate from an unknown CA is still untrusted."""
        stranger = pki.make_client(foreign_authority, "AGENT_AGT_0001")
        with pytest.raises(CertificateRejected) as caught:
            validator.validate([stranger.pem])
        assert caught.value.reason == REASON_UNTRUSTED

    def test_an_issuer_without_ca_permission_cannot_sign(
        self, authority: TestCertificate
    ) -> None:
        """``basicConstraints CA:false`` is not an authority.

        ⚠️ Défaut trouvé en écrivant ce module : ``verify_directly_issued_by``
        vérifie la signature mais **pas** la qualité de CA de l'émetteur. Ce test
        est la garde qui empêche le retour du trou.
        """
        impostor = pki.build_certificate(
            subject_common_name="Not-A-CA",
            subject_key=pki.new_key(),
            issuer_name=authority.certificate.subject,
            issuer_key=authority.key,
            is_ca=False,
            eku=None,
        )
        leaf = pki.make_client(impostor, "AGENT_AGT_UNDER_IMPOSTOR")
        with pytest.raises(CertificateRejected) as caught:
            MTLSCertValidator(trusted_cas=[authority.pem]).validate(
                [leaf.pem, impostor.pem]
            )
        assert caught.value.reason == REASON_ISSUER_NOT_CA

    def test_an_anchor_without_ca_permission_is_refused(
        self, authority: TestCertificate
    ) -> None:
        """Un point d'ancrage mal configuré n'authentifie personne."""
        not_a_ca = pki.build_certificate(
            subject_common_name="Misconfigured-Anchor",
            subject_key=pki.new_key(),
            issuer_name=authority.certificate.subject,
            issuer_key=authority.key,
            is_ca=False,
            eku=None,
        )
        leaf = pki.make_client(not_a_ca, "AGENT_AGT_0003")
        with pytest.raises(CertificateRejected) as caught:
            MTLSCertValidator(trusted_cas=[not_a_ca.pem]).validate([leaf.pem])
        assert caught.value.reason == REASON_ISSUER_NOT_CA

    def test_an_incomplete_chain_is_refused(
        self, validator: MTLSCertValidator, authority: TestCertificate
    ) -> None:
        """A leaf whose issuer is missing from the chain cannot be attached."""
        intermediate = pki.build_certificate(
            subject_common_name="INIS-Test-Intermediate",
            subject_key=pki.new_key(),
            issuer_name=authority.certificate.subject,
            issuer_key=authority.key,
            is_ca=True,
            eku=None,
        )
        leaf = pki.make_client(intermediate, "AGENT_AGT_ORPHAN")
        with pytest.raises(CertificateRejected) as caught:
            validator.validate([leaf.pem])
        assert caught.value.reason == REASON_UNTRUSTED


class TestTemporalValidity:
    """La fenêtre de validité est vérifiée, avec deux refus distincts."""

    def test_an_expired_certificate_is_refused(
        self, validator: MTLSCertValidator, authority: TestCertificate
    ) -> None:
        """Un certificat dont la signature est bonne mais qui est périmé est refusé."""
        expired = pki.make_client(
            authority,
            "AGENT_AGT_EXPIRED",
            not_before=pki.now() - timedelta(days=30),
            not_after=pki.now() - timedelta(days=2),
        )
        with pytest.raises(CertificateRejected) as caught:
            validator.validate([expired.pem])
        assert caught.value.reason == REASON_EXPIRED

    def test_a_certificate_not_yet_valid_is_refused(
        self, validator: MTLSCertValidator, authority: TestCertificate
    ) -> None:
        """« Pas encore valide » n'est pas « expiré » : le motif le distingue."""
        early = pki.make_client(
            authority,
            "AGENT_AGT_EARLY",
            not_before=pki.now() + timedelta(days=2),
            not_after=pki.now() + timedelta(days=30),
        )
        with pytest.raises(CertificateRejected) as caught:
            validator.validate([early.pem])
        assert caught.value.reason == REASON_NOT_YET_VALID

    def test_an_expired_intermediate_invalidates_the_chain(
        self, authority: TestCertificate
    ) -> None:
        """Une chaîne dont l'intermédiaire a expiré est refusée."""
        stale = pki.build_certificate(
            subject_common_name="Expired-Intermediate",
            subject_key=pki.new_key(),
            issuer_name=authority.certificate.subject,
            issuer_key=authority.key,
            not_before=pki.now() - timedelta(days=30),
            not_after=pki.now() - timedelta(days=2),
            is_ca=True,
            eku=None,
        )
        leaf = pki.make_client(stale, "AGENT_AGT_STALE_PATH")
        with pytest.raises(CertificateRejected) as caught:
            MTLSCertValidator(trusted_cas=[authority.pem]).validate([leaf.pem, stale.pem])
        assert caught.value.reason == REASON_EXPIRED


class TestRevocation:
    """La révocation est vérifiée — sans inventer de distribution (la spec n'en définit pas)."""

    def test_a_serially_revoked_certificate_is_refused(
        self, authority: TestCertificate
    ) -> None:
        """Un numéro de série explicitement révoqué est refusé."""
        revoked = pki.make_client(authority, "AGENT_AGT_REVOKED")
        validator = MTLSCertValidator(
            trusted_cas=[authority.pem],
            revoked_serials=[revoked.certificate.serial_number],
        )
        with pytest.raises(CertificateRejected) as caught:
            validator.validate([revoked.pem])
        assert caught.value.reason == REASON_REVOKED

    def test_a_certificate_listed_in_a_crl_is_refused(
        self, authority: TestCertificate
    ) -> None:
        """Une CRL fournie par le déploiement est appliquée."""
        revoked = pki.make_client(authority, "AGENT_AGT_CRL")
        crl = pki.make_crl(authority, [revoked])
        validator = MTLSCertValidator(trusted_cas=[authority.pem], crl=crl)
        with pytest.raises(CertificateRejected) as caught:
            validator.validate([revoked.pem])
        assert caught.value.reason == REASON_REVOKED

    def test_a_certificate_absent_from_the_crl_is_still_accepted(
        self, authority: TestCertificate, validator: MTLSCertValidator
    ) -> None:
        """Contre-preuve : la CRL ne doit pas tout refuser."""
        kept = pki.make_client(authority, "AGENT_AGT_KEPT")
        crl = pki.make_crl(authority, [pki.make_client(authority, "AGENT_AGT_OTHER")])
        with_crl = MTLSCertValidator(trusted_cas=[authority.pem], crl=crl)
        assert with_crl.validate([kept.pem]).agent_id == "AGENT_AGT_KEPT"
        assert validator.validate([kept.pem]).agent_id == "AGENT_AGT_KEPT"

    def test_an_unreadable_crl_is_an_operational_error(
        self, authority: TestCertificate
    ) -> None:
        """Une CRL illisible est une faute de configuration, pas un refus client."""
        with pytest.raises(InfrastructureError):
            MTLSCertValidator(trusted_cas=[authority.pem], crl=b"not a crl")

    def test_an_unreadable_trust_anchor_is_an_operational_error(self) -> None:
        """Idem pour une ancre : ``trusted_cas`` n'accepte pas n'importe quoi."""
        with pytest.raises(InfrastructureError):
            MTLSCertValidator(trusted_cas=["ca-1"])


class TestIdentity:
    """Le ``CN`` devient l'``agent_id`` — et doit être utilisable."""

    def test_a_certificate_without_common_name_is_refused(
        self, validator: MTLSCertValidator, authority: TestCertificate
    ) -> None:
        """Un sujet sans ``CN`` ne nomme aucun agent."""
        anonymous = pki.build_certificate(
            subject_common_name=None,
            subject_key=pki.new_key(),
            issuer_name=authority.certificate.subject,
            issuer_key=authority.key,
        )
        with pytest.raises(CertificateRejected) as caught:
            validator.validate([anonymous.pem])
        assert caught.value.reason == REASON_IDENTITY

    def test_a_common_name_outside_the_agent_namespace_is_refused(
        self, validator: MTLSCertValidator, authority: TestCertificate
    ) -> None:
        """Un certificat serveur ne doit pas servir d'identité d'agent."""
        server = pki.make_client(authority, "server-01")
        with pytest.raises(CertificateRejected) as caught:
            validator.validate([server.pem])
        assert caught.value.reason == REASON_IDENTITY

    def test_two_common_names_are_ambiguous_and_refused(
        self, validator: MTLSCertValidator, authority: TestCertificate
    ) -> None:
        """Deux ``CN`` rendent l'identité ambiguë : refus, pas de choix arbitraire."""
        ambiguous = pki.build_certificate(
            subject_common_name="AGENT_AGT_FIRST",
            subject_key=pki.new_key(),
            issuer_name=authority.certificate.subject,
            issuer_key=authority.key,
            extra_common_names=("AGENT_AGT_SECOND",),
        )
        with pytest.raises(CertificateRejected) as caught:
            validator.validate([ambiguous.pem])
        assert caught.value.reason == REASON_IDENTITY

    def test_the_namespace_can_be_relaxed_explicitly(
        self, authority: TestCertificate
    ) -> None:
        """Un déploiement qui n'utilise pas le préfixe peut le dire — jamais par défaut."""
        relaxed = MTLSCertValidator(
            trusted_cas=[authority.pem], require_agent_namespace=False
        )
        client = pki.make_client(authority, "server-01")
        assert relaxed.validate([client.pem]).agent_id == "server-01"


class TestUsage:
    """Un certificat qui se déclare non-client est refusé."""

    def test_a_server_only_certificate_is_refused(
        self, validator: MTLSCertValidator, authority: TestCertificate
    ) -> None:
        """``extendedKeyUsage = serverAuth`` n'autorise pas l'usage client."""
        server_only = pki.make_client(
            authority, "AGENT_AGT_SERVER", eku=(ExtendedKeyUsageOID.SERVER_AUTH,)
        )
        with pytest.raises(CertificateRejected) as caught:
            validator.validate([server_only.pem])
        assert caught.value.reason == REASON_USAGE

    def test_no_declared_usage_is_not_a_restriction(
        self, validator: MTLSCertValidator, authority: TestCertificate
    ) -> None:
        """Sans extension d'usage, rien n'est interdit (comme ``generate_certs.sh``)."""
        plain = pki.make_client(authority, "AGENT_AGT_PLAIN", eku=None)
        assert validator.validate([plain.pem]).agent_id == "AGENT_AGT_PLAIN"


class TestMalformedAndFailClosed:
    """Rien à lire, ou rien pour décider ⇒ refus. Jamais d'acceptation par défaut."""

    @pytest.mark.parametrize(
        "material",
        ["", "not a pem", "-----BEGIN CERTIFICATE-----\nzzz\n-----END CERTIFICATE-----\n"],
    )
    def test_unusable_material_is_refused(
        self, validator: MTLSCertValidator, material: str
    ) -> None:
        """Un contenu vide ou illisible est un refus explicite."""
        with pytest.raises(CertificateRejected) as caught:
            validator.validate(material)
        assert caught.value.reason == REASON_MALFORMED

    def test_an_empty_chain_is_refused(self, validator: MTLSCertValidator) -> None:
        """Une liste vide n'est pas un certificat."""
        with pytest.raises(CertificateRejected) as caught:
            validator.validate([])
        assert caught.value.reason == REASON_MALFORMED

    def test_without_trust_anchor_everything_is_refused(
        self, authority: TestCertificate
    ) -> None:
        """Échec fermé : un validateur non configuré n'authentifie personne."""
        client = pki.make_client(authority, "AGENT_AGT_ANY")
        with pytest.raises(CertificateRejected) as caught:
            MTLSCertValidator().validate([client.pem])
        assert caught.value.reason == REASON_NO_TRUST_ANCHOR

    def test_a_rejection_never_leaks_certificate_material(
        self, validator: MTLSCertValidator, authority: TestCertificate
    ) -> None:
        """Le message de refus ne recopie ni le PEM, ni le ``CN``, ni le série.

        Un message d'erreur ne doit pas devenir un canal d'exfiltration : il est
        journalisé, agrégé et parfois renvoyé au client.
        """
        client = pki.make_client(authority, "AGENT_AGT_SECRET_NAME")
        crl = pki.make_crl(authority, [client])
        revoking = MTLSCertValidator(trusted_cas=[authority.pem], crl=crl)
        with pytest.raises(CertificateRejected) as caught:
            revoking.validate([client.pem])
        message = str(caught.value)
        assert "AGENT_AGT_SECRET_NAME" not in message
        assert "BEGIN CERTIFICATE" not in message
        assert str(client.certificate.serial_number) not in message
        assert caught.value.reason in message


class TestTheRepositoryToolingIsConsistent:
    """Le plan cite ``scripts/generate_certs.sh`` comme source des matériaux."""

    @pytest.mark.skipif(
        shutil.which("openssl") is None or shutil.which("sh") is None,
        reason="openssl et sh sont nécessaires pour produire les matériaux du dépôt",
    )
    def test_the_material_generated_by_the_repository_is_accepted(
        self, tmp_path: Path
    ) -> None:
        """Le script du dépôt doit produire un certificat que le validateur accepte.

        Sans ce test, les deux moitiés de l'item pourraient diverger : un script qui
        émet ``CN=agent-default`` et un validateur qui exige l'espace ``AGENT_``
        resteraient tous deux « verts » séparément. ``MSYS_NO_PATHCONV`` neutralise
        la réécriture de ``/CN=...`` en chemin Windows quand Git Bash appelle
        ``openssl``.
        """
        certs = tmp_path / "certs"
        environment = {
            **os.environ,
            "CERTS_DIR": str(certs),
            "MSYS_NO_PATHCONV": "1",
        }
        result = subprocess.run(
            ["sh", str(GENERATE_CERTS)],
            env=environment,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        validator = MTLSCertValidator(trusted_cas=[(certs / "ca.crt").read_text("ascii")])
        authenticated = validator.validate(
            [(certs / "client.crt").read_text("ascii")]
        )
        assert authenticated.agent_id == "AGENT_agent-default"
        assert authenticated.chain_length == 2
        # Le `rm` du script quotait son glob : il ne supprimait donc rien.
        assert not list(certs.glob("*.csr"))
