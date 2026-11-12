"""create notifications table

Revision ID: 0012_create_notifications_table
Revises: 0011_previous_revision
Create Date: 2026-11-10 12:25:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0012_create_notifications_table"
down_revision: str | None = "2b566568e9f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column(
            "notification_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "employee_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column(
            "is_read",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "email_sent",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "send_attempts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.employee_id"],
            name=op.f("fk_notifications_employee_id_employees"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("notification_id", name=op.f("pk_notifications")),
    )

    # Single-column indexes
    op.create_index(
        op.f("ix_notifications_employee_id"),
        "notifications",
        ["employee_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notifications_type"),
        "notifications",
        ["type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notifications_is_read"),
        "notifications",
        ["is_read"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notifications_email_sent"),
        "notifications",
        ["email_sent"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notifications_created_at"),
        "notifications",
        ["created_at"],
        unique=False,
    )

    # Composite indexes defined in __table_args__
    op.create_index(
        "ix_notifications_emp_read_created",
        "notifications",
        ["employee_id", "is_read", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_notifications_recovery_scan",
        "notifications",
        ["email_sent", "type", "send_attempts", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    # Drop composite indexes
    op.drop_index("ix_notifications_recovery_scan", table_name="notifications")
    op.drop_index("ix_notifications_emp_read_created", table_name="notifications")

    # Drop single-column indexes
    op.drop_index(op.f("ix_notifications_created_at"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_email_sent"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_is_read"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_type"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_employee_id"), table_name="notifications")

    # Drop table
    op.drop_table("notifications")