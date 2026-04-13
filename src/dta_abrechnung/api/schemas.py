from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from ..domain import TenantMode


class TenantCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    mode: TenantMode
    reason: str | None = None
    legal_basis: str | None = None


class TenantResponse(BaseModel):
    id: str
    name: str
    mode: TenantMode
    created_at: datetime


class ProviderCreateRequest(BaseModel):
    tenant_id: str
    name: str = Field(min_length=1, max_length=255)
    ik: str = Field(min_length=1, max_length=32)
    billing_ik: str | None = Field(default=None, max_length=32)
    reason: str | None = None
    legal_basis: str | None = None


class ProviderResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    ik: str
    billing_ik: str | None = None


class PlanningSnapshotCreateRequest(BaseModel):
    tenant_id: str
    hub_id: str | None = None
    planning_date: date
    mission_count: int = Field(ge=0)
    source_job_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None
    legal_basis: str | None = None


class PlanningSnapshotResponse(BaseModel):
    snapshot_id: str
    tenant_id: str
    hub_id: str | None
    planning_date: date
    mission_count: int
    extracted_at: datetime
    source_job_id: str | None = None


class ProjectionFreshnessResponse(BaseModel):
    tenant_id: str
    hub_id: str | None
    snapshot_id: str
    extracted_at: datetime
    age_seconds: int


class AuditEventResponse(BaseModel):
    event_id: str
    occurred_at: datetime
    table_name: str
    row_pk: str
    actor_id: str
    actor_type: str
    operation: str
    request_id: str
    tenant_id: str | None = None
    reason: str | None = None
    legal_basis: str | None = None
    changed_fields: tuple[str, ...] = ()
    before_state: dict[str, Any] | None = None
    after_state: dict[str, Any] | None = None
    sensitive_read_target: str | None = None


class DatabaseHealthResponse(BaseModel):
    ok: bool
    profile: str
    role: str
    application_name: str
    dialect: str


class ProjectionHealthResponse(BaseModel):
    ok: bool
    freshness: ProjectionFreshnessResponse | None = None
