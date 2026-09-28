# INIS — Production Cloud Deployment Guide

This guide details enterprise cloud deployment strategies for INIS across major cloud providers (AWS, GCP, Azure), Kubernetes architectures, Helm, and production Docker Compose per §19, §32, and §35.

---

## 1. Supported Cloud Architecture Overview

| Cloud Provider | Managed Kubernetes | Managed Database (pgvector) | Object Storage |
|---|---|---|---|
| **AWS** | Amazon EKS | Amazon RDS for PostgreSQL (pgvector enabled) | Amazon S3 |
| **GCP** | Google Kubernetes Engine (GKE) | Cloud SQL for PostgreSQL (pgvector enabled) | Google Cloud Storage (GCS) |
| **Azure** | Azure Kubernetes Service (AKS) | Azure Database for PostgreSQL - Flexible Server | Azure Blob Storage |

---

## 2. Environment Variables Reference

The following environment variables configure the INIS API, workers, message brokers, and storage services.

### Core Database & Caching
| Variable | Description | Example |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string (asyncpg/psycopg) | `postgresql://inis_user:secret@postgres.cloud:5432/inis_db` |
| `INIS_DATABASE_URL` | Explicit INIS database URI for repository layer | `postgresql://inis_user:secret@postgres.cloud:5432/inis_db` |
| `REDIS_URL` | Redis endpoint for cache, rate limiting, and ephemeral state | `redis://:redis_secret@redis.cloud:6379/0` |

### Message Broker (AMQP / RabbitMQ)
| Variable | Description | Example |
|---|---|---|
| `RABBITMQ_URL` | RabbitMQ broker AMQP URL for inter-agent communication | `amqp://inis_user:secret@rabbitmq.cloud:5672//` |
| `AMQP_URL` | Alternative AMQP broker connection string | `amqp://inis_user:secret@rabbitmq.cloud:5672//` |

### Object Storage (S3 / GCS / Azure Blob)
| Variable | Description | Example |
|---|---|---|
| `S3_ENDPOINT` | Custom endpoint for S3-compatible APIs (MinIO/GCS/Azure) | `https://s3.eu-west-3.amazonaws.com` |
| `S3_ACCESS_KEY` | S3 access key / cloud storage client ID | `AKIAIOSFODNN7EXAMPLE` |
| `S3_SECRET_KEY` | S3 secret access key / cloud storage secret | `wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY` |
| `S3_BUCKET` | Target bucket name for artifacts and documents | `inis-production-artifacts` |
| `S3_REGION` | Storage region | `eu-west-3` |
| `S3_USE_SSL` | Enable SSL/TLS for storage client | `true` |

### Security & Authentication
| Variable | Description | Example |
|---|---|---|
| `JWT_SECRET` | Secret key used for signing and verifying JWT tokens | `generate-a-strong-random-hex-secret` |
| `JWT_ALGORITHM` | JWT signing algorithm | `HS256` |
| `AUTH_STRICT_MODE` | Enforce authentication on all protected endpoints | `true` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token expiration in minutes | `60` |

#### Rate limiting — MANDATORY in production

| Variable | Description | Example |
|---|---|---|
| `INIS_AUTH_ENABLED` | Enables the auth middleware (§19) | `true` |
| `INIS_RATE_LIMIT_ENABLED` | Enables the per-actor token bucket (§19) | `true` |
| `RATE_LIMIT_RPM` | Requests per minute and per `actor_id` | `60` |

> **MANDATORY:** `INIS_RATE_LIMIT_ENABLED=true` is required in production.
> Without it an authenticated API accepts unlimited requests per actor.
>
> Precedence: an explicit `INIS_RATE_LIMIT_ENABLED` always wins. When it is not
> set, the limiter defaults to **on** if `INIS_AUTH_ENABLED=true`, so enabling
> authentication can never leave the API unmetered by omission. With
> `INIS_AUTH_ENABLED=false` (local dev, CI) it stays off, and setting
> `RATE_LIMIT_RPM` re-enables it.
>
> When `REDIS_URL` is set the buckets are shared across replicas; otherwise each
> pod enforces its own budget. `/v1/health*` and `/v1/status` are never metered
> so orchestrator probes cannot be throttled.

### External APIs & LLM Providers
| Variable | Description | Example |
|---|---|---|
| `LLM_API_KEY` | Primary LLM provider API key | `sk-proj-your-api-key` |
| `LLM_PROVIDER` | LLM router provider (`openai`, `anthropic`, `gemini`) | `openai` |
| `LLM_MODEL` | Default LLM model name | `gpt-4o` |
| `SERPER_API_KEY` | Web search provider API key (Serper) | `your-serper-api-key` |

### Server & Observability
| Variable | Description | Example |
|---|---|---|
| `ENVIRONMENT` | Target deployment environment | `production` |
| `LOG_LEVEL` | Log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO` |
| `PORT` | API listen port | `8000` |
| `CORS_ORIGINS` | Comma-separated list of allowed origins | `https://inis.example.com,https://app.inis.example.com` |
| `GIT_COMMIT` | Injected commit SHA for version endpoint | `abcdef1234567890` |

---

## 3. Cloud Provider Deployment Guides

