"""§19.2 — chemin d'import historique vers le validateur mTLS.

L'implémentation réelle vit dans :mod:`app.security.certificates.validator` (le
plan L8 place la validation X.509 dans ``app/security/certificates/``). Ce module
ne fait que **ré-exporter** la même classe : il n'existe pas de seconde
architecture d'authentification, et le nom ``MTLSCertValidator`` reste valide pour
les appelants historiques comme pour ``app.security``.

Ce qui a changé, et pourquoi : l'ancienne implémentation acceptait un
dictionnaire ``{"subject": {"cn": ...}}`` et ne vérifiait que le préfixe du nom
commun. Un ``CN`` n'est pas une preuve — n'importe qui peut écrire le bon nom dans
un certificat auto-signé. Le validateur exige désormais un certificat PEM réel,
vérifie sa signature jusqu'à une ancre de confiance configurée, sa fenêtre de
validité, sa non-révocation, puis seulement son identité.
"""

from __future__ import annotations

from app.security.certificates.validator import (
    AGENT_IDENTITY_NAMESPACE,
    AgentCertificate,
    CertificateRejected,
    MTLSCertValidator,
)

__all__ = [
    "AGENT_IDENTITY_NAMESPACE",
    "AgentCertificate",
    "CertificateRejected",
    "MTLSCertValidator",
]

