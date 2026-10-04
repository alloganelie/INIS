"""A real — but disposable — PKI for the §19.2 mTLS proofs.

Chaque certificat de ce module est **réellement signé** : les tests qui s'en
servent prouvent une vérification cryptographique, pas la lecture d'un
dictionnaire. Un test qui n'utilise que des chaînes de caractères ne peut pas
distinguer « la signature est valide » de « le champ ``CN`` contient le bon mot ».

Les clés et certificats sont générés en mémoire. Seule l'intégration TLS a besoin
de fichiers : :func:`write_pem` les écrit dans un dossier temporaire.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import ClassVar

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID, ObjectIdentifier

#: Algorithme de test : RSA 2048 comme `scripts/generate_certs.sh`, pour que le
#: test éprouve la même famille de clés que l'outillage du dépôt.
RSA_PUBLIC_EXPONENT = 65537
RSA_KEY_SIZE = 2048

#: Fenêtre par défaut d'un certificat de test : ni expiré, ni « pas encore valide ».
DEFAULT_NOT_BEFORE_DELTA = timedelta(days=1)
DEFAULT_NOT_AFTER_DELTA = timedelta(days=30)


@dataclass(frozen=True)
class TestCertificate:
    """Une paire clé/certificat générée pour un test."""

    #: Ce n'est pas une classe de test : sans ce marqueur, pytest tente de la
    #: collecter parce que son nom commence par ``Test``, et avertit.
    __test__: ClassVar[bool] = False

    certificate: x509.Certificate
    key: rsa.RSAPrivateKey

    @property
    def pem(self) -> str:
        """Return the certificate as PEM text."""
        return self.certificate.public_bytes(serialization.Encoding.PEM).decode("ascii")

    @property
    def key_pem(self) -> str:
        """Return the private key as unencrypted PKCS#8 PEM text."""
        return self.key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("ascii")


def new_key() -> rsa.RSAPrivateKey:
    """Generate a fresh RSA key for one certificate."""
    return rsa.generate_private_key(
        public_exponent=RSA_PUBLIC_EXPONENT, key_size=RSA_KEY_SIZE
    )


def subject_name(common_name: str, *, organization: str = "INIS-Tests") -> x509.Name:
    """Build an X.509 name carrying exactly one CN."""
    return x509.Name(
        [
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ]
    )


def now() -> datetime:
    """Return the reference instant used by the fixtures."""
    return datetime.now(UTC)


def window(*, days_before: int = 1, days_after: int = 30) -> tuple[datetime, datetime]:
    """Return a ``(not_before, not_after)`` pair around the current instant."""
    moment = now()
    return moment - timedelta(days=days_before), moment + timedelta(days=days_after)


def write_pem(path: Path, material: str) -> Path:
    """Write PEM *material* to *path* and return the path (TLS needs files)."""
    path.write_text(material, encoding="ascii")
    return path


