"""Align Postgres trigger audit payload with application audit output."""

from __future__ import annotations

from alembic import op

from dta_abrechnung.persistence.postgres import AUDIT_FUNCTION_SQL


revision = "20260413_0002"
down_revision = "20260413_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(AUDIT_FUNCTION_SQL)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(AUDIT_FUNCTION_SQL)
