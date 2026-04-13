# Domain Model

## Core Actors

- `Mandant`: tenant boundary for either a self-biller or a billing center
- `Abrechnungszentrum`: centralized billing operator inside a billing-center tenant
- `Leistungserbringer`: provider billed under its own `IK` or a delegated billing `IK`
- `Kostentraeger`: payer with transport and procedure capability metadata
- `Vertrag`: billing contract between provider and payer for one procedure and version

## Clinical And Operational Source Data

- `Verordnung`: billing-relevant prescription or authorization reference
- `Leistungsnachweis`: captured service instance with patient, date, quantity, and evidence links
- `EvidenceDocument`: binary evidence such as scanned proofs, PDFs, or electronic signatures

## Billing And Reconciliation

- `Abrechnungsfall`: patient-centric grouping of services within an invoice
- `Rechnung`: generated invoice with message version, line items, and correction metadata
- `Korrektur`: explicit link between a replacement invoice and the original invoice
- `Fehlernachricht`: stored technical or fachliche inbound error
- `Zahlung`: posted payment record
- `OffenerPosten`: invoice-level receivable with payment status

## Submission Layer

- `ProcedureCapability`: procedure-specific payer capability, route, and transport flags
- `RoutingTarget`: resolved receiver endpoint for one transport family
- `SubmissionArtifact`: file or binary payload ready for transport
- `SubmissionEnvelope`: grouped transport package
- `SubmissionJob`: tracked outbound submission
- `InboundEvent`: normalized inbound status event

## Persistence, Audit, And Storage

- `DatabaseProfile`: database runtime mode such as local SQLite or production Postgres
- `DurabilityClass`: indicates whether an operation requires strong synchronous durability
- `AuditContext`: actor and request metadata required for writes and sensitive reads
- `AuditEventView`: normalized audit event returned by the persistence layer
- `ObjectStorageRef`: metadata pointer to encrypted object-storage content
- `BackupPolicy`: retention and immutability policy for backups
- `RecoveryPolicy`: target recovery expectations for failover and restore
- `PlanningSnapshot`: persisted planning/read-model extract for heavy optimization workloads

## Current Modeling Boundaries

The current model is intentionally broad enough to support:

- self-billers and billing centers
- classic DTA and TI/KIM submissions
- mixed electronic and scan-based evidence
- invoice corrections and basic reconciliation
- SQL-backed runtime and audit foundations
- local SQLite testing and Postgres production profiles

The model does not yet encode every production concern, for example:

- full user identities and permissions workflow
- payer-specific deep validation catalogs
- persistent version history for master data snapshots
- real-world scheduling, care documentation, or ERP ledger models
- all high-volume operational entities for hubs, tours, missions, and rostering
