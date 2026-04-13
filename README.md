# DTA Abrechnung

Scaffold for a national `SGB V` and `SGB XI` billing platform with:

- procedure-aware billing and transport adapters
- classic `DTA` and `TI/KIM` transport lanes
- SQLAlchemy persistence with `Postgres`/`SQLite` runtime profiles
- immutable object-storage metadata for evidence and projections
- audit-aware private `FastAPI` boundary
- local Postgres development path and Alembic migrations

## Current Scope

Implemented foundations:

- shared domain model for tenants, providers, payers, contracts, services, invoices, submissions, payments, and open items
- in-memory care-ops, billing, evidence, inbound, and accounting services
- procedure adapters for:
  - `§ 105 SGB XI` Pflege
  - `§ 302 SGB V` HKP
  - `§ 302 SGB V` Haushaltshilfe
  - `§ 302 SGB V` Heilmittel
  - `§ 302 SGB V` Hilfsmittel
  - `§ 302 SGB V` Krankentransport
- transport adapters for:
  - `classic_dta`
  - `ti_kim`
- persistence foundation for:
  - tenants
  - providers
  - object storage references
  - planning snapshots
  - audit events
- private API endpoints for:
  - health and projection freshness
  - tenant and provider commands/reads
  - planning snapshot writes and projection reads
  - audit event queries
  - realtime planning updates

Not implemented yet:

- spec-complete GKV/ITSG/Gematik payload conformance
- production user management / external identity providers
- full SQL-backed replacement of the in-memory billing core
- real TI/KIM or Dakota integrations
- production cloud provisioning and ops automation inside the repo

## Quick Start

### 1. Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Configure the environment

Use [.env.example](.env.example) as the committed reference and keep local secrets in `.env`.

### 3. Run migrations

```bash
source .venv/bin/activate
PYTHONPATH=src .venv/bin/alembic upgrade head
```

### 4. Run the API

```bash
source .venv/bin/activate
PYTHONPATH=src uvicorn dta_abrechnung.api.app:create_default_app --factory --host 127.0.0.1 --port 8000
```

### 5. Run tests

```bash
source .venv/bin/activate
.venv/bin/python -m unittest discover -s tests -v
```

## Project Layout

- [src/dta_abrechnung/api](src/dta_abrechnung/api): FastAPI app, JWT auth, schemas, realtime broker, API services
- [src/dta_abrechnung/persistence](src/dta_abrechnung/persistence): SQLAlchemy models, repositories, sessions, unit of work
- [src/dta_abrechnung/platform.py](src/dta_abrechnung/platform.py): in-memory orchestration facade
- [src/dta_abrechnung/procedures.py](src/dta_abrechnung/procedures.py): procedure-specific adapters and serializers
- [src/dta_abrechnung/transport.py](src/dta_abrechnung/transport.py): classic DTA and TI/KIM transport helpers
- [alembic](alembic): schema migration scaffolding
- [tests](tests): API, persistence, object-storage, and in-memory flow tests

## Documentation

- [docs/README.md](docs/README.md): docs index
- [docs/getting-started.md](docs/getting-started.md): local setup and day-one workflows
- [docs/current-status.md](docs/current-status.md): implemented capabilities, gaps, and next build areas
- [docs/architecture.md](docs/architecture.md): subsystem boundaries and execution flow
- [docs/api-and-cloud.md](docs/api-and-cloud.md): private API boundary and cloud rollout shape
- [docs/persistence-and-security.md](docs/persistence-and-security.md): persistence, audit, and security rules
- [docs/procedures-and-transports.md](docs/procedures-and-transports.md): current procedure coverage and transport mapping
- [docs/redundancy-and-dr.md](docs/redundancy-and-dr.md): Postgres HA and recovery assumptions

## Current Release

This repository is still a platform foundation, not a production-ready billing system. The code is structured so the API, persistence, transport, and procedure layers can be hardened incrementally without rewriting the overall system shape.
