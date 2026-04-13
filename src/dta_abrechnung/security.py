from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any


class ActorType(StrEnum):
    USER = "user"
    SERVICE = "service"
    SYSTEM = "system"


class AuditOperation(StrEnum):
    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"
    READ = "read"
    EXPORT = "export"


class SensitiveReadTarget(StrEnum):
    PII = "pii"
    EVIDENCE = "evidence"
    AUDIT_EXPORT = "audit_export"


class PrincipalRole(StrEnum):
    PLATFORM_ADMIN = "platform_admin"
    TENANT_ADMIN = "tenant_admin"
    BILLING_OPERATOR = "billing_operator"
    AUDITOR = "auditor"
    SERVICE_PRINCIPAL = "service_principal"


@dataclass(slots=True, frozen=True)
class AuditContext:
    actor_id: str
    actor_type: ActorType
    request_id: str
    source_system: str
    tenant_id: str | None = None
    reason: str | None = None
    legal_basis: str | None = None


@dataclass(slots=True, frozen=True)
class User:
    id: str
    email: str
    active: bool = True


@dataclass(slots=True, frozen=True)
class RoleBinding:
    actor_id: str
    role: PrincipalRole
    tenant_id: str | None = None


@dataclass(slots=True, frozen=True)
class ServicePrincipal:
    id: str
    display_name: str
    active: bool = True


@dataclass(slots=True, frozen=True)
class AuditEventView:
    event_id: str
    occurred_at: datetime
    table_name: str
    row_pk: str
    actor_id: str
    actor_type: ActorType
    operation: AuditOperation
    request_id: str
    tenant_id: str | None = None
    reason: str | None = None
    legal_basis: str | None = None
    changed_fields: tuple[str, ...] = ()
    before_state: dict[str, Any] | None = None
    after_state: dict[str, Any] | None = None
    sensitive_read_target: SensitiveReadTarget | None = None


def require_audit_context(context: AuditContext | None) -> AuditContext:
    if context is None:
        raise ValueError("AuditContext is required for this operation")
    return context


def normalize_for_json(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, dict):
        return {str(key): normalize_for_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [normalize_for_json(item) for item in value]
    return value


def diff_state(before_state: dict[str, Any] | None, after_state: dict[str, Any] | None) -> tuple[str, ...]:
    before_state = before_state or {}
    after_state = after_state or {}
    changed = {
        key
        for key in set(before_state) | set(after_state)
        if before_state.get(key) != after_state.get(key)
    }
    return tuple(sorted(changed))
