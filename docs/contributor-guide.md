# Contributor Guide

This repository is structured to grow from a scaffold into a production-capable billing platform. Contributors should protect that structure instead of solving short-term needs with cross-cutting shortcuts.

## Goals

- keep the code modular
- keep billing and transport rules explicit
- preserve auditability and tenant isolation
- make future hardening possible without large rewrites

## How To Think About The Codebase

Use these boundaries when deciding where code belongs:

- `domain.py`: stable business entities, value objects, enums
- `care_ops.py`, `billing.py`, `evidence.py`, `inbound.py`, `accounting.py`: business workflows
- `procedures.py`: procedure-specific validation, serialization, and inbound parsing
- `transport.py`: classic DTA and TI/KIM submission mechanics
- `api/`: HTTP auth, request/response models, endpoint orchestration, realtime delivery
- `persistence/`: SQLAlchemy models, repositories, session/runtime bootstrapping, audit-aware unit of work
- `docs/`: architecture, security, procedures, contributor rules, and user-facing instructions

When a change spans multiple boundaries, keep each layer small and explicit instead of solving everything in one file.

## Required Coding Rules

- Follow [coding-standards.md](coding-standards.md).
- Add docstrings to every class, function, and method.
- Keep API handlers thin.
- Keep repositories free of business pricing or workflow rules.
- Keep business services free of raw SQL and HTTP concerns.
- Prefer adding a focused module over expanding a file into a catch-all.

## Suggested Change Workflow

1. Identify the boundary the change belongs to.
2. Add or update the minimal domain types first if the model changes.
3. Implement the workflow in the responsible service, adapter, repository, or API layer.
4. Add or update tests close to the changed behavior.
5. Update the relevant docs in the same change.

## Documentation Suggestions

The documentation set should stay split by audience.

Recommended end-user documents:

- one concise manual for daily operation
- one troubleshooting page for common errors and health checks
- one release notes page that states what the product currently supports

Recommended contributor documents:

- coding standards
- architecture overview
- persistence and security rules
- procedure and transport rules
- API and deployment guide
- decision records for major architectural choices

## Suggested Documentation Additions

These would be useful next documents after the current pass:

- `docs/troubleshooting.md`: common API, auth, migration, and projection issues
- `docs/release-process.md`: versioning, migrations, verification, tagging, and rollout steps
- `docs/testing-strategy.md`: SQLite vs Postgres test responsibilities and required CI gates
- `docs/adr/`: short architecture decision records for major choices such as Postgres-first, private API boundary, audit model, and TI/KIM integration strategy

## Review Checklist

Before a change is merged, check:

- responsibilities are still separated cleanly
- names reflect the domain precisely
- new code has docstrings
- tests cover the changed behavior
- docs were updated where needed
- no raw SQL was added outside approved locations
- tenant and audit context are preserved
