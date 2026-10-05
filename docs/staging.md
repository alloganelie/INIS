# INIS — Premier déploiement staging

Ce document décrit ce qu'un opérateur doit faire **avant** et **pendant** le
premier déploiement staging. Il ne décrit pas l'architecture métier (voir
`ARCHITECTURE.md`) ni les décisions déjà prises dans le code.

Tout ce qui suit a été vérifié sur le dépôt ; chaque élément non vérifiable en
local est marqué **« décision de déploiement »**.

---

## 1. Services requis

| Service | Image de référence | Rôle | Port interne |
|---|---|---|---|
| PostgreSQL + pgvector | `pgvector/pgvector:pg16` | schéma §27, recherche vectorielle §16 | 5432 |
| **Valkey** (protocole Redis) | `valkey/valkey:8-alpine` | cache §41.5, budget de débit §19 **partagé** | 6379 |
| RabbitMQ | `rabbitmq:3.13-management-alpine` | broker AMQP §5 | 5672 |
| Stockage objet S3 | RustFS/MinIO **ou** S3 cloud | artefacts §24.2, documents §9.1 | 9000 |
| API | `docker/Dockerfile` | API §32 | 8000 |
| (optionnel) Mosquitto, OTel, Prometheus, Grafana | voir `docker-compose.yml` | MQTT §4.4, observabilité §20/§34 | 1883, 4317/4318, 9090, 3000 |

Mosquitto, OTel, Prometheus et Grafana ne sont pas nécessaires au premier
staging fonctionnel : sans eux, l'API et le parcours complet fonctionnent.

## 2. PostgreSQL — URL **async** obligatoire

L'application (`app/storage/database/engine.py`) **et** Alembic
(`migrations/env.py`) construisent un moteur **async**. Les URL doivent donc
porter le driver `asyncpg` :

```
INIS_DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST:5432/DB
DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST:5432/DB   # alias, même valeur
```

Une URL `postgresql://` échoue avec `No module named 'psycopg'` (seul `asyncpg`
est installé). C'est le défaut corrigé dans `docker-compose.prod.yml` et
`deploy/cloud/k8s/secrets.yaml.example`.

Sur un PostgreSQL managé, l'extension `vector` doit être autorisée par le
fournisseur (la migration `0001` exécute `CREATE EXTENSION IF NOT EXISTS vector`).

## 3. Migrations

```bash
python -m alembic upgrade head            # ou : make migrate
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm migrate
```

Elles s'appliquent **avant** de servir du trafic (§41.14). Rollback d'un cran :
`make migrate-rollback` (`scripts/migrate_rollback.py`). Gate de compatibilité :
`python scripts/check_backward_compat.py migrations/versions/`.

Contrôle post-déploiement : `GET /v1/health` expose
`migrations.applied / head / latest_available / up_to_date`.

## 4. Bucket objet — à créer **avant** le démarrage

L'application **ne crée pas** le bucket (`create_bucket` est absent de
`app/storage/object_storage/`) : le bucket doit **préexister**, sinon l'upload
d'un document échoue. Aucun script de bootstrap n'est livré dans le dépôt — la
création est une opération d'infrastructure, **jamais** avec un secret committé.

Procédure (au choix) :

```bash
# a) client MinIO (mc) — S3 self-hosted
mc alias set inis-staging "$S3_ENDPOINT" "$S3_ACCESS_KEY" "$S3_SECRET_KEY"
mc mb --ignore-existing inis-staging/"$S3_BUCKET"

# b) AWS CLI — S3 cloud
aws s3 mb "s3://$S3_BUCKET" --region "$S3_REGION"
```

Résultat attendu : `bucket staging existant → INIS démarre → upload document →
création artefact → téléchargement → vérification SHA-256`.

## 5. Valkey authentifié

Le serveur est **Valkey** ; la variable reste `REDIS_URL` (schéma `redis://`,
client `redis.asyncio` — `from_url` accepte le mot de passe). En staging :

```
REDIS_URL=redis://:MOT_DE_PASSE@valkey:6379/0
```

