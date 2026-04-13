"""Persistence foundation tables and Postgres audit hooks."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from dta_abrechnung.persistence.postgres import AUDIT_FUNCTION_SQL, create_audit_trigger_sql, create_tenant_rls_sql
from dta_abrechnung.runtime import DatabaseProfile
from dta_abrechnung.security import ActorType, AuditOperation, SensitiveReadTarget


revision = "20260413_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "providers",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("ik", sa.String(length=32), nullable=False),
        sa.Column("billing_ik", sa.String(length=32)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_providers_tenant_id", "providers", ["tenant_id"])
    op.create_table(
        "object_storage_refs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64)),
        sa.Column("bucket", sa.String(length=255), nullable=False),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("media_type", sa.String(length=255), nullable=False),
        sa.Column("encryption_key_id", sa.String(length=255), nullable=False),
        sa.Column("retention_class", sa.String(length=64), nullable=False),
        sa.Column("legal_hold", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("immutable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("residency", sa.String(length=64), nullable=False),
        sa.Column("version_id", sa.String(length=255)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("bucket", "object_key", "version_id"),
    )
    op.create_index("ix_object_storage_refs_tenant_id", "object_storage_refs", ["tenant_id"])
    op.create_table(
        "planning_snapshots",
        sa.Column("snapshot_id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("hub_id", sa.String(length=64)),
        sa.Column("planning_date", sa.Date(), nullable=False),
        sa.Column("mission_count", sa.Integer(), nullable=False),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_job_id", sa.String(length=64)),
        sa.Column("object_storage_ref_id", sa.String(length=64), sa.ForeignKey("object_storage_refs.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_planning_snapshots_tenant_id", "planning_snapshots", ["tenant_id"])
    op.create_index("ix_planning_snapshots_hub_id", "planning_snapshots", ["hub_id"])
    op.create_index("ix_planning_snapshots_planning_date", "planning_snapshots", ["planning_date"])
    op.create_table(
        "audit_ledger",
        sa.Column("event_id", sa.String(length=64), primary_key=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("table_name", sa.String(length=128), nullable=False),
        sa.Column("row_pk", sa.String(length=128), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("actor_type", sa.Enum(ActorType), nullable=False),
        sa.Column("operation", sa.Enum(AuditOperation), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("tenant_id", sa.String(length=64)),
        sa.Column("reason", sa.Text()),
        sa.Column("legal_basis", sa.Text()),
        sa.Column("changed_fields", sa.JSON(), nullable=False),
        sa.Column("before_state", sa.JSON()),
        sa.Column("after_state", sa.JSON()),
        sa.Column("sensitive_read_target", sa.Enum(SensitiveReadTarget)),
    )
    op.create_index("ix_audit_ledger_occurred_at", "audit_ledger", ["occurred_at"])
    op.create_index("ix_audit_ledger_table_name", "audit_ledger", ["table_name"])
    op.create_index("ix_audit_ledger_row_pk", "audit_ledger", ["row_pk"])
    op.create_index("ix_audit_ledger_actor_id", "audit_ledger", ["actor_id"])
    op.create_index("ix_audit_ledger_operation", "audit_ledger", ["operation"])
    op.create_index("ix_audit_ledger_request_id", "audit_ledger", ["request_id"])
    op.create_index("ix_audit_ledger_tenant_id", "audit_ledger", ["tenant_id"])
    op.create_table(
        "runtime_profiles",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("profile", sa.Enum(DatabaseProfile), nullable=False),
        sa.Column("database_url", sa.String(length=512), nullable=False),
        sa.Column("environment", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "submission_artifacts",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64)),
        sa.Column("invoice_id", sa.String(length=64)),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("object_storage_ref_id", sa.String(length=64), sa.ForeignKey("object_storage_refs.id"), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_submission_artifacts_tenant_id", "submission_artifacts", ["tenant_id"])
    op.create_index("ix_submission_artifacts_invoice_id", "submission_artifacts", ["invoice_id"])
    op.create_table(
        "billing_facts",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("provider_id", sa.String(length=64), nullable=False),
        sa.Column("payer_id", sa.String(length=64), nullable=False),
        sa.Column("procedure", sa.String(length=64), nullable=False),
        sa.Column("service_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("line_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_billing_facts_tenant_id", "billing_facts", ["tenant_id"])
    op.create_index("ix_billing_facts_provider_id", "billing_facts", ["provider_id"])
    op.create_index("ix_billing_facts_payer_id", "billing_facts", ["payer_id"])
    op.create_index("ix_billing_facts_procedure", "billing_facts", ["procedure"])
    op.create_index("ix_billing_facts_service_date", "billing_facts", ["service_date"])

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(AUDIT_FUNCTION_SQL)
        op.execute(create_audit_trigger_sql("tenants"))
        op.execute(create_audit_trigger_sql("providers"))
        op.execute(create_audit_trigger_sql("object_storage_refs"))
        op.execute(create_audit_trigger_sql("planning_snapshots"))
        op.execute(create_tenant_rls_sql("providers"))
        op.execute(create_tenant_rls_sql("object_storage_refs"))
        op.execute(create_tenant_rls_sql("planning_snapshots"))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP FUNCTION IF EXISTS audit_row_change() CASCADE;")

    op.drop_index("ix_billing_facts_service_date", table_name="billing_facts")
    op.drop_index("ix_billing_facts_procedure", table_name="billing_facts")
    op.drop_index("ix_billing_facts_payer_id", table_name="billing_facts")
    op.drop_index("ix_billing_facts_provider_id", table_name="billing_facts")
    op.drop_index("ix_billing_facts_tenant_id", table_name="billing_facts")
    op.drop_table("billing_facts")
    op.drop_index("ix_submission_artifacts_invoice_id", table_name="submission_artifacts")
    op.drop_index("ix_submission_artifacts_tenant_id", table_name="submission_artifacts")
    op.drop_table("submission_artifacts")
    op.drop_table("runtime_profiles")
    op.drop_index("ix_audit_ledger_tenant_id", table_name="audit_ledger")
    op.drop_index("ix_audit_ledger_request_id", table_name="audit_ledger")
    op.drop_index("ix_audit_ledger_operation", table_name="audit_ledger")
    op.drop_index("ix_audit_ledger_actor_id", table_name="audit_ledger")
    op.drop_index("ix_audit_ledger_row_pk", table_name="audit_ledger")
    op.drop_index("ix_audit_ledger_table_name", table_name="audit_ledger")
    op.drop_index("ix_audit_ledger_occurred_at", table_name="audit_ledger")
    op.drop_table("audit_ledger")
    op.drop_index("ix_planning_snapshots_planning_date", table_name="planning_snapshots")
    op.drop_index("ix_planning_snapshots_hub_id", table_name="planning_snapshots")
    op.drop_index("ix_planning_snapshots_tenant_id", table_name="planning_snapshots")
    op.drop_table("planning_snapshots")
    op.drop_index("ix_object_storage_refs_tenant_id", table_name="object_storage_refs")
    op.drop_table("object_storage_refs")
    op.drop_index("ix_providers_tenant_id", table_name="providers")
    op.drop_table("providers")
    op.drop_table("tenants")
