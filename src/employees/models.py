from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.organization.models import Department

import uuid
from datetime import date, datetime
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base

class Designation(Base):
    __tablename__ = "designations"
    __table_args__ = (
        Index("idx_designations_is_active", "is_active"),
        Index("idx_designations_level", "level"),
    )

    designation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    designation_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    designation_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.employee_id", ondelete="RESTRICT"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.employee_id", ondelete="RESTRICT"), nullable=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)


class StatusMaster(Base):
    __tablename__ = "status_master"
    __table_args__ = (
        Index("idx_status_master_entity_type", "entity_type"),
        Index("idx_status_master_entity_type_status_code", "entity_type", "status_code"),
    )

    status_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    status_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    status_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.employee_id", ondelete="RESTRICT"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.employee_id", ondelete="RESTRICT"), nullable=True
    )


class Employee(Base):
    __tablename__ = "employees"
    __table_args__ = (
        Index("idx_employees_created_at", "created_at"),
        Index("idx_employees_date_of_birth", "date_of_birth"),
        Index("idx_employees_date_of_joining", "date_of_joining"),
        Index("idx_employees_department_id", "department_id"),
        Index("idx_employees_department_id_status_id", "department_id", "status_id"),
        Index("idx_employees_designation_id", "designation_id"),
        Index("idx_employees_manager_id", "manager_id"),
        Index("idx_employees_manager_id_status_id", "manager_id", "status_id"),
        Index("idx_employees_status_id", "status_id"),
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    designation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("designations.designation_id"), nullable=False
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    department_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.department_id"), nullable=False
    )
    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.employee_id"), nullable=True
    )
    date_of_joining: Mapped[date] = mapped_column(Date, nullable=False)
    status_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("status_master.status_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.employee_id", ondelete="RESTRICT"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.employee_id", ondelete="RESTRICT"), nullable=True
    )
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)

    designation: Mapped["Designation"] = relationship("Designation", foreign_keys=[designation_id])
    status: Mapped["StatusMaster"] = relationship("StatusMaster", foreign_keys=[status_id])
    manager: Mapped["Employee | None"] = relationship(
        "Employee", foreign_keys=[manager_id], remote_side=[employee_id], back_populates="subordinates"
    )
    subordinates: Mapped[list["Employee"]] = relationship(
        "Employee", foreign_keys=[manager_id], back_populates="manager"
    )
    