from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from ..domain import InstitutionCode, Leistungserbringer, Mandant, TenantMode
from ..persistence import PersistenceRuntime, SqlAlchemyUnitOfWork
from ..planning import PlanningSnapshot
from ..security import AuditEventView, AuditOperation, PrincipalRole, SensitiveReadTarget
from ..storage import ObjectStore
from .auth import AuthContext
from .realtime import RealtimeBroker


@dataclass(slots=True, frozen=True)
class ProjectionFreshness:
    tenant_id: str
    hub_id: str | None
    snapshot_id: str
    extracted_at: datetime
    age_seconds: int


@dataclass(slots=True)
class ApiServices:
    primary_runtime: PersistenceRuntime
    projection_runtime: PersistenceRuntime
    object_store: ObjectStore
    realtime_broker: RealtimeBroker

    def create_tenant(self, name: str, mode: TenantMode, auth: AuthContext, reason: str | None, legal_basis: str | None) -> Mandant:
        tenant = Mandant(
            id=f"tenant-{uuid4().hex[:12]}",
            name=name,
            mode=mode,
            created_at=datetime.now(UTC),
        )
        audit_context = auth.to_audit_context(reason=reason, legal_basis=legal_basis, tenant_id=tenant.id)
        with SqlAlchemyUnitOfWork(self.primary_runtime, audit_context=audit_context) as uow:
            assert uow.tenants
            uow.tenants.add(tenant, audit_context)
            uow.commit()
        return tenant

    def list_tenants(self, auth: AuthContext) -> list[Mandant]:
        with SqlAlchemyUnitOfWork(self.primary_runtime, audit_context=auth.to_audit_context()) as uow:
            assert uow.tenants
            if auth.tenant_id and not auth.has_role(PrincipalRole.PLATFORM_ADMIN):
                return [tenant for tenant in uow.tenants.list(sort_field="name") if tenant.id == auth.tenant_id]
            return uow.tenants.list(sort_field="name")

    def get_tenant(self, tenant_id: str, auth: AuthContext) -> Mandant | None:
        with SqlAlchemyUnitOfWork(self.primary_runtime, audit_context=auth.to_audit_context(tenant_id=tenant_id)) as uow:
            assert uow.tenants
            return uow.tenants.get(tenant_id)

    def create_provider(
        self,
        tenant_id: str,
        name: str,
        ik: str,
        billing_ik: str | None,
        auth: AuthContext,
        reason: str | None,
        legal_basis: str | None,
    ) -> Leistungserbringer:
        provider = Leistungserbringer(
            id=f"provider-{uuid4().hex[:12]}",
            tenant_id=tenant_id,
            name=name,
            ik=InstitutionCode(ik),
            billing_ik=InstitutionCode(billing_ik) if billing_ik else None,
        )
        audit_context = auth.to_audit_context(reason=reason, legal_basis=legal_basis, tenant_id=tenant_id)
        with SqlAlchemyUnitOfWork(self.primary_runtime, audit_context=audit_context) as uow:
            assert uow.providers and uow.tenants
            if uow.tenants.get(tenant_id) is None:
                raise LookupError(f"Unknown tenant: {tenant_id}")
            uow.providers.add(provider, audit_context)
            uow.commit()
        return provider

    def get_provider(self, provider_id: str, auth: AuthContext) -> Leistungserbringer | None:
        with SqlAlchemyUnitOfWork(self.primary_runtime, audit_context=auth.to_audit_context()) as uow:
            assert uow.providers
            provider = uow.providers.get(provider_id, context=auth.to_audit_context(), sensitive=True)
            uow.commit()
            return provider

    def list_providers(self, tenant_id: str, auth: AuthContext) -> list[Leistungserbringer]:
        with SqlAlchemyUnitOfWork(self.primary_runtime, audit_context=auth.to_audit_context(tenant_id=tenant_id)) as uow:
            assert uow.providers
            return uow.providers.list_by_tenant(tenant_id, sort_field="name")

    async def store_planning_snapshot(
        self,
        tenant_id: str,
        hub_id: str | None,
        planning_date,
        mission_count: int,
        payload: dict[str, Any],
        source_job_id: str | None,
        auth: AuthContext,
        reason: str | None,
        legal_basis: str | None,
    ) -> PlanningSnapshot:
        snapshot_id = f"plan-{uuid4().hex[:12]}"
        object_ref_id = f"obj-{uuid4().hex[:12]}"
        serialized_payload = json.dumps(payload, separators=(",", ":"), sort_keys=True, default=str).encode("utf-8")
        object_key = f"{tenant_id}/planning/{planning_date.isoformat()}/{snapshot_id}.json"
        object_ref = self.object_store.put_blob(
            key=object_key,
            content=serialized_payload,
            media_type="application/json",
            retention_class="planning_projection",
            legal_hold=False,
        )
        snapshot = PlanningSnapshot(
            snapshot_id=snapshot_id,
            tenant_id=tenant_id,
            hub_id=hub_id,
            planning_date=planning_date,
            mission_count=mission_count,
            extracted_at=datetime.now(UTC),
            source_job_id=source_job_id,
            object_ref=object_ref,
        )
        audit_context = auth.to_audit_context(reason=reason, legal_basis=legal_basis, tenant_id=tenant_id)
        with SqlAlchemyUnitOfWork(self.primary_runtime, audit_context=audit_context) as uow:
            assert uow.object_storage_refs and uow.planning_snapshots
            uow.object_storage_refs.add(object_ref_id, tenant_id, object_ref, audit_context)
            uow.planning_snapshots.store_snapshot(snapshot, object_ref_id, audit_context)
            uow.commit()
        await self.realtime_broker.publish(
            self.realtime_broker.make_event(
                channel=self._planning_channel(tenant_id),
                event_type="planning.snapshot.stored",
                tenant_id=tenant_id,
                payload={
                    "snapshot_id": snapshot.snapshot_id,
                    "hub_id": snapshot.hub_id,
                    "planning_date": snapshot.planning_date.isoformat(),
                    "mission_count": snapshot.mission_count,
                    "source_job_id": snapshot.source_job_id,
                },
            )
        )
        return snapshot

    def latest_planning_snapshot(self, tenant_id: str, hub_id: str | None, auth: AuthContext) -> PlanningSnapshot | None:
        with SqlAlchemyUnitOfWork(self.projection_runtime, audit_context=None) as uow:
            assert uow.planning_snapshots
            snapshot = uow.planning_snapshots.latest_snapshot(tenant_id, hub_id=hub_id, context=None)
        if snapshot is None:
            return None
        audit_context = auth.to_audit_context(tenant_id=tenant_id)
        with SqlAlchemyUnitOfWork(self.primary_runtime, audit_context=audit_context) as uow:
            assert uow.audit
            uow.audit.record_sensitive_read("planning_snapshots", snapshot.snapshot_id, audit_context, SensitiveReadTarget.PII)
            uow.commit()
        return snapshot

    def list_planning_snapshots(
        self,
        tenant_id: str,
        hub_id: str | None,
        auth: AuthContext,
        limit: int = 50,
    ) -> list[PlanningSnapshot]:
        with SqlAlchemyUnitOfWork(self.projection_runtime, audit_context=None) as uow:
            assert uow.planning_snapshots
            snapshots = uow.planning_snapshots.list_for_tenant(tenant_id, hub_id=hub_id, limit=limit)
        return snapshots

    def projection_freshness(self, tenant_id: str, hub_id: str | None, auth: AuthContext) -> ProjectionFreshness | None:
        snapshot = self.latest_planning_snapshot(tenant_id, hub_id, auth)
        if snapshot is None:
            return None
        extracted_at = snapshot.extracted_at if snapshot.extracted_at.tzinfo is not None else snapshot.extracted_at.replace(tzinfo=UTC)
        age_seconds = max(0, int((datetime.now(UTC) - extracted_at).total_seconds()))
        return ProjectionFreshness(
            tenant_id=tenant_id,
            hub_id=hub_id,
            snapshot_id=snapshot.snapshot_id,
            extracted_at=extracted_at,
            age_seconds=age_seconds,
        )

    def list_audit_events(self, auth: AuthContext, tenant_id: str | None = None) -> list[AuditEventView]:
        scoped_tenant = tenant_id or auth.tenant_id
        with SqlAlchemyUnitOfWork(self.primary_runtime, audit_context=auth.to_audit_context(tenant_id=scoped_tenant)) as uow:
            assert uow.audit
            return uow.audit.list_events(tenant_id=scoped_tenant, sort_field="occurred_at", descending=True)

    def record_realtime_subscription(self, channel: str, auth: AuthContext) -> None:
        audit_context = auth.to_audit_context(tenant_id=auth.tenant_id)
        event = AuditEventView(
            event_id=f"audit-{uuid4().hex[:20]}",
            occurred_at=datetime.now(UTC),
            table_name="realtime_subscriptions",
            row_pk=channel,
            actor_id=audit_context.actor_id,
            actor_type=audit_context.actor_type,
            operation=AuditOperation.READ,
            request_id=audit_context.request_id,
            tenant_id=audit_context.tenant_id,
            reason="realtime subscription authorized",
            legal_basis=audit_context.legal_basis,
            changed_fields=("channel",),
            after_state={"channel": channel},
        )
        with SqlAlchemyUnitOfWork(self.primary_runtime, audit_context=audit_context) as uow:
            assert uow.audit
            uow.audit.record_event(event)
            uow.commit()

    def check_database(self, runtime: PersistenceRuntime) -> dict[str, object]:
        with runtime.engine.connect() as connection:
            probe = connection.exec_driver_sql("SELECT 1").scalar_one()
        return {
            "ok": probe == 1,
            "profile": runtime.settings.profile.value,
            "role": runtime.settings.role.value,
            "application_name": runtime.settings.application_name,
            "dialect": runtime.settings.dialect,
        }

    @staticmethod
    def _planning_channel(tenant_id: str) -> str:
        return f"planning:{tenant_id}"
