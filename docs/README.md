# Documentation

This folder documents the current software shape and the intended growth path from scaffold to production billing platform.

## Documents

- [getting-started.md](getting-started.md): local setup, migrations, API boot, and basic developer workflows
- [current-status.md](current-status.md): current capability boundary, major gaps, and recommended build order
- [architecture.md](architecture.md): subsystem boundaries, orchestration flow, and deployment model
- [api-and-cloud.md](api-and-cloud.md): private REST API boundary, JWT/auth flow, and cloud rollout shape
- [domain-model.md](domain-model.md): core entities, responsibilities, and lifecycle notes
- [persistence-and-security.md](persistence-and-security.md): runtime profiles, repositories, audit model, and query-safety rules
- [procedures-and-transports.md](procedures-and-transports.md): supported billing lanes, transport families, and current implementation boundaries
- [redundancy-and-dr.md](redundancy-and-dr.md): HA Postgres, backup, residency, and disaster-recovery assumptions

## Current Status

The codebase is a functional platform scaffold. It now includes a SQLAlchemy-based persistence/security foundation and a private FastAPI boundary alongside the original in-memory billing flow, but it does not yet implement every legally required detail from the official GKV, ITSG, and Gematik specifications.

Use this folder to document:

- architecture decisions
- technical assumptions taken from specifications
- procedure-specific payload constraints
- rollout notes when the system moves from in-memory scaffolding to persistent services and real integrations
