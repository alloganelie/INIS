"""mTLS certificate validation per INIS §19.2."""

from typing import Any

from app.core.errors import ValidationError


class MTLSCertValidator:
    """Validate mTLS certificates for inter-agent authentication."""

    def __init__(self, trusted_cas: list[str] | None = None):
        """Initialize mTLS certificate validator.

        Args:
            trusted_cas: List of trusted CA certificates (stub for V1)
        """
        self.trusted_cas = trusted_cas or []

    def validate(self, cert: dict[str, Any]) -> str:
        """Validate mTLS certificate and return agent ID.

        Args:
            cert: Certificate dictionary with subject, issuer, etc.

        Returns:
            Agent ID if certificate is valid

        Raises:
            ValidationError: If certificate is invalid
        """
        if not cert or "subject" not in cert:
            raise ValidationError("Invalid certificate: missing subject")

        subject = cert["subject"]

        if "cn" not in subject:
            raise ValidationError("Invalid certificate: missing common name")

        agent_id = subject["cn"]

        if not agent_id.startswith("AGENT_"):
            raise ValidationError("Invalid certificate: CN must start with AGENT_")

        return agent_id