Le mot de passe se règle côté serveur (`valkey-server --requirepass …`). En
multi-réplicas, ce store partagé rend le budget §19 commun aux instances.
**Ne pas supprimer** un volume Redis historique (RDB v12) : Valkey 8 le refuse,
il a son propre volume.

## 6. Healthchecks

| Sonde | Chemin | Ce qu'elle prouve |
|---|---|---|
| liveness | `/health` (et `/v1/health`) | le processus répond |
| readiness | `/v1/health/ready` | `database`, `redis` (Valkey), `broker` (AMQP), `llm` réels → `ready` (200) / `degraded` (200) / `not_ready` (503) |

`/v1/status` renvoie `ready` sans rien vérifier : il ne doit **pas** servir de
sonde de disponibilité (corrigé dans `deploy/k8s/deployment.yaml`).

## 7. TLS / mTLS

- **TLS d'entrée = infrastructure** (reverse proxy ou ingress). Le dépôt fournit
  un ingress cohérent (`deploy/k8s/ingress.yaml` : `cert-manager` +
  `ssl-redirect` + `secretName: inis-tls-cert`). uvicorn n'ouvre pas de TLS
  lui-même : ne pas ajouter `--ssl-certfile`/`--ssl-keyfile`.
- **mTLS inter-agents = mécanisme INIS déjà implémenté**
  (`app/security/certificates/`, trust anchors + révocation fournis par le
  déploiement, identité `CN` = `AGENT_…`). Il lit la chaîne du certificat client
  via l'extension ASGI `extensions.tls.client_cert_chain` : **le proxy/serveur
  ASGI doit la fournir**. Aucune route ne l'exige aujourd'hui ; l'activer est une
  décision d'infrastructure, pas une modification du validateur.

## 8. CORS / frontend

Le frontend appelle l'API en **chemin relatif `/v1`** et l'application ne monte
**aucun `CORSMiddleware`** (`CORS_ORIGINS` est déclarée mais lue nulle part).
L'architecture correcte en staging est **same-origin** :

```
HTTPS (proxy/ingress)
  ├── /            → frontend
  └── /v1, /health → API :8000
```

N'ajouter CORS que si le frontend est réellement servi depuis une autre origine.

## 9. Secrets — tous externes au dépôt

`JWT_SECRET`, `POSTGRES_PASSWORD`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`,
`INIS_API_KEY`, `INIS_VAULT_KEY`, `INIS_RESUME_SECRET`, `LLM_API_KEY`,
`SERPER_API_KEY`, identifiants de sources (`INIS_CRED_<REF>`).

Aucune valeur de développement par défaut ne doit être conservée en staging
(`JWT_SECRET` défaut code `inis-secret-key-v1-dev`, `INIS_API_KEY` défaut
`inis-admin-key`, `INIS_RESUME_SECRET` défaut dev).

Variables à vérifier explicitement : `INIS_AUTH_ENABLED=true`,
`INIS_RATE_LIMIT_ENABLED=true`, `REDIS_URL` avec mot de passe,
`INIS_DATABASE_URL` en `postgresql+asyncpg`, `S3_USE_SSL=true` si S3 cloud.

## 10. Vérification du parcours réel (E2E)

```bash
python -m tests.load.run_load --base-url https://staging.example.com \
    --requests 1 --concurrency 1 --rows 5 --scope staging
```

Le harnais §41.13 exécute le parcours complet (`upload → ingestion → pipeline →
livraison → téléchargement`) et **vérifie le `sha256`** de l'artefact
téléchargé ; il conclut `MEASURED` en portée `local`, `PASS`/`FAIL` en portée
`staging`. Le rapport est écrit dans `tests/load/results/`.

## 11. Décisions de déploiement (non tranchées par le dépôt)

- Choix du stockage objet : RustFS (image `1.0.0-rc.5`) ou S3 cloud managé.
- Mot de passe Valkey, réseau privé, exposition des ports.
- Domaine staging, certificats TLS, `cert-manager` ou équivalent.
- Activation réelle du mTLS (quel proxy fournit `client_cert_chain`).
- Nombre de `--workers` / dimensionnement des réplicas.
- Politique de rétention §41.9, budgets §41.2, tableaux de bord Grafana.

