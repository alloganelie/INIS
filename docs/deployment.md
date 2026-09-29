# Guide de Déploiement INIS

## 1. Déploiement Local avec Docker Compose
Pour un démarrage complet incluant PostgreSQL, Redis, RabbitMQ, Mosquitto, S3 et Grafana :
```bash
cp .env.example .env
docker compose up -d
```
Les migrations de schéma s'appliquent automatiquement au démarrage du conteneur API.

## 2. Déploiement en Production
Utiliser la surcouche de production :
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

## 3. Kubernetes / Helm
Les manifestes Kubernetes et charts Helm sont organisés dans :
- `deploy/k8s/` : ConfigMaps, Services, Deployments, Ingress, HPA.
- `deploy/helm/` : Chart Helm packagé et configurations de valeurs dev/prod.

