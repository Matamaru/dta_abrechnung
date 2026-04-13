# API And Cloud Rollout

## Current API Surface

The repo now includes a private `FastAPI` application under `src/dta_abrechnung/api/`.

Implemented v1 routes:

- `GET /api/v1/health/live`
- `GET /api/v1/health/primary-db`
- `GET /api/v1/health/read-replica`
- `GET /api/v1/health/projections`
- `POST /api/v1/tenants`
- `GET /api/v1/tenants`
- `GET /api/v1/tenants/{tenant_id}`
- `POST /api/v1/providers`
- `GET /api/v1/tenants/{tenant_id}/providers`
- `GET /api/v1/providers/{provider_id}`
- `POST /api/v1/planning/snapshots`
- `GET /api/v1/planning/snapshots`
- `GET /api/v1/planning/snapshots/latest`
- `GET /api/v1/audit/events`
- `WS /api/v1/realtime/planning`

The routes are task-focused. They do not expose generic table CRUD and they do not allow direct database access from clients.

## API Shape

The current route split is:

- health and infrastructure checks
- administrative commands for tenants and providers
- projection writes and projection reads for planning snapshots
- audit inspection
- realtime planning updates over websocket

This is intentionally narrow. The API is meant to grow around business workflows, not around raw table exposure.

## Auth And Audit

The private API uses JWT bearer tokens with:

- `subject`
- `actor_type`
- `roles`
- `tenant_id`
- `token_kind`
- `source_system`
- `issuer` and `audience`
- expiry

Request handling turns JWT claims into an API `AuthContext`, then into a repo-compatible `AuditContext`.

Current role enforcement:

- `platform_admin` for tenant-wide/global administration
- `tenant_admin` and `billing_operator` for tenant-scoped operational actions
- `service_principal` for service-driven planning updates
- `auditor` or `platform_admin` for audit log queries

Sensitive reads and realtime subscription authorization are written into the audit ledger.

## Database Routing

`ApplicationSettings` now loads:

- primary database settings
- optional read-replica database settings
- object-storage settings
- KMS key identifier
- JWT settings
- public/private API URLs

Query routing is intentionally split:

- command writes use the primary runtime
- planning/projection list reads can use the read-model runtime
- if no read replica is configured, the projection runtime falls back to the primary runtime

This keeps the code compatible with local development while preserving the intended cloud shape.

## Local Run

Local boot:

```bash
source .venv/bin/activate
PYTHONPATH=src uvicorn dta_abrechnung.api.app:create_default_app --factory --host 127.0.0.1 --port 8000
```

The API reads `.env` automatically for local development. Non-local environments should inject equivalent values through secret management and deployment configuration.

## Cloud Shape

Target deployed topology:

- private `FastAPI` service inside the application network/VPC
- managed `Postgres` primary
- managed `Postgres` read replica for projection-heavy reads
- encrypted object storage for evidence and projection artifacts
- KMS-managed keys
- no direct client database access

This repo does not provision cloud resources itself. It now provides the application boundary and settings model needed to move local Postgres to managed cloud Postgres without changing the app shape.

## Next API Build Areas

- billing and correction commands
- submission job creation and status inspection
- inbound error and acknowledgement handling
- payer/master-data read models
- operator-oriented work queues
