# Persistence And Security

## Runtime Profiles

The codebase now distinguishes database runtime profiles explicitly:

- `local_sqlite`: allowed only for local development and unit tests
- `prod_postgres`: writable production/staging transactional database
- `postgres_read_replica`: read-oriented replica profile

`SQLite` is not a deployed fallback. The runtime layer rejects SQLite in production-like environments.

On top of database settings, the API now loads an `ApplicationSettings` bundle with:

- primary database
- optional read replica
- object storage
- KMS key id
- JWT issuer/audience/signing key
- public/private API URLs

## Persistence Foundation

The SQLAlchemy persistence layer lives under `src/dta_abrechnung/persistence/` and currently provides:

- engine/session bootstrap
- backend capability flags
- repository pattern for selected aggregates
- a transaction-scoped unit of work
- Alembic migration scaffolding

The persistence layer is the foundation for replacing direct in-memory access over time. The current billing services still operate on the in-memory scaffold, while the new persistence modules establish the production direction.

## Audit Model

Auditability is split into two parts:

- write audit
  - SQLite/local mode records audit rows in application code
  - Postgres is prepared for trigger-backed audit through migration DDL
- sensitive read audit
  - PII reads
  - evidence metadata access
  - audit export access

Every audited action is expected to carry an `AuditContext` with:

- actor ID
- actor type
- tenant ID where applicable
- request ID
- source system
- optional reason/legal basis

The private API builds this context from JWT-authenticated requests and explicit request data. Realtime subscription authorization is also written into the audit ledger.

## API Security Boundary

The new FastAPI layer is a private application boundary:

- clients authenticate with JWT bearer tokens
- role checks happen before tenant-scoped commands/queries
- normal clients never receive database credentials
- handlers call service/repository code only; they do not build SQL
- planning websocket access is tenant-scoped and audited

## Query Safety

Application data access must use:

- `SQLAlchemy ORM/Core`
- bound parameters
- whitelisted dynamic sort/filter fields

Application code must not build SQL strings from user input.

## Object Storage

Binary evidence and generated artifacts belong in object storage, not the main database.

The repo now includes:

- `ObjectStorageRef`
- `BackupPolicy`
- `RecoveryPolicy`
- `LocalObjectStore` for local development/tests

Production object storage is expected to be:

- encrypted
- immutable/versioned for backups where required
- residency-constrained to Germany/EU
- integrated with KMS-managed keys
