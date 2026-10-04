"""X.509 client-certificate validation for inter-agent mTLS (§19.2).

§19.2 est court et volontairement muet sur les détails : « *mTLS pour
inter-agents* », plus `security.auth_method ∈ {mtls, jwt, api_key}` (§5.1). La
spec ne définit **ni** algorithme, **ni** PKI, **ni** autorité de certification,
**ni** révocation (CRL/OCSP), **ni** format de certificat, **ni** intégration
réseau. Ce module n'en invente donc aucun : il vérifie ce que « mTLS » implique
par construction — un certificat X.509 présenté par le pair est **réellement
vérifié** (signature, chaîne, fenêtre de validité) — et il refuse tout ce qu'il
ne peut pas établir.

Ce qui est vérifié, dans cet ordre, chacun avec un motif de refus distinct :

1. **Lisibilité** — la chaîne est du PEM X.509 exploitable ;
2. **Validité temporelle** — `notBefore`/`notAfter` du feuillet *et* de chaque
   élément de chaîne, à l'instant fourni par l'horloge ;
3. **Révocation** — numéro de série du feuillet dans une liste explicite ou dans
   une CRL fournie par le déploiement (aucun téléchargement : la spec ne définit
   aucune distribution) ;
4. **Chaîne de confiance** — remontée de signatures jusqu'à une ancre de
   confiance configurée (`verify_directly_issued_by` : nom de l'émetteur,
   signature cryptographique et `basicConstraints CA:true` de l'émetteur) ;
5. **Identité** — `CN` unique et nommé dans l'espace `AGENT_` (convention déjà
   en vigueur dans `app/security/authn/mtls_validator.py`) devient `agent_id`.

**Ce que ce module ne fait pas, et ne prétend pas faire** : télécharger une CRL
ou interroger un répondeur OCSP, appliquer les *name constraints* ou les
*policy constraints*, ni arbitrer un algorithme de signature (il utilise celui
déclaré dans le certificat, et refuse ce que la bibliothèque ne sait pas
vérifier). Un déploiement qui exige ces points doit les ajouter explicitement.

L'échec est **fermé** : sans ancre de confiance configurée, tout certificat est
refusé — jamais accepté par défaut. Les motifs de refus sont des codes stables
et **n'incluent jamais** le certificat, son sujet ou son numéro de série : un
message d'erreur ne doit pas devenir un canal d'exfiltration.

Ce paquet expose deux choses, et **une seule** parle au monde web :

* :mod:`app.security.certificates.validator` — la vérification X.509 elle-même,
  sans aucune dépendance web, donc utilisable partout (le canal inter-agents
  d'INIS est AMQP, et la spec n'impose aucun transport) ;
* :mod:`app.security.certificates.dependency` — la liaison FastAPI
  (``require_agent_certificate``) et l'identité authentifiée
  (``AgentAuthentication``).

Ce fichier n'importe **que** le validateur : importer ``app.security`` ne doit pas
tirer FastAPI dans un processus qui n'en a pas besoin. Pour la dépendance web, le
chemin est explicite —
``from app.security.certificates.dependency import require_agent_certificate``.
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
