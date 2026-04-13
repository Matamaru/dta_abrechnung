from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Select, asc, desc, select
from sqlalchemy.orm import Session

from ..domain import InstitutionCode, Leistungserbringer, Mandant, TenantMode
from ..planning import PlanningSnapshot
from ..runtime import BackendCapabilities
from ..security import AuditContext, AuditEventView, AuditOperation, SensitiveReadTarget, normalize_for_json, require_audit_context
from ..storage import ObjectStorageRef
from .models import AuditLedgerModel, ObjectStorageRefModel, PlanningSnapshotModel, ProviderModel, TenantModel


def _sort_expression(allowed: dict[str, Any], sort_field: str, descending: bool):
    try:
        column = allowed[sort_field]
    except KeyError as exc:
        raise ValueError(f"Unsupported sort field: {sort_field}") from exc
    return desc(column) if descending else asc(column)


def _tenant_from_row(row: TenantModel) -> Mandant:
    return Mandant(id=row.id, name=row.name, mode=TenantMode(row.mode), created_at=row.created_at)


def _provider_from_row(row: ProviderModel) -> Leistungserbringer:
    return Leistungserbringer(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        ik=InstitutionCode(row.ik),
        billing_ik=InstitutionCode(row.billing_ik) if row.billing_ik else None,
    )


def _object_storage_ref_from_row(row: ObjectStorageRefModel) -> ObjectStorageRef:
    return ObjectStorageRef(
        bucket=row.bucket,
        key=row.object_key,
        checksum_sha256=row.checksum_sha256,
        size_bytes=row.size_bytes,
        media_type=row.media_type,
        encryption_key_id=row.encryption_key_id,
        retention_class=row.retention_class,
        legal_hold=row.legal_hold,
        immutable=row.immutable,
        residency=row.residency,
        version_id=row.version_id,
        created_at=row.created_at,
    )


def _planning_snapshot_from_row(row: PlanningSnapshotModel) -> PlanningSnapshot:
    return PlanningSnapshot(
        snapshot_id=row.snapshot_id,
        tenant_id=row.tenant_id,
        hub_id=row.hub_id,
        planning_date=row.planning_date,
        mission_count=row.mission_count,
        extracted_at=row.extracted_at,
        source_job_id=row.source_job_id,
    )


class SqlAlchemyAuditRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def record_event(self, event: AuditEventView) -> AuditEventView:
        record = AuditLedgerModel(
            event_id=event.event_id,
            occurred_at=event.occurred_at,
            table_name=event.table_name,
            row_pk=event.row_pk,
            actor_id=event.actor_id,
            actor_type=event.actor_type,
            operation=event.operation,
            request_id=event.request_id,
            tenant_id=event.tenant_id,
            reason=event.reason,
            legal_basis=event.legal_basis,
            changed_fields=list(event.changed_fields),
            before_state=event.before_state,
            after_state=event.after_state,
            sensitive_read_target=event.sensitive_read_target,
        )
        self.session.add(record)
        return event

    def record_sensitive_read(
        self,
        table_name: str,
        row_pk: str,
        context: AuditContext,
        target: SensitiveReadTarget,
    ) -> AuditEventView:
        ctx = require_audit_context(context)
        event = AuditEventView(
            event_id=f"audit-{uuid4().hex[:20]}",
            occurred_at=datetime.now(UTC),
            table_name=table_name,
            row_pk=row_pk,
            actor_id=ctx.actor_id,
            actor_type=ctx.actor_type,
            operation=AuditOperation.READ,
            request_id=ctx.request_id,
            tenant_id=ctx.tenant_id,
            reason=ctx.reason,
            legal_basis=ctx.legal_basis,
            sensitive_read_target=target,
        )
        return self.record_event(event)

    def list_events(self, tenant_id: str | None = None, sort_field: str = "occurred_at", descending: bool = False) -> list[AuditEventView]:
        allowed = {
            "occurred_at": AuditLedgerModel.occurred_at,
            "table_name": AuditLedgerModel.table_name,
            "operation": AuditLedgerModel.operation,
        }
        stmt: Select[Any] = select(AuditLedgerModel)
        if tenant_id is not None:
            stmt = stmt.where(AuditLedgerModel.tenant_id == tenant_id)
        stmt = stmt.order_by(_sort_expression(allowed, sort_field, descending))
        rows = self.session.execute(stmt).scalars().all()
        return [
            AuditEventView(
                event_id=row.event_id,
                occurred_at=row.occurred_at,
                table_name=row.table_name,
                row_pk=row.row_pk,
                actor_id=row.actor_id,
                actor_type=row.actor_type,
                operation=row.operation,
                request_id=row.request_id,
                tenant_id=row.tenant_id,
                reason=row.reason,
                legal_basis=row.legal_basis,
                changed_fields=tuple(row.changed_fields or []),
                before_state=row.before_state,
                after_state=row.after_state,
                sensitive_read_target=row.sensitive_read_target,
            )
            for row in rows
        ]


