# Blue-Green Deployment Strategy (§41.14)

This procedure implements zero-downtime Blue-Green deployments for INIS API.

## Principle
Two identical environments:
- **Blue**: Currently live active version (e.g., v2.0.0-rc1)
- **Green**: Idle environment where new release (e.g., v2.0.0) is deployed and verified

## Zero-Downtime Migration Rule
Per §41.14, every database migration must be backward-compatible with the Blue version:
- Never DROP columns or rename active tables
- New columns must have defaults or be nullable
- Checker: `python scripts/migrations/check_backward_compat.py migrations/versions`

## Rollout Steps
1. **Pre-flight**: Run `python scripts/migrations/check_backward_compat.py`.
2. **Migrate DB**: Apply `alembic upgrade head`. Since changes are backward compatible, Blue keeps running normally.
3. **Deploy Green**: Spin up Green pods with new release container.
4. **Health Check Green**: Poll `/v1/health` and `/v1/health/ready` on Green. Confirm `migrations.up_to_date == true` and `checks.*.status` are ready.
5. **Switch Traffic**: Update ingress / service routing to point to Green.
6. **Drain Blue**: Monitor metrics `/v1/metrics`. Terminate Blue pods after in-flight requests finish.
