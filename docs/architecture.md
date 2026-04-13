# Architecture

## System Shape

The software is intentionally split into shared platform services, procedure-specific billing adapters, persistence infrastructure, and a private API boundary.

Shared services:

- `CareOpsService`: captures operational source data such as prescriptions, services, and evidence references
- `BillingEngine`: groups services into invoices, creates billing cases, and tracks correction chains
- `PayerMasterDataService`: stores payer routing and capability metadata
- `EvidenceService`: bundles invoice-linked documents for submission
- `InboundProcessingService`: normalizes acknowledgements and errors into workflow events
- `AccountingExportService`: tracks payments and exports open items
- `NationalDtaPlatform`: orchestrates the end-to-end workflow

Infrastructure services:

- runtime profiles and capability flags in `runtime.py`
- actor/audit primitives in `security.py`
- object-storage abstractions in `storage.py`
- planning snapshot interfaces in `planning.py`
- private API, JWT auth, and realtime broker under `api/`
- SQLAlchemy persistence runtime, repositories, and unit of work under `persistence/`

Procedure-specific services:

- `PflegeProcedureAdapter`: hybrid support for classic DTA and TI/KIM
- `HkpProcedureAdapter`: TI/KIM-first serializer and inbound parser
- `Classic302ProcedureAdapter`: classic-first adapter used for Haushaltshilfe, Heilmittel, Hilfsmittel, and Krankentransport

Transport services:

- `ClassicDtaTransportAdapter`: packages main payload plus `Auftragsdatei` and evidence artifacts
- `TiKimTransportAdapter`: builds KIM messages with signatures and service identifiers
- `ExternalTiBridge` and `NativeTiBridge`: pluggable bridge layer for different TI operating models

Persistence services:

- `PersistenceRuntime`: engine/session bootstrap around a validated database profile
- `SqlAlchemyUnitOfWork`: transaction boundary for SQL-backed operations
- repository implementations for tenants, providers, object storage references, planning snapshots, and audit events
- Alembic migration scaffolding for schema management

API services:

- `create_app()` / `create_default_app()`: FastAPI application factory
- `JwtCodec`: local JWT issue/verify helper for the private API
- `ApiServices`: API-facing service layer for tenant/provider commands, planning snapshot persistence, projection reads, and audit queries
- `RealtimeBroker`: async broker for planning websocket updates

## Execution Flow

1. Source data is captured through care operations services.
2. Billing rules resolve prices and aggregate services into an invoice and billing cases.
3. The platform selects a compatible transport based on the contract and procedure adapter.
4. The procedure adapter validates the invoice and serializes the fachliche payload.
5. Evidence is packaged and routed through either classic DTA or TI/KIM transport.
6. Submission jobs are recorded with tracking references.
7. Inbound messages update submission status and create normalized error or acknowledgement events.
8. Payments update open items and can be exported for downstream accounting.

Persistence-enabled flows add:

1. validate runtime profile and backend capabilities
2. store relational state in SQLAlchemy-backed repositories
3. keep binary evidence/artifacts outside the main database via object-storage references
4. record write audit and sensitive-read audit
5. expose task-focused operations only through the private API boundary
6. route heavy planning/projection reads through the projection runtime

## Deployment Model

The intended deployment model is hybrid:

- cloud-hosted core application and business logic
- private REST API inside the application network/VPC
- managed Postgres primary plus optional read replica
- customer-side or controlled-edge components where TI/KIM, local connector access, scanning, or document capture require it

The current codebase now has a persistence foundation and private API surface, but it still does not yet implement:

- a full migration of business workflows from in-memory services to repositories
- full user lifecycle management or external SSO/OIDC
- real KIM/TI integration
- real Dakota integration
- production-grade Postgres operations, backups, and failover automation inside the repo

## Near-Term Architecture Direction

The intended next moves are:

- push more business workflows behind SQL-backed repositories
- widen the private API to billing, submission, and inbound flows
- add multi-hub, multi-org-unit, and planning-heavy operational models
- keep heavy planning reads and optimization outside the hot OLTP write path

## Extension Strategy

When extending the system:

- add new procedures by implementing or specializing procedure adapters
- add new transport rules by extending transport adapters or TI bridge abstractions
- keep payer-specific quirks in master data or adapter-level logic
- avoid coupling the platform facade to one billing lane or one transport family
- keep application SQL inside repositories and SQLAlchemy models
- use raw SQL only for migrations, triggers, and reviewed Postgres-only setup
