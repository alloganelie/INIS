# INIS Deployment Guide

This guide covers deploying INIS using Docker Compose with the frontend, API, and PostgreSQL services.

## Prerequisites

- Docker and Docker Compose installed
- Git repository cloned locally

## Quick Start

### 1. Start all services

```bash
docker compose -f docker/docker-compose.frontend.yml up -d
```

This will start:
- **Frontend**: Available at http://localhost
- **API**: Available at http://localhost:8000
- **PostgreSQL**: Available at localhost:5432

### 2. Access the services

- **Frontend application**: http://localhost
- **API documentation**: http://localhost:8000/v1/docs
- **API OpenAPI spec**: http://localhost:8000/v1/openapi.json
- **Health check**: http://localhost:8000/health

### 3. Stop the services

```bash
docker compose -f docker/docker-compose.frontend.yml down
```

## Service Details

### Frontend Service
- **Image**: Built from `docker/Dockerfile.frontend`
- **Port**: 80 (host) → 80 (container)
- **Features**:
  - Multi-stage build (node:20-alpine → nginx:alpine)
  - Serves static files via nginx
  - Proxies `/v1/*` requests to the API service
  - SPA fallback for client-side routing

### API Service
- **Image**: Built from `docker/Dockerfile.dev`
- **Port**: 8000 (host) → 8000 (container)
- **Environment**:
  - `DATABASE_URL`: PostgreSQL connection string
  - `PYTHONUNBUFFERED`: Enabled for logging
- **Dependencies**: Waits for PostgreSQL to be healthy before starting

### PostgreSQL Service
- **Image**: pgvector/pgvector:pg16
- **Port**: 5432 (host) → 5432 (container)
- **Environment**:
  - `POSTGRES_USER`: inis
  - `POSTGRES_PASSWORD`: inis_password
  - `POSTGRES_DB`: inis
- **Volume**: `postgres_data` for persistent storage
- **Init script**: `docker/postgres/init.sql`

## Development

### Rebuild services after code changes

```bash
docker compose -f docker/docker-compose.frontend.yml up -d --build
```

### View logs

```bash
# All services
docker compose -f docker/docker-compose.frontend.yml logs -f

# Specific service
docker compose -f docker/docker-compose.frontend.yml logs -f frontend
docker compose -f docker/docker-compose.frontend.yml logs -f api
docker compose -f docker/docker-compose.frontend.yml logs -f postgres
```

### Access containers

```bash
# Frontend container
docker compose -f docker/docker-compose.frontend.yml exec frontend sh

# API container
docker compose -f docker/docker-compose.frontend.yml exec api bash

# PostgreSQL container
docker compose -f docker/docker-compose.frontend.yml exec postgres psql -U inis -d inis
```

## Troubleshooting

### Frontend build fails
- Ensure `frontend/package.json` has a valid `build` script
- Check that all dependencies are listed in `package.json`

### API cannot connect to database
- Verify PostgreSQL is healthy: `docker compose -f docker/docker-compose.frontend.yml ps postgres`
- Check the database URL in the compose file matches your environment

### Nginx proxy issues
- Check `docker/nginx/frontend.conf` for correct proxy settings
- Verify the API service is accessible from the frontend container

## Production Considerations

This setup is intended for development and testing. For production deployment, consider:

1. **Security**: Change default passwords and secrets
2. **SSL/TLS**: Use reverse proxy with HTTPS
3. **Scaling**: Use swarm mode or Kubernetes for horizontal scaling
4. **Monitoring**: Add logging and monitoring services
5. **Backups**: Implement PostgreSQL backup strategy
6. **Resource limits**: Set appropriate memory and CPU limits

## Additional Resources

- [Docker Compose documentation](https://docs.docker.com/compose/)
- [nginx configuration](https://nginx.org/en/docs/)
- [INIS specification](../INIS_SPEC.md)