class SqlAlchemyTenantRepository:
    def __init__(self, session: Session, capabilities: BackendCapabilities, audit: SqlAlchemyAuditRepository) -> None:
        self.session = session
        self.capabilities = capabilities
        self.audit = audit

    def add(self, tenant: Mandant, context: AuditContext) -> Mandant:
        ctx = require_audit_context(context)
        record = TenantModel(id=tenant.id, name=tenant.name, mode=tenant.mode.value, created_at=tenant.created_at)
        self.session.add(record)
        self.session.flush()
        if not self.capabilities.supports_trigger_audit:
            after = normalize_for_json(asdict(tenant))
            self.audit.record_event(
                AuditEventView(
                    event_id=f"audit-{uuid4().hex[:20]}",
                    occurred_at=datetime.now(UTC),
                    table_name=TenantModel.__tablename__,
                    row_pk=tenant.id,
                    actor_id=ctx.actor_id,
                    actor_type=ctx.actor_type,
                    operation=AuditOperation.INSERT,
                    request_id=ctx.request_id,
                    tenant_id=tenant.id,
                    reason=ctx.reason,
                    legal_basis=ctx.legal_basis,
                    changed_fields=tuple(sorted(after.keys())),
                    before_state=None,
                    after_state=after,
                )
            )
        return tenant

    def get(self, tenant_id: str) -> Mandant | None:
        row = self.session.get(TenantModel, tenant_id)
        if row is None:
            return None
        return _tenant_from_row(row)

    def list(self, sort_field: str = "created_at", descending: bool = False) -> list[Mandant]:
        allowed = {
            "created_at": TenantModel.created_at,
            "name": TenantModel.name,
        }
        stmt = select(TenantModel).order_by(_sort_expression(allowed, sort_field, descending))
        rows = self.session.execute(stmt).scalars().all()
        return [_tenant_from_row(row) for row in rows]


