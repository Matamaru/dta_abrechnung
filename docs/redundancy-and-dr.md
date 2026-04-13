# Redundancy And Disaster Recovery

## Default Database Strategy

The default strategy is `HA Postgres`, not distributed SQL.

Target topology:

- one writable primary
- two or more hot standbys in different availability zones/datacenters
- automatic failover for single-AZ/datacenter loss
- synchronous durability for critical writes
- asynchronous replicas for read scaling where appropriate
- private API services pointed at the primary for commands and at the replica runtime for projection-heavy reads where configured

## Backup And Recovery

The architecture targets:

- continuous WAL archiving
- point-in-time recovery
- encrypted immutable backups
- Germany/EU-only residency
- minutes-level RPO/RTO for the transactional core

Backups and evidence storage should live in separate failure domains where possible.

## Planning And Scale

Heavy care-ops planning workloads should not push the transactional OLTP database toward a distributed-SQL-first design.

Instead:

- keep Postgres as system of record
- use read replicas and planning projections for heavy reads
- use an async planning/optimization service for route and tour computation
- partition high-volume operational tables once those models are introduced

## Operational Expectations

Production operations should include:

- replica lag monitoring
- backup success/failure alerts
- restore drills
- failover drills
- evidence/object-store recovery checks
- audit trigger health checks

Automatic region failover is not a v1 assumption. Regional disaster recovery should be controlled/manual inside Germany/EU boundaries.