def build_certificate(
    *,
    subject_common_name: str | None,
    subject_key: rsa.RSAPrivateKey,
    issuer_name: x509.Name,
    issuer_key: rsa.RSAPrivateKey,
    not_before: datetime | None = None,
    not_after: datetime | None = None,
    serial: int | None = None,
    is_ca: bool = False,
    eku: Sequence[ObjectIdentifier] | None = (ExtendedKeyUsageOID.CLIENT_AUTH,),
    extra_common_names: Sequence[str] = (),
    san: Sequence[str] = (),
) -> TestCertificate:
    """Sign one certificate with an explicit issuer name **and** issuer key.

    L'émetteur est décrit par deux paramètres distincts exprès : un test doit
    pouvoir produire un certificat qui **prétend** venir d'une autorité (même nom)
    mais dont la signature a été faite par une autre clé. C'est exactement le
    scénario qu'une implémentation qui ne lit que des métadonnées laisserait
    passer.

    Args:
        subject_common_name: le ``CN`` du sujet, ou ``None`` pour un sujet sans CN.
        subject_key: la clé publique embarquée dans le certificat.
        issuer_name: le nom de l'émetteur écrit dans le certificat.
        issuer_key: la clé qui **signe** — peut ne pas correspondre à *issuer_name*.
        not_before: début de validité ; par défaut autour de maintenant.
        not_after: fin de validité ; par défaut autour de maintenant.
        serial: numéro de série imposé (utile pour éprouver la révocation).
        is_ca: pose ``basicConstraints CA:true`` et l'usage de signature de CA.
        eku: usage étendu déclaré, ou ``None`` pour n'en déclarer aucun.
        extra_common_names: CN supplémentaires, pour éprouver « le CN est unique ».
        san: noms alternatifs (``"localhost"`` ou ``"IP:127.0.0.1"``) — nécessaires
            au client TLS qui vérifie l'identité du serveur qu'il appelle.
    """
    start, end = window()
    attributes: list[x509.NameAttribute] = [
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "INIS-Tests")
    ]
    if subject_common_name is not None:
        attributes.append(x509.NameAttribute(NameOID.COMMON_NAME, subject_common_name))
    attributes.extend(
        x509.NameAttribute(NameOID.COMMON_NAME, extra) for extra in extra_common_names
    )
    builder = (
        x509.CertificateBuilder()
        .subject_name(x509.Name(attributes))
        .issuer_name(issuer_name)
        .public_key(subject_key.public_key())
        .serial_number(x509.random_serial_number() if serial is None else serial)
        .not_valid_before(not_before or start)
        .not_valid_after(not_after or end)
        .add_extension(x509.BasicConstraints(ca=is_ca, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=is_ca,
                crl_sign=is_ca,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
    )
    if eku is not None:
        builder = builder.add_extension(x509.ExtendedKeyUsage(list(eku)), critical=False)
    if san:
        names: list[x509.GeneralName] = []
        for entry in san:
            if entry.startswith("IP:"):
                names.append(x509.IPAddress(ipaddress.ip_address(entry[3:])))
            else:
                names.append(x509.DNSName(entry))
        builder = builder.add_extension(x509.SubjectAlternativeName(names), critical=False)
    return TestCertificate(
        certificate=builder.sign(issuer_key, hashes.SHA256()), key=subject_key
    )


def make_ca(
    common_name: str = "INIS-Test-CA",
    *,
    key: rsa.RSAPrivateKey | None = None,
    not_before: datetime | None = None,
    not_after: datetime | None = None,
) -> TestCertificate:
    """Create a self-signed certificate authority usable as a trust anchor."""
    material = key or new_key()
    name = subject_name(common_name)
    return build_certificate(
        subject_common_name=common_name,
        subject_key=material,
        issuer_name=name,
        issuer_key=material,
        not_before=not_before,
        not_after=not_after,
        is_ca=True,
        eku=None,
    )


def make_client(
    authority: TestCertificate,
    common_name: str,
    **kwargs: object,
) -> TestCertificate:
    """Issue a client certificate signed by *authority*."""
    return build_certificate(
        subject_common_name=common_name,
        subject_key=new_key(),
        issuer_name=authority.certificate.subject,
        issuer_key=authority.key,
        **kwargs,  # type: ignore[arg-type]
    )


def make_crl(
    authority: TestCertificate,
    revoked: Sequence[TestCertificate],
    *,
    not_before: datetime | None = None,
    not_after: datetime | None = None,
) -> x509.CertificateRevocationList:
    """Build a CRL listing *revoked*, signed by *authority*."""
    start, end = window(days_after=7)
    builder = (
        x509.CertificateRevocationListBuilder()
        .issuer_name(authority.certificate.subject)
        .last_update(not_before or start)
        .next_update(not_after or end)
    )
    for entry in revoked:
        builder = builder.add_revoked_certificate(
            x509.RevokedCertificateBuilder()
            .serial_number(entry.certificate.serial_number)
            .revocation_date(now())
            .build()
        )
    return builder.sign(authority.key, hashes.SHA256())
