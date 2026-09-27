# Canary Deployment Strategy (§41.14)

Canary routing allows gradual traffic shifting (e.g. 5% -> 25% -> 100%) to validate releases in production.

## Architecture
- **Primary (Stable)**: Handles 95% of traffic.
- **Canary**: Handles 5% of traffic, matched via header `X-Canary: true` or weighted routing via Istio / Nginx Ingress.

## Gate Criteria
1. Latency: p99 latency on canary must not exceed 1.2x baseline.
2. Error Rate: 5xx errors on canary must be < 0.1%.
3. Health check `/v1/health/ready` must report operational status.
