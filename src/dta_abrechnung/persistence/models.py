from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..runtime import DatabaseProfile
from ..security import ActorType, AuditOperation, SensitiveReadTarget
from .base import Base, TimestampedModel


class TenantModel(TimestampedModel, Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)


class ProviderModel(TimestampedModel, Base):
    __tablename__ = "providers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    ik: Mapped[str] = mapped_column(String(32), nullable=False)
    billing_ik: Mapped[str | None] = mapped_column(String(32))


class ObjectStorageRefModel(TimestampedModel, Base):
    __tablename__ = "object_storage_refs"
    __table_args__ = (UniqueConstraint("bucket", "object_key", "version_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str | None] = mapped_column(String(64), index=True)
    bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    media_type: Mapped[str] = mapped_column(String(255), nullable=False)
    encryption_key_id: Mapped[str] = mapped_column(String(255), nullable=False)
    retention_class: Mapped[str] = mapped_column(String(64), nullable=False)
    legal_hold: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    immutable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    residency: Mapped[str] = mapped_column(String(64), nullable=False)
    version_id: Mapped[str | None] = mapped_column(String(255))


class PlanningSnapshotModel(TimestampedModel, Base):
    __tablename__ = "planning_snapshots"

    snapshot_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    hub_id: Mapped[str | None] = mapped_column(String(64), index=True)
    planning_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    mission_count: Mapped[int] = mapped_column(Integer, nullable=False)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_job_id: Mapped[str | None] = mapped_column(String(64))
    object_storage_ref_id: Mapped[str | None] = mapped_column(ForeignKey("object_storage_refs.id"))


class AuditLedgerModel(Base):
    __tablename__ = "audit_ledger"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    table_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    row_pk: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    actor_type: Mapped[ActorType] = mapped_column(Enum(ActorType), nullable=False)
    operation: Mapped[AuditOperation] = mapped_column(Enum(AuditOperation), nullable=False, index=True)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    tenant_id: Mapped[str | None] = mapped_column(String(64), index=True)
    reason: Mapped[str | None] = mapped_column(Text)
    legal_basis: Mapped[str | None] = mapped_column(Text)
    changed_fields: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    before_state: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    after_state: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    sensitive_read_target: Mapped[SensitiveReadTarget | None] = mapped_column(Enum(SensitiveReadTarget))


class RuntimeProfileModel(TimestampedModel, Base):
    __tablename__ = "runtime_profiles"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    profile: Mapped[DatabaseProfile] = mapped_column(Enum(DatabaseProfile), nullable=False)
    database_url: Mapped[str] = mapped_column(String(512), nullable=False)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)


class SubmissionArtifactRecord(TimestampedModel, Base):
    __tablename__ = "submission_artifacts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str | None] = mapped_column(String(64), index=True)
    invoice_id: Mapped[str | None] = mapped_column(String(64), index=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    object_storage_ref_id: Mapped[str] = mapped_column(ForeignKey("object_storage_refs.id"), nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)


class BillingFactRecord(TimestampedModel, Base):
    __tablename__ = "billing_facts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payer_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    procedure: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    service_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    line_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
