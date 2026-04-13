# Getting Started

## Local Prerequisites

- `Python 3.12`
- local `Postgres` for the main development path
- `.venv` virtual environment
- `.env` file with local secrets and connection settings

`SQLite` is supported only for unit tests and local developer workflows. It is not a production fallback.

## Environment File

Start from [.env.example](../.env.example) and create a local `.env`.

Important variables:

- `DTA_DATABASE_URL`
- `DTA_READ_REPLICA_URL`
- `DTA_OBJECT_STORAGE_ROOT`
- `DTA_JWT_SIGNING_KEY`
- `DTA_API_BASE_URL`
- `DTA_API_PRIVATE_BASE_URL`

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Database Bootstrap

Apply the Alembic schema to the configured database:

```bash
source .venv/bin/activate
PYTHONPATH=src .venv/bin/alembic upgrade head
```

This creates the current persistence foundation:

- tenants
- providers
- object storage references
- planning snapshots
- audit ledger
- runtime profile metadata
- submission artifact metadata
- billing facts

## Run The API

```bash
source .venv/bin/activate
PYTHONPATH=src uvicorn dta_abrechnung.api.app:create_default_app --factory --host 127.0.0.1 --port 8000
```

Key URLs:

- `http://127.0.0.1:8000/api/docs`
- `http://127.0.0.1:8000/api/openapi.json`
- `http://127.0.0.1:8000/api/v1/health/live`

## Test Commands

Full suite:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Syntax check:

```bash
.venv/bin/python -m py_compile src/dta_abrechnung/*.py src/dta_abrechnung/api/*.py src/dta_abrechnung/persistence/*.py tests/*.py
```

## Local Development Notes

- The API reads settings from `.env` through `ApplicationSettings.from_env()`.
- The default local object store is an immutable folder under `.local-object-store/`.
- JWT handling is local and intentionally simple at this stage; it is a private API boundary, not a finished identity platform.
- Billing workflows in `platform.py` still use the in-memory scaffold while the SQL-backed foundation grows underneath.