class SqlAlchemyProviderRepository:
    def __init__(self, session: Session, capabilities: BackendCapabilities, audit: SqlAlchemyAuditRepository) -> None:
        self.session = session
        self.capabilities = capabilities
        self.audit = audit

    def add(self, provider: Leistungserbringer, context: AuditContext) -> Leistungserbringer:
        ctx = require_audit_context(context)
        record = ProviderModel(
            id=provider.id,
            tenant_id=provider.tenant_id,
            name=provider.name,
            ik=provider.ik.value,
            billing_ik=provider.billing_ik.value if provider.billing_ik else None,
        )
        self.session.add(record)
        self.session.flush()
        if not self.capabilities.supports_trigger_audit:
            after = normalize_for_json(
                {
                    "id": provider.id,
                    "tenant_id": provider.tenant_id,
                    "name": provider.name,
                    "ik": provider.ik.value,
                    "billing_ik": provider.billing_ik.value if provider.billing_ik else None,
                }
            )
            self.audit.record_event(
                AuditEventView(
                    event_id=f"audit-{uuid4().hex[:20]}",
                    occurred_at=datetime.now(UTC),
                    table_name=ProviderModel.__tablename__,
                    row_pk=provider.id,
                    actor_id=ctx.actor_id,
                    actor_type=ctx.actor_type,
                    operation=AuditOperation.INSERT,
                    request_id=ctx.request_id,
                    tenant_id=provider.tenant_id,
                    reason=ctx.reason,
                    legal_basis=ctx.legal_basis,
                    changed_fields=tuple(sorted(after.keys())),
                    before_state=None,
                    after_state=after,
                )
            )
        return provider

    def get(self, provider_id: str, context: AuditContext | None = None, sensitive: bool = False) -> Leistungserbringer | None:
        row = self.session.get(ProviderModel, provider_id)
        if row is None:
            return None
        if sensitive and context is not None:
            self.audit.record_sensitive_read(ProviderModel.__tablename__, provider_id, context, SensitiveReadTarget.PII)
        return _provider_from_row(row)

    def list_by_tenant(self, tenant_id: str, sort_field: str = "name", descending: bool = False) -> list[Leistungserbringer]:
        allowed = {
            "name": ProviderModel.name,
            "id": ProviderModel.id,
        }
        stmt = (
            select(ProviderModel)
            .where(ProviderModel.tenant_id == tenant_id)
            .order_by(_sort_expression(allowed, sort_field, descending))
        )
        rows = self.session.execute(stmt).scalars().all()
        return [_provider_from_row(row) for row in rows]


class SqlAlchemyObjectStorageRefRepository:
    def __init__(self, session: Session, capabilities: BackendCapabilities, audit: SqlAlchemyAuditRepository) -> None:
        self.session = session
        self.capabilities = capabilities
        self.audit = audit

    def add(self, ref_id: str, tenant_id: str | None, ref: ObjectStorageRef, context: AuditContext) -> ObjectStorageRef:
        ctx = require_audit_context(context)
        record = ObjectStorageRefModel(
            id=ref_id,
            tenant_id=tenant_id,
            bucket=ref.bucket,
            object_key=ref.key,
            checksum_sha256=ref.checksum_sha256,
            size_bytes=ref.size_bytes,
            media_type=ref.media_type,
            encryption_key_id=ref.encryption_key_id,
            retention_class=ref.retention_class,
            legal_hold=ref.legal_hold,
            immutable=ref.immutable,
            residency=ref.residency,
            version_id=ref.version_id,
            created_at=ref.created_at or datetime.now(UTC),
        )
        self.session.add(record)
        self.session.flush()
        if not self.capabilities.supports_trigger_audit:
            after = normalize_for_json(
                {
                    "id": ref_id,
                    "tenant_id": tenant_id,
                    "bucket": ref.bucket,
                    "object_key": ref.key,
                    "checksum_sha256": ref.checksum_sha256,
                    "retention_class": ref.retention_class,
                    "legal_hold": ref.legal_hold,
                    "immutable": ref.immutable,
                }
            )
            self.audit.record_event(
                AuditEventView(
                    event_id=f"audit-{uuid4().hex[:20]}",
                    occurred_at=datetime.now(UTC),
                    table_name=ObjectStorageRefModel.__tablename__,
                    row_pk=ref_id,
                    actor_id=ctx.actor_id,
                    actor_type=ctx.actor_type,
                    operation=AuditOperation.INSERT,
                    request_id=ctx.request_id,
                    tenant_id=tenant_id,
                    reason=ctx.reason,
                    legal_basis=ctx.legal_basis,
                    changed_fields=tuple(sorted(after.keys())),
                    before_state=None,
                    after_state=after,
                )
            )
        return ref

    def get(self, ref_id: str, context: AuditContext | None = None, sensitive: bool = False) -> ObjectStorageRef | None:
        row = self.session.get(ObjectStorageRefModel, ref_id)
        if row is None:
            return None
        if sensitive and context is not None:
            self.audit.record_sensitive_read(ObjectStorageRefModel.__tablename__, ref_id, context, SensitiveReadTarget.EVIDENCE)
        return _object_storage_ref_from_row(row)


