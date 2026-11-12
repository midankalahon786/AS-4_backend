import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base

class Role(Base):
    __tablename__ = "roles"

    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    role_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    role_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.employee_id", ondelete="RESTRICT"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.employee_id", ondelete="RESTRICT"), nullable=True
    )
    reviewer_weight: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), default=Decimal("1.0000"), server_default="1.0000", nullable=False
    )

    employee_roles: Mapped[list["EmployeeRole"]] = relationship("EmployeeRole", back_populates="role")
    route_permissions: Mapped[list["RoutePermission"]] = relationship(
        "RoutePermission", back_populates="role", cascade="all, delete-orphan"
    )


class RoutePermission(Base):
    __tablename__ = "route_permissions"
    __table_args__ = (
        UniqueConstraint("route_key", "role_id", name="uq_route_permissions_route_role"),
        Index("idx_route_permissions_route_key", "route_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    route_key: Mapped[str] = mapped_column(String(200), nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.role_id", ondelete="CASCADE", name="fk_route_permissions_role"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)

    role: Mapped["Role"] = relationship("Role", back_populates="route_permissions")


class EmployeeRole(Base):
    __tablename__ = "employee_roles"
    __table_args__ = (
        UniqueConstraint("employee_id", "role_id", "is_active", name="uq_employee_role_active"),
        Index("idx_employee_roles_assigned_at", "assigned_at"),
        Index("idx_employee_roles_employee_id", "employee_id"),
        Index("idx_employee_roles_employee_id_is_active", "employee_id", "is_active"),
        Index("idx_employee_roles_is_active", "is_active"),
        Index("idx_employee_roles_revoked_at", "revoked_at"),
        Index("idx_employee_roles_role_id", "role_id"),
    )

    employee_role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.employee_id", ondelete="CASCADE"), nullable=False
    )
    role_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("roles.role_id"), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    assigned_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.employee_id"), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.employee_id", ondelete="RESTRICT"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.employee_id"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.employee_id"), nullable=False
    )

    role: Mapped["Role"] = relationship("Role", back_populates="employee_roles")