"""Security tests: §19.2 authentication and §19.3 authorization bypass attempts.

Each test plays an attacker: a wrong API key, a forged/expired/unsigned JWT, a
certificate without a usable CN, or a subject trying to reach a ``restricted``
resource. Every attempt must end in an explicit rejection, never in a
``None``-ish "let it through" result.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

import pytest

from app.core.errors import ValidationError
from app.security.authn.api_key_validator import APIKeyValidator
from app.security.authn.jwt_validator import JWTValidator
from app.security.authn.mtls_validator import MTLSCertValidator
from app.security.authz.abac_engine import ABACEngine
from app.security.authz.permission_checker import PermissionChecker
from app.security.authz.policy_evaluator import PolicyEvaluator
from app.security.authz.rbac_engine import RBACEngine
from tests.security import pki

SECRET = "test-secret"


def _b64(data: bytes) -> str:
    """Base64url-encode *data* without padding (JWT wire format)."""
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _sign(payload: dict[str, Any], secret: str = SECRET) -> str:
    """Build a JWT with a correct HS256 signature."""
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = _b64(json.dumps(payload).encode())
    signature = _b64(
        hmac.new(secret.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest()
    )
    return f"{header}.{body}.{signature}"


class TestAPIKeyValidation:
    """§19.2 — administration API keys."""

    def test_valid_key_returns_its_identifier(self) -> None:
        """A known key is accepted and identified."""
        validator = APIKeyValidator({"admin": "key-123"})
        assert validator.validate("key-123") == "admin"

    @pytest.mark.parametrize("key", ["", "key-124", "KEY-123", "key-12", "unknown"])
    def test_wrong_key_is_rejected(self, key: str) -> None:
        """A wrong, truncated or case-changed key never validates."""
        validator = APIKeyValidator({"admin": "key-123"})
        with pytest.raises(ValidationError, match="Invalid API key"):
            validator.validate(key)

    def test_no_configured_key_refuses_everything(self) -> None:
        """An empty key store cannot authenticate anybody (fail closed)."""
        with pytest.raises(ValidationError):
            APIKeyValidator({}).validate("anything")


class TestJWTValidation:
    """§19.2 — bearer tokens."""

    def test_valid_token_returns_the_payload(self) -> None:
        """A correctly signed, unexpired token is accepted."""
        validator = JWTValidator(SECRET)
        payload = validator.validate(_sign({"sub": "AGT_1", "exp": time.time() + 60}))
        assert payload["sub"] == "AGT_1"

    def test_token_signed_with_another_secret_is_rejected(self) -> None:
        """A signature from a different key is refused."""
        token = _sign({"sub": "AGT_1"}, secret="attacker-secret")
        with pytest.raises(ValidationError, match="Invalid JWT token"):
            JWTValidator(SECRET).validate(token)

    def test_tampered_payload_is_rejected(self) -> None:
        """Re-encoding the payload breaks the signature."""
        token = _sign({"sub": "AGT_1"})
        header, _, signature = token.split(".")
        forged_body = _b64(json.dumps({"sub": "AGT_admin"}).encode())
        with pytest.raises(ValidationError):
            JWTValidator(SECRET).validate(f"{header}.{forged_body}.{signature}")

    def test_unsigned_token_is_rejected(self) -> None:
        """An ``alg=none`` style token has no valid signature."""
        header = _b64(json.dumps({"alg": "none", "typ": "JWT"}).encode())
        body = _b64(json.dumps({"sub": "AGT_admin"}).encode())
        with pytest.raises(ValidationError):
            JWTValidator(SECRET).validate(f"{header}.{body}.")

    def test_expired_token_is_rejected(self) -> None:
        """An expired token is refused even though the signature is valid."""
        token = _sign({"sub": "AGT_1", "exp": time.time() - 1})
        with pytest.raises(ValidationError):
            JWTValidator(SECRET).validate(token)

    @pytest.mark.parametrize("token", ["", "a.b", "not-a-token", "a.b.c.d"])
    def test_malformed_token_is_rejected(self, token: str) -> None:
        """Anything that is not a three-part JWT is refused."""
        with pytest.raises(ValidationError):
            JWTValidator(SECRET).validate(token)


class TestCertificateValidation:
    """§19.2 — inter-agent mTLS identity.

    L'identité vient d'un certificat **réellement vérifié** : les certificats sont
    signés pour de vrai (:mod:`tests.security.pki`), et un certificat auto-signé qui
    écrit le bon ``CN`` est exactement l'attaque que ce bloc refuse. Les cas
    exhaustifs (expiration, révocation, chaîne à plusieurs niveaux) vivent dans
    ``tests/security/test_mtls_validator.py`` ; ici, on éprouve la tentative de
    contournement.
    """

    @pytest.fixture(scope="class")
    def authority(self) -> pki.TestCertificate:
        """A CA to issue the legitimate agent certificate."""
        return pki.make_ca("INIS-Auth-Bypass-CA")

    def test_valid_certificate_returns_the_agent_id(
        self, authority: pki.TestCertificate
    ) -> None:
        """A CA-signed certificate yields its CN as the agent identity."""
        client = pki.make_client(authority, "AGENT_AGT_1")
        validator = MTLSCertValidator(trusted_cas=[authority.pem])
        assert validator.validate([client.pem]).agent_id == "AGENT_AGT_1"

    def test_a_self_signed_certificate_claiming_the_agent_name_is_rejected(
        self, authority: pki.TestCertificate
    ) -> None:
        """Writing the right CN in a self-made certificate must not be enough.

        C'est la tentative de contournement qui rendait l'ancien validateur (CN seul)
        inoffensif en apparence : le nom est bon, la signature ne l'est pas.
        """
        forger = pki.make_ca("AGENT_AGT_1")
        validator = MTLSCertValidator(trusted_cas=[authority.pem])
        with pytest.raises(ValidationError):
            validator.validate([forger.pem])

    @pytest.mark.parametrize(
        "common_name",
        ["", "AGT_1", "agent-default", "SERVER_AGT_1"],
    )
    def test_a_certificate_without_a_usable_agent_identity_is_rejected(
        self, authority: pki.TestCertificate, common_name: str
    ) -> None:
        """A CN outside the ``AGENT_`` namespace (or empty) is not an agent."""
        client = pki.make_client(authority, common_name or "placeholder")
        if not common_name:
            client = pki.build_certificate(
                subject_common_name=None,
                subject_key=pki.new_key(),
                issuer_name=authority.certificate.subject,
                issuer_key=authority.key,
            )
        validator = MTLSCertValidator(trusted_cas=[authority.pem])
        with pytest.raises(ValidationError):
            validator.validate([client.pem])

    def test_no_configured_trust_anchor_rejects_everything(self) -> None:
        """Fail closed: without a trust anchor nobody is authenticated."""
        anyone = pki.make_ca("AGENT_AGT_1")
        with pytest.raises(ValidationError):
            MTLSCertValidator().validate([anyone.pem])


class TestAuthorizationBypass:
    """§19.3 — privilege escalation attempts."""

    @pytest.fixture
    def checker(self) -> PermissionChecker:
        """Return a checker where ``admin`` holds every permission."""
        roles = {
            "admin": {"read:information", "write:information", "delete:information"},
            "reader": {"read:information"},
        }
        return PermissionChecker(PolicyEvaluator(RBACEngine(roles), ABACEngine()))

    def test_restricted_resource_is_denied_even_for_admin(
        self, checker: PermissionChecker
    ) -> None:
        """The classification veto outranks every role."""
        decision, reason = checker.check(
            {"agent_id": "AGT_admin"},
            {"type": "information", "classification": "restricted"},
            "read",
            "admin",
        )
        assert decision == "deny"
        assert "restricted" in reason

    def test_reader_cannot_write(self, checker: PermissionChecker) -> None:
        """A read-only role cannot escalate to a write."""
        decision, _ = checker.check(
            {}, {"type": "information", "classification": "public"}, "write", "reader"
        )
        assert decision == "deny"

    def test_claims_in_the_subject_do_not_grant_permissions(
        self, checker: PermissionChecker
    ) -> None:
        """A self-declared ``roles`` attribute is not an RBAC role."""
        decision, _ = checker.check(
            {"agent_id": "AGT_1", "roles": ["admin"], "scopes": ["*"]},
            {"type": "information", "classification": "public"},
            "delete",
            "reader",
        )
        assert decision == "deny"

    def test_unknown_caller_is_denied(self, checker: PermissionChecker) -> None:
        """An unregistered role is denied even on a public resource."""
        decision, _ = checker.check(
            {}, {"type": "information", "classification": "public"}, "read", "ghost"
        )
        assert decision == "deny"

