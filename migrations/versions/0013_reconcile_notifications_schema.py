
"""Reconcile notifications schema for databases previously stamped at 0012.

Revision ID: 0013_reconcile_notifications_schema
Revises: 0012_create_notifications_table
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0013_reconcile_notifications"
down_revision: str | None = "0012_create_notifications_table"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 1. Reconcile title length.
    columns = {
        column["name"]: column
        for column in inspector.get_columns("notifications")
    }

    if "title" not in columns:
        raise RuntimeError("notifications.title does not exist")

    title_type = columns["title"]["type"]
    title_length = getattr(title_type, "length", None)

    if title_length == 500:
        op.alter_column(
            "notifications",
            "title",
            existing_type=title_type,
            type_=sa.String(length=255),
            existing_nullable=False,
        )
    elif title_length != 255:
        raise RuntimeError(
            f"Unexpected notifications.title length: {title_length}"
        )

    # 2. Reconcile updated_at.
    columns = {
        column["name"]: column
        for column in sa.inspect(bind).get_columns("notifications")
    }

    if "updated_at" not in columns:
        op.add_column(
            "notifications",
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
    elif columns["updated_at"]["nullable"]:
        op.alter_column(
            "notifications",
            "updated_at",
            existing_type=columns["updated_at"]["type"],
            existing_nullable=True,
            nullable=False,
        )

    # 3. Reconcile employee foreign key.
    foreign_keys = sa.inspect(bind).get_foreign_keys("notifications")

    employee_fk = next(
        (
            fk for fk in foreign_keys
            if fk["constrained_columns"] == ["employee_id"]
            and fk["referred_table"] == "employees"
        ),
        None,
    )

    if employee_fk is None:
        op.create_foreign_key(
            "fk_notifications_employee_id_employees",
            "notifications",
            "employees",
            ["employee_id"],
            ["employee_id"],
            ondelete="CASCADE",
        )
    else:
        ondelete = (
            employee_fk.get("options", {}).get("ondelete", "")
            .upper()
        )
        if ondelete != "CASCADE":
            raise RuntimeError(
                "notifications.employee_id already has a foreign key "
                "without ON DELETE CASCADE"
            )

    # 4. Reconcile composite employee/read/created index.
    indexes = {
        index["name"]: index
        for index in sa.inspect(bind).get_indexes("notifications")
    }

    index_name = "ix_notifications_emp_read_created"
    expected_columns = ["employee_id", "is_read", "created_at"]

    if index_name not in indexes:
        op.create_index(
            index_name,
            "notifications",
            expected_columns,
            unique=False,
        )
    elif indexes[index_name]["column_names"] != expected_columns:
        raise RuntimeError(
            f"Unexpected definition for index {index_name}"
        )


def downgrade() -> None:
    # No-op intentionally.
    #
    # Revision 0012 now defines the upgraded notification schema.
    # This revision only reconciles databases that were previously
    # stamped at 0012 without actually applying its operations.
    # Downgrading to 0012 must therefore preserve that schema.
    pass
