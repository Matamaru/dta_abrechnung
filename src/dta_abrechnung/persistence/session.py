from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from ..runtime import BackendCapabilities, DatabaseSettings, capabilities_for_profile
from ..security import AuditContext
from .base import Base


@dataclass(slots=True, frozen=True)
class PersistenceRuntime:
    settings: DatabaseSettings
    capabilities: BackendCapabilities
    engine: Engine
    session_factory: Callable[[], Session]


def build_engine(settings: DatabaseSettings) -> Engine:
    settings.validate()
    connect_args: dict[str, object] = {}
    if settings.is_sqlite:
        connect_args["check_same_thread"] = False
    elif settings.is_postgres:
        connect_args["application_name"] = settings.application_name
    engine = create_engine(
        settings.url,
        echo=settings.echo_sql,
        future=True,
        pool_pre_ping=not settings.is_sqlite,
        connect_args=connect_args,
    )
    if settings.is_sqlite:
        _enable_sqlite_pragmas(engine)
    return engine


def build_runtime(settings: DatabaseSettings) -> PersistenceRuntime:
    engine = build_engine(settings)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)
    return PersistenceRuntime(
        settings=settings,
        capabilities=capabilities_for_profile(settings.profile),
        engine=engine,
        session_factory=factory,
    )


def create_schema(engine: Engine) -> None:
    Base.metadata.create_all(engine)


def drop_schema(engine: Engine) -> None:
    Base.metadata.drop_all(engine)


def apply_audit_context(session: Session, context: AuditContext) -> None:
    bind = session.get_bind()
    if bind is None or bind.dialect.name != "postgresql":
        return
    pairs = {
        "app.audit.actor_id": context.actor_id,
        "app.audit.actor_type": context.actor_type.value,
        "app.audit.request_id": context.request_id,
        "app.audit.reason": context.reason or "",
        "app.audit.legal_basis": context.legal_basis or "",
        "app.current_tenant": context.tenant_id or "",
    }
    for key, value in pairs.items():
        session.execute(text("SELECT set_config(:key, :value, true)"), {"key": key, "value": value})


def _enable_sqlite_pragmas(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
