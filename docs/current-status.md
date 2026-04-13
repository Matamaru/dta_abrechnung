# Current Status

## What Exists

The repository already contains a usable technical foundation for the product direction:

- in-memory business services for care ops, billing, evidence, inbound handling, and accounting export
- procedure adapters for the targeted `SGB V` and `SGB XI` lanes
- two transport families: `classic_dta` and `ti_kim`
- SQLAlchemy persistence foundation with runtime profiles and Alembic migrations
- audit event capture for writes and sensitive reads
- private `FastAPI` boundary with JWT-based tenant scoping
- planning projection persistence and realtime update channel

## What Is Still Foundational

The current implementation is not yet a production billing product.

Major gaps:

- exact official payload formats and rule validation
- persistent SQL-backed replacement of the in-memory billing domain
- large-scale operational models for hubs, org units, rostering, missions, and tours
- external identity integration and hardened secrets management
- production infrastructure for TI/KIM, KMS, cloud object storage, and monitoring
- importer and versioning workflows for payer master data and `Kostenträgerdateien`

## Current Recommended Build Order

1. Move more business entities and workflows from in-memory storage to SQL-backed repositories.
2. Add authenticated API surfaces for billing, submission, and inbound response handling.
3. Introduce multi-hub and multi-org-unit operational models.
4. Add versioned compensation agreements, service catalogs, and service-basis rules.
5. Add planning-service integration and high-volume read models.
6. Harden procedure serializers and transport integrations against the official specifications.

## Release Readiness

Current readiness level:

- suitable for architecture exploration and iterative implementation
- suitable for local development and repository-level testing
- not yet suitable for regulated production billing operations