class SqlAlchemyPlanningSnapshotRepository:
    def __init__(self, session: Session, capabilities: BackendCapabilities, audit: SqlAlchemyAuditRepository) -> None:
        self.session = session
        self.capabilities = capabilities
        self.audit = audit

    def store_snapshot(self, snapshot: PlanningSnapshot, object_storage_ref_id: str | None, context: AuditContext) -> PlanningSnapshot:
        ctx = require_audit_context(context)
        record = PlanningSnapshotModel(
            snapshot_id=snapshot.snapshot_id,
            tenant_id=snapshot.tenant_id,
            hub_id=snapshot.hub_id,
            planning_date=snapshot.planning_date,
            mission_count=snapshot.mission_count,
            extracted_at=snapshot.extracted_at,
            source_job_id=snapshot.source_job_id,
            object_storage_ref_id=object_storage_ref_id,
        )
        self.session.add(record)
        self.session.flush()
        if not self.capabilities.supports_trigger_audit:
            after = normalize_for_json(
                {
                    "snapshot_id": snapshot.snapshot_id,
                    "tenant_id": snapshot.tenant_id,
                    "hub_id": snapshot.hub_id,
                    "planning_date": snapshot.planning_date.isoformat(),
                    "mission_count": snapshot.mission_count,
                }
            )
            self.audit.record_event(
                AuditEventView(
                    event_id=f"audit-{uuid4().hex[:20]}",
                    occurred_at=datetime.now(UTC),
                    table_name=PlanningSnapshotModel.__tablename__,
                    row_pk=snapshot.snapshot_id,
                    actor_id=ctx.actor_id,
                    actor_type=ctx.actor_type,
                    operation=AuditOperation.INSERT,
                    request_id=ctx.request_id,
                    tenant_id=snapshot.tenant_id,
                    reason=ctx.reason,
                    legal_basis=ctx.legal_basis,
                    changed_fields=tuple(sorted(after.keys())),
                    before_state=None,
                    after_state=after,
                )
            )
        return snapshot

    def latest_snapshot(self, tenant_id: str, hub_id: str | None = None, context: AuditContext | None = None) -> PlanningSnapshot | None:
        stmt = select(PlanningSnapshotModel).where(PlanningSnapshotModel.tenant_id == tenant_id)
        if hub_id is not None:
            stmt = stmt.where(PlanningSnapshotModel.hub_id == hub_id)
        stmt = stmt.order_by(desc(PlanningSnapshotModel.extracted_at))
        row = self.session.execute(stmt).scalars().first()
        if row is None:
            return None
        if context is not None:
            self.audit.record_sensitive_read(PlanningSnapshotModel.__tablename__, row.snapshot_id, context, SensitiveReadTarget.PII)
        return _planning_snapshot_from_row(row)

    def list_for_tenant(
        self,
        tenant_id: str,
        hub_id: str | None = None,
        limit: int = 50,
        sort_field: str = "extracted_at",
        descending: bool = True,
    ) -> list[PlanningSnapshot]:
        allowed = {
            "extracted_at": PlanningSnapshotModel.extracted_at,
            "planning_date": PlanningSnapshotModel.planning_date,
            "mission_count": PlanningSnapshotModel.mission_count,
        }
        stmt = select(PlanningSnapshotModel).where(PlanningSnapshotModel.tenant_id == tenant_id)
        if hub_id is not None:
            stmt = stmt.where(PlanningSnapshotModel.hub_id == hub_id)
        stmt = stmt.order_by(_sort_expression(allowed, sort_field, descending)).limit(limit)
        rows = self.session.execute(stmt).scalars().all()
        return [_planning_snapshot_from_row(row) for row in rows]
