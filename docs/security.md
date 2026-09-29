# Sécurité, Authentification et Protection des Données (§19)

## 1. Niveaux d'Authentification
- **mTLS (Service-à-Service)** : Échanges chiffrés et mutuellement authentifiés entre nœuds et agents.
- **JWT (Accès HTTP API)** : Jetons porteurs à durée de vie limitée (HMAC-SHA256 ou asymétrique).
- **Clés d'API (Intégration Externe)** : Préfixes typés avec validation de droits ABAC/RBAC.

## 2. Détection et Anonymisation PII (§19)
Les données nominatives, emails, numéros de téléphone et coordonnées bancaires sont détectés et masqués via le module `app.security.pii.redactor` avant toute ingestion durable ou exposition en log.

## 3. Traces LLM et Anonymisation (§41.12)
Les traces décisionnelles des LLM ne stockent **jamais** les prompts en clair : seule l'empreinte SHA-256 (`prompt_hash`) est persistée pour audit.

