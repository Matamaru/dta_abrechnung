from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..security import AuditContext
from .repositories import (
    SqlAlchemyAuditRepository,
    SqlAlchemyObjectStorageRefRepository,
    SqlAlchemyPlanningSnapshotRepository,
    SqlAlchemyProviderRepository,
    SqlAlchemyTenantRepository,
)
from .session import PersistenceRuntime, apply_audit_context


@dataclass(slots=True)
class SqlAlchemyUnitOfWork:
    runtime: PersistenceRuntime
    audit_context: AuditContext | None = None
    session: Session | None = None
    audit: SqlAlchemyAuditRepository | None = None
    tenants: SqlAlchemyTenantRepository | None = None
    providers: SqlAlchemyProviderRepository | None = None
    object_storage_refs: SqlAlchemyObjectStorageRefRepository | None = None
    planning_snapshots: SqlAlchemyPlanningSnapshotRepository | None = None

    def __enter__(self) -> "SqlAlchemyUnitOfWork":
        self.session = self.runtime.session_factory()
        if self.audit_context is not None:
            apply_audit_context(self.session, self.audit_context)
        self.audit = SqlAlchemyAuditRepository(self.session)
        self.tenants = SqlAlchemyTenantRepository(self.session, self.runtime.capabilities, self.audit)
        self.providers = SqlAlchemyProviderRepository(self.session, self.runtime.capabilities, self.audit)
        self.object_storage_refs = SqlAlchemyObjectStorageRefRepository(self.session, self.runtime.capabilities, self.audit)
        self.planning_snapshots = SqlAlchemyPlanningSnapshotRepository(self.session, self.runtime.capabilities, self.audit)
        return self

    def commit(self) -> None:
        if self.session is None:
            raise RuntimeError("UnitOfWork is not active")
        self.session.commit()

    def rollback(self) -> None:
        if self.session is None:
            return
        self.session.rollback()

    def __exit__(self, exc_type, _exc, _tb) -> None:
        if self.session is None:
            return
        if exc_type is not None:
            self.session.rollback()
        self.session.close()