### A. Amazon Web Services (AWS)
1. **Compute (EKS)**:
   - Deploy managed node groups across at least 3 Availability Zones.
   - Configure IAM Roles for Service Accounts (IRSA) for pod permissions.
2. **Database (RDS)**:
   - Provision Amazon RDS PostgreSQL 16 Multi-AZ.
   - Run `CREATE EXTENSION IF NOT EXISTS vector;` in the primary database.
3. **Storage (S3)**:
   - Create private S3 bucket with default KMS encryption and versioning.
   - Block public access on the bucket.
4. **Deploy manifests**:
   ```bash
   kubectl apply -f deploy/cloud/k8s/secrets.yaml
   kubectl apply -f deploy/cloud/k8s/deployment.yaml
   kubectl apply -f deploy/cloud/k8s/ingress.yaml
   ```

### B. Google Cloud Platform (GCP)
1. **Compute (GKE)**:
   - Create GKE Autopilot or Standard regional cluster.
   - Enable Workload Identity Federation.
2. **Database (Cloud SQL)**:
   - Create Cloud SQL PostgreSQL 16 instance with High Availability (HA).
   - Enable `cloudsql.enable_pgvector` database flag.
3. **Storage (Cloud Storage)**:
   - Create regional or dual-region GCS bucket with uniform bucket-level access.
   - Configure S3-compatible interoperability keys or service account credentials.

### C. Microsoft Azure
1. **Compute (AKS)**:
   - Create AKS cluster with Azure CNI and managed identity.
2. **Database (PostgreSQL Flexible Server)**:
   - Provision Azure Database for PostgreSQL Flexible Server with Zone Redundancy.
   - In server parameters, add `vector` to `azure.extensions`.
3. **Storage (Azure Blob Storage)**:
   - Create Blob storage account with Blob versioning and soft delete.
   - Enable S3 compatibility endpoint or use MinIO gateway / Azure SDK connector.

---

## 3 bis. SECURITY CHECKLIST (mandatory before any production deployment)

> Run through this list for every environment that is not a local dev box.
> A single unchecked box is a deployment incident waiting to happen.

- [ ] **`INIS_AUTH_ENABLED=true`** - mandatory in production. Without it the
      `AuthMiddleware` (section 19) is inactive and every endpoint is reachable
      anonymously.
- [ ] **`INIS_RATE_LIMIT_ENABLED=true`** - mandatory in production. It already
      defaults to `true` when `INIS_AUTH_ENABLED=true`, but set it explicitly so
      no auth-flag change can silently unmeter the API. Pair it with
      `RATE_LIMIT_RPM` and, in a multi-replica setup, with `REDIS_URL` so the
      budget is shared instead of per-pod.
- [ ] **`JWT_SECRET`: 64+ random characters, regenerated at every deployment.**
      Never reuse a dev value, never commit it, and rotate it together with the
      tokens it signed - a leaked secret means every issued JWT is forgeable
      until its natural expiry.
- [ ] **`secrets.yaml` is NEVER committed.** Only `secrets.yaml.example`
      (placeholders) is versioned. Materialise the real file locally or from your
      secret manager, keep it out of Git, and make sure `git status` is clean
      before you push. `.gitignore` covers `**/secrets.yaml`, `.env`, `*.pem`,
      `*.key`, `*.p12`, `*.pfx` and `**/credentials.*`.

Additional production hygiene:

- [ ] `LLM_API_KEY`, `SERPER_API_KEY`, `S3_*`, `DATABASE_URL`, `REDIS_URL`,
      `RABBITMQ_URL` all injected from a secret manager, never from a manifest
      in the repository.
- [ ] `/v1/health/ready` reports every dependency as `ready` - a `degraded`
      or `not_configured` answer on `database`, `redis`, `broker` or `llm` means
      the deployment is incomplete.
- [ ] Secrets rotation documented, and the previous secret revoked after
      rotation.

## 4. Kubernetes and Helm Usage

### Deploying via Raw Manifests
1. Copy template files:
   ```bash
   cp deploy/cloud/k8s/secrets.yaml.example deploy/cloud/k8s/secrets.yaml
   cp deploy/cloud/k8s/deployment.yaml.example deploy/cloud/k8s/deployment.yaml
   cp deploy/cloud/k8s/ingress.yaml.example deploy/cloud/k8s/ingress.yaml
   ```
2. Populate real values in `secrets.yaml`.
3. Apply:
   ```bash
   kubectl apply -f deploy/cloud/k8s/
   ```

### Deploying via Helm
```bash
helm upgrade --install inis ./deploy/cloud/helm \
  --values ./deploy/cloud/helm/values.yaml.example \
  --set secrets.jwtSecret="my-strong-secret" \
  --set secrets.databaseUrl="postgresql://..."
```

---

## 5. Production Docker Compose

For single-node or on-premises staging/production:
```bash
docker compose -f deploy/cloud/docker-compose.prod.yaml.example up -d
```
Includes:
- PostgreSQL 16 with pgvector extension
- Redis 7 for cache and queue state
- MinIO for S3-compatible object storage
- RabbitMQ 3 with management UI
- INIS API with health check probes
