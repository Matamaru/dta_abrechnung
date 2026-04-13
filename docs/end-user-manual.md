# End-User Manual

This manual is for operators who use the current platform foundation. At the moment, the user-facing surface is the private API and its Swagger documentation, not a finished business UI.

## What The System Currently Does

The current version supports these operational basics:

- check application and database health
- create tenants
- create providers inside a tenant
- store planning snapshots
- read the latest planning snapshots
- inspect audit events with the correct roles
- receive realtime planning snapshot events

The current version does not yet provide a full end-user workflow for complete `SGB V` and `SGB XI` billing through a browser interface.

## Before You Start

You need:

- a running API service
- a valid access token
- the correct tenant-bound role for your work

Useful URLs in a local setup:

- `/api/docs`: interactive Swagger UI
- `/api/openapi.json`: machine-readable API description
- `/api/v1/health/live`: liveness check

## Common Roles

- `platform_admin`: can create tenants and inspect the full system
- `tenant_admin`: can work inside one tenant
- `billing_operator`: can create providers and planning snapshots inside one tenant
- `auditor`: can inspect audit events within the allowed scope

## Daily Tasks

### 1. Check system health

Use these endpoints first:

- `GET /api/v1/health/live`
- `GET /api/v1/health/primary-db`
- `GET /api/v1/health/read-replica`
- `GET /api/v1/health/projections?tenant_id=...`

If the database or projection health is not `ok`, stop normal work and check the operator logs before entering new operational data.

### 2. Create a tenant

Use:

- `POST /api/v1/tenants`

Provide:

- `name`
- `mode`
- optional `reason`
- optional `legal_basis`

This step needs a `platform_admin` token.

### 3. Create a provider

Use:

- `POST /api/v1/providers`

Provide:

- `tenant_id`
- `name`
- `ik`
- optional `billing_ik`
- optional `reason`
- optional `legal_basis`

Use `GET /api/v1/tenants/{tenant_id}/providers` to verify the result.

### 4. Store a planning snapshot

Use:

- `POST /api/v1/planning/snapshots`

Provide:

- `tenant_id`
- optional `hub_id`
- `planning_date`
- `mission_count`
- optional `source_job_id`
- `payload`

This is used to persist a planning result or operational extract so it can be queried later and inspected through audit trails.

### 5. Read planning data

Use:

- `GET /api/v1/planning/snapshots/latest`
- `GET /api/v1/planning/snapshots`

Use the tenant and optional hub filters to narrow the result.

### 6. Inspect audit history

Use:

- `GET /api/v1/audit/events`

Audit history helps answer:

- who created or read a record
- when a change happened
- which fields changed
- which request triggered the change

## Realtime Planning Updates

Clients can subscribe to:

- `WS /api/v1/realtime/planning?tenant_id=...&token=...`

After subscription, the client receives:

- `subscription.ready`
- `planning.snapshot.stored`

Use this channel for dashboards or operator consoles that need near-realtime planning updates.

## Good Operating Practice

- always work with the correct tenant-scoped token
- record a `reason` when the action is operationally important
- check health endpoints before larger imports or planning jobs
- use audit events to verify what happened before retrying a failed operation

## Current Limits

This version is still a platform foundation. It does not yet provide:

- a complete business UI
- full invoice creation and submission through the API
- final production integrations for TI/KIM or Dakota
- complete legal payload conformance for all `SGB V` and `SGB XI` procedures

If you need those capabilities, use this manual as the foundation manual for the current API stage, not as a full production operations handbook.
