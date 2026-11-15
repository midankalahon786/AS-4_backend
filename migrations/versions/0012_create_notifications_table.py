
"""Upgrade notifications table schema.

Revision ID: 0012_create_notifications_table
Revises: 2b566568e9f6
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0012_create_notifications_table"
down_revision: str | None = "2b566568e9f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Narrow title column. Existing data was checked and fits VARCHAR(255).
    op.alter_column(
        "notifications",
        "title",
        existing_type=sa.String(length=500),
        type_=sa.String(length=255),
        existing_nullable=False,
    )

    # Add updated_at for databases created from the initial revision.
    op.add_column(
        "notifications",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Enforce employee ownership.
    op.create_foreign_key(
        "fk_notifications_employee_id_employees",
        "notifications",
        "employees",
        ["employee_id"],
        ["employee_id"],
        ondelete="CASCADE",
    )

    # Optimize employee notification retrieval.
    op.create_index(
        "ix_notifications_emp_read_created",
        "notifications",
        ["employee_id", "is_read", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_notifications_emp_read_created",
        table_name="notifications",
    )

    op.drop_constraint(
        "fk_notifications_employee_id_employees",
        "notifications",
        type_="foreignkey",
    )

    op.drop_column("notifications", "updated_at")

    op.alter_column(
        "notifications",
        "title",
        existing_type=sa.String(length=255),
        type_=sa.String(length=500),
        existing_nullable=False,
    )
