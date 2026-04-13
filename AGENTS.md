# AGENTS.md

## Purpose

This repository contains a Python scaffold for a national DTA billing platform covering ambulatory `SGB V` and `SGB XI` billing flows. The current codebase models:

- care operations and billing source data
- invoice generation and correction chains
- procedure-specific serialization
- classic `KKS` / `Auftragsdatei` submission
- `TI/KIM` submission with pluggable TI bridges
- inbound processing, reconciliation, and accounting export
- runtime database profiles, SQLAlchemy persistence primitives, and local object storage
- audit context and sensitive-read/write audit foundations
- a private FastAPI boundary with JWT auth, projection reads, and realtime planning updates

The goal for contributors and coding agents is to harden this scaffold into a production-capable platform without collapsing the separation between shared platform services and procedure-specific rules.

## Working Rules

- Preserve the split between shared services and procedure-specific adapters.
- Do not bake payer- or procedure-specific rules into generic modules when they belong in a procedure adapter or master-data layer.
- Treat `classic_dta` and `ti_kim` as parallel transport families. Do not make one an implementation detail of the other.
- Treat `dakota.le` as a classic transport compatibility concern only. Do not model it as the primary transport for `HKP` or TI-based Pflege.
- Prefer small, composable changes. If a new procedure or transport rule is added, extend the adapter interfaces rather than branching platform orchestration.
- Keep application database access inside SQLAlchemy repositories and unit-of-work boundaries.
- Do not build SQL strings from user input. Use bound parameters and whitelisted sort/filter fields.
- Raw SQL belongs only in migrations, DDL, triggers, or narrowly reviewed Postgres-only setup.
- Keep modules focused. If a file starts to accumulate unrelated responsibilities, split it before adding more code.
- Prefer thin orchestration layers and explicit service boundaries over large god classes or catch-all utility modules.
- Keep classes and functions small enough that their responsibility is obvious without scrolling through multiple screens.
- Every class, function, and method must have a short docstring that explains:
  - what it does
  - params
  - returns
- Docstrings should be precise, not verbose. Describe behavior and intent, not line-by-line implementation.
- Public APIs, repositories, and services must use explicit types and predictable naming. Avoid ambiguous names like `data`, `info`, or `handle` when a domain term is known.
- Prefer composition over inheritance unless inheritance is already the established pattern in that subsystem.
- Avoid circular dependencies. Shared concepts belong in `domain.py`, `runtime.py`, `security.py`, or another deliberate boundary module, not in cross-imported service files.
- If a change adds a new workflow, update the relevant documentation in `docs/` in the same change.

## Repo Map

- [README.md](/home/chief/Projects/dta_abrechnung/README.md): top-level project summary
- [docs/README.md](/home/chief/Projects/dta_abrechnung/docs/README.md): documentation index
- [src/dta_abrechnung/domain.py](/home/chief/Projects/dta_abrechnung/src/dta_abrechnung/domain.py): core entities and enums
- [src/dta_abrechnung/runtime.py](/home/chief/Projects/dta_abrechnung/src/dta_abrechnung/runtime.py): database profiles and backend capability flags
- [src/dta_abrechnung/security.py](/home/chief/Projects/dta_abrechnung/src/dta_abrechnung/security.py): audit, actor, and role primitives
- [src/dta_abrechnung/storage.py](/home/chief/Projects/dta_abrechnung/src/dta_abrechnung/storage.py): object storage refs and local object store
- [src/dta_abrechnung/planning.py](/home/chief/Projects/dta_abrechnung/src/dta_abrechnung/planning.py): planning snapshot types
- [src/dta_abrechnung/api](/home/chief/Projects/dta_abrechnung/src/dta_abrechnung/api): FastAPI app factory, auth helpers, realtime broker, schemas, and API services
- [src/dta_abrechnung/persistence](/home/chief/Projects/dta_abrechnung/src/dta_abrechnung/persistence): SQLAlchemy runtime, models, repositories, and unit of work
- [src/dta_abrechnung/care_ops.py](/home/chief/Projects/dta_abrechnung/src/dta_abrechnung/care_ops.py): source data capture
- [src/dta_abrechnung/billing.py](/home/chief/Projects/dta_abrechnung/src/dta_abrechnung/billing.py): invoice creation and correction handling
- [src/dta_abrechnung/procedures.py](/home/chief/Projects/dta_abrechnung/src/dta_abrechnung/procedures.py): procedure adapters and serializers
- [src/dta_abrechnung/transport.py](/home/chief/Projects/dta_abrechnung/src/dta_abrechnung/transport.py): classic DTA and TI/KIM transport helpers
- [src/dta_abrechnung/platform.py](/home/chief/Projects/dta_abrechnung/src/dta_abrechnung/platform.py): orchestration facade
- [alembic](/home/chief/Projects/dta_abrechnung/alembic): migration scaffolding
- [tests/test_platform.py](/home/chief/Projects/dta_abrechnung/tests/test_platform.py): in-memory billing flow tests
- [tests/test_persistence_sqlite.py](/home/chief/Projects/dta_abrechnung/tests/test_persistence_sqlite.py): SQLite persistence and audit tests
- [tests/test_api.py](/home/chief/Projects/dta_abrechnung/tests/test_api.py): private API, auth, projection, and realtime tests

## Common Commands

- Create or use the local environment: `source .venv/bin/activate`
- Run tests: `.venv/bin/python -m unittest discover -s tests -v`
- Syntax check: `.venv/bin/python -m py_compile src/dta_abrechnung/*.py src/dta_abrechnung/api/*.py src/dta_abrechnung/persistence/*.py tests/*.py`
- Run migrations locally: `PYTHONPATH=src DTA_DATABASE_URL=sqlite:///local-dev.db .venv/bin/alembic upgrade head`
- Run the private API locally: `PYTHONPATH=src uvicorn dta_abrechnung.api.app:create_default_app --factory --host 127.0.0.1 --port 8000`

## Implementation Guidance

- New business lanes should usually mean:
  - add or extend a `ProcedureAdapter`
  - add routing/master-data capability fields if needed
  - add tests covering payload generation, submission, and inbound handling
- New shared workflows should usually be added through the platform services in `care_ops.py`, `billing.py`, `evidence.py`, `inbound.py`, or `accounting.py`.
- If you tighten payload conformance against official specs, keep the exact technical assumptions documented in `docs/`.
- If you add persistence, external APIs, or real TI integrations, document the boundary and operating model before or alongside the code change.

## Documentation Expectations

- Follow [docs/coding-standards.md](/home/chief/Projects/dta_abrechnung/docs/coding-standards.md) for structure, naming, docstrings, and module boundaries.
- Follow [docs/contributor-guide.md](/home/chief/Projects/dta_abrechnung/docs/contributor-guide.md) when adding features, refactors, tests, or docs.
- Keep [docs/end-user-manual.md](/home/chief/Projects/dta_abrechnung/docs/end-user-manual.md) aligned with the real user-facing behavior of the system.
- Update [docs/architecture.md](/home/chief/Projects/dta_abrechnung/docs/architecture.md) when subsystem boundaries change.
- Update [docs/domain-model.md](/home/chief/Projects/dta_abrechnung/docs/domain-model.md) when new core entities or lifecycle states are introduced.
- Update [docs/persistence-and-security.md](/home/chief/Projects/dta_abrechnung/docs/persistence-and-security.md) when runtime, audit, storage, or SQL-safety rules change.
- Update [docs/procedures-and-transports.md](/home/chief/Projects/dta_abrechnung/docs/procedures-and-transports.md) when a procedure, `Verfahrenskennung`, or transport rule changes.
