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
    _audit: SqlAlchemyAuditRepository | None = None
    _tenants: SqlAlchemyTenantRepository | None = None
    _providers: SqlAlchemyProviderRepository | None = None
    _object_storage_refs: SqlAlchemyObjectStorageRefRepository | None = None
    _planning_snapshots: SqlAlchemyPlanningSnapshotRepository | None = None

    def __enter__(self) -> "SqlAlchemyUnitOfWork":
        self.session = self.runtime.session_factory()
        if self.audit_context is not None:
            apply_audit_context(self.session, self.audit_context)
        self._audit = SqlAlchemyAuditRepository(self.session)
        self._tenants = SqlAlchemyTenantRepository(self.session, self.runtime.capabilities, self.audit)
        self._providers = SqlAlchemyProviderRepository(self.session, self.runtime.capabilities, self.audit)
        self._object_storage_refs = SqlAlchemyObjectStorageRefRepository(self.session, self.runtime.capabilities, self.audit)
        self._planning_snapshots = SqlAlchemyPlanningSnapshotRepository(self.session, self.runtime.capabilities, self.audit)
        return self

    def commit(self) -> None:
        if self.session is None:
            raise RuntimeError("UnitOfWork is not active")
        self.session.commit()

    def flush(self) -> None:
        if self.session is None:
            raise RuntimeError("UnitOfWork is not active")
        self.session.flush()

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
        self.session = None
        self._audit = None
        self._tenants = None
        self._providers = None
        self._object_storage_refs = None
        self._planning_snapshots = None

    @property
    def audit(self) -> SqlAlchemyAuditRepository:
        return self._require_repository(self._audit, "audit")

    @property
    def tenants(self) -> SqlAlchemyTenantRepository:
        return self._require_repository(self._tenants, "tenants")

    @property
    def providers(self) -> SqlAlchemyProviderRepository:
        return self._require_repository(self._providers, "providers")

    @property
    def object_storage_refs(self) -> SqlAlchemyObjectStorageRefRepository:
        return self._require_repository(self._object_storage_refs, "object_storage_refs")

    @property
    def planning_snapshots(self) -> SqlAlchemyPlanningSnapshotRepository:
        return self._require_repository(self._planning_snapshots, "planning_snapshots")

    @staticmethod
    def _require_repository(repository, name: str):
        if repository is None:
            raise RuntimeError(f"Repository '{name}' is not available outside an active unit of work")
        return repository
