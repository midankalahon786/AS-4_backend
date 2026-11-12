"""
src/organization/schemas.py
───────────────────────────
Pydantic v2 schemas for Departments, Designations, Department Types,
Status Master, and Audit Logs.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ══════════════════════════════════════════════════════════════
#  Shared Nested DTOs & Pagination
# ══════════════════════════════════════════════════════════════

class DepartmentTypeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    department_type_id: UUID
    type_name: str
    type_code: str


class ManagerBriefResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    employee_id: UUID
    username: str
    email: str | None = None


class PaginationMeta(BaseModel):
    current_page: int
    per_page: int
    total: int
    total_pages: int
    has_next: bool
    has_previous: bool


# ══════════════════════════════════════════════════════════════
#  Department Type Schemas
# ══════════════════════════════════════════════════════════════

class CreateDepartmentTypeRequest(BaseModel):
    type_name: str = Field(..., min_length=2, max_length=100)
    type_code: str = Field(..., min_length=2, max_length=50)

    @field_validator("type_code")
    @classmethod
    def uppercase_code(cls, v: str) -> str:
        return v.strip().upper()


class UpdateDepartmentTypeRequest(BaseModel):
    type_name: str | None = Field(None, min_length=2, max_length=100)
    type_code: str | None = Field(None, min_length=2, max_length=50)

    @field_validator("type_code")
    @classmethod
    def uppercase_code(cls, v: str | None) -> str | None:
        return v.strip().upper() if v else v


# ══════════════════════════════════════════════════════════════
#  Department Schemas
# ══════════════════════════════════════════════════════════════

class DepartmentListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    department_id: UUID
    department_name: str
    department_code: str
    department_type: DepartmentTypeResponse | None = None
    is_active: bool
    created_at: datetime
    created_by: UUID | None = None
    created_by_info: ManagerBriefResponse | None = None
    updated_by: UUID | None = None
    updated_by_info: ManagerBriefResponse | None = None


class DepartmentListResponse(BaseModel):
    data: list[DepartmentListItem]
    pagination: PaginationMeta


class DepartmentDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    department_id: UUID
    department_name: str
    department_code: str
    department_type: DepartmentTypeResponse | None = None
    employee_count: int
    is_active: bool
    created_at: datetime
    updated_at: datetime | None = None
    created_by: UUID | None = None
    created_by_info: ManagerBriefResponse | None = None
    updated_by: UUID | None = None
    updated_by_info: ManagerBriefResponse | None = None


class CreateDepartmentRequest(BaseModel):
    department_name: str = Field(..., min_length=2, max_length=100)
    department_code: str = Field(..., min_length=2, max_length=50)
    department_type_id: UUID

    @field_validator("department_code")
    @classmethod
    def uppercase_code(cls, v: str) -> str:
        return v.strip().upper()


class UpdateDepartmentRequest(BaseModel):
    department_name: str | None = Field(None, min_length=2, max_length=100)
    department_code: str | None = Field(None, min_length=2, max_length=50)
    department_type_id: UUID | None = None
    is_active: bool | None = None

    @field_validator("department_code")
    @classmethod
    def uppercase_code(cls, v: str | None) -> str | None:
        return v.strip().upper() if v else v


class DepartmentCreatedResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    department_id: UUID
    department_name: str
    department_code: str
    department_type: DepartmentTypeResponse | None = None
    is_active: bool
    created_at: datetime
    created_by: UUID | None = None
    created_by_info: ManagerBriefResponse | None = None


class DepartmentUpdatedResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    department_id: UUID
    department_name: str
    department_code: str
    department_type: DepartmentTypeResponse | None = None
    is_active: bool
    updated_at: datetime | None = None
    updated_by: UUID | None = None
    updated_by_info: ManagerBriefResponse | None = None


# ══════════════════════════════════════════════════════════════
#  Designation Schemas
# ══════════════════════════════════════════════════════════════

class DesignationListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    designation_id: UUID
    designation_name: str
    designation_code: str
    level: int
    is_active: bool
    created_at: datetime


class DesignationListResponse(BaseModel):
    data: list[DesignationListItem]
    pagination: PaginationMeta


class DesignationDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    designation_id: UUID
    designation_name: str
    designation_code: str
    level: int
    description: str | None = None
    employee_count: int
    is_active: bool
    created_at: datetime
    updated_at: datetime | None = None


class CreateDesignationRequest(BaseModel):
    designation_name: str = Field(..., min_length=2, max_length=100)
    designation_code: str = Field(..., min_length=2, max_length=50)
    level: int = Field(..., ge=1)
    description: str | None = None

    @field_validator("designation_code")
    @classmethod
    def uppercase_code(cls, v: str) -> str:
        return v.strip().upper()


class UpdateDesignationRequest(BaseModel):
    designation_name: str | None = Field(None, min_length=2, max_length=100)
    designation_code: str | None = Field(None, min_length=2, max_length=50)
    level: int | None = Field(None, ge=1)
    description: str | None = None
    is_active: bool | None = None

    @field_validator("designation_code")
    @classmethod
    def uppercase_code(cls, v: str | None) -> str | None:
        return v.strip().upper() if v else v


# ══════════════════════════════════════════════════════════════
#  Status Master Schemas
# ══════════════════════════════════════════════════════════════

class StatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status_id: UUID
    status_code: str
    status_name: str
    description: str | None = None
    entity_type: str
    created_at: datetime


class StatusDetailResponse(StatusResponse):
    updated_at: datetime | None = None


class CreateStatusRequest(BaseModel):
    status_code: str = Field(..., min_length=2, max_length=50)
    status_name: str = Field(..., min_length=2, max_length=100)
    description: str | None = None
    entity_type: str = Field(..., min_length=2, max_length=50)

    @field_validator("status_code")
    @classmethod
    def uppercase_status_code(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("entity_type")
    @classmethod
    def validate_entity_type(cls, v: str) -> str:
        allowed = {"EMPLOYEE", "REVIEW", "TRANSACTION", "REWARD"}
        clean = v.strip().upper()
        if clean not in allowed:
            raise ValueError(f"entity_type must be one of: {', '.join(sorted(allowed))}")
        return clean


class UpdateStatusRequest(BaseModel):
    status_name: str | None = Field(None, min_length=2, max_length=100)
    description: str | None = None


# ══════════════════════════════════════════════════════════════
#  Audit Log Schemas
# ══════════════════════════════════════════════════════════════

class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    audit_id: UUID
    table_name: str
    record_id: UUID
    operation_type: str
    old_values: Any | None = None
    new_values: Any | None = None
    performed_by: UUID
    performed_at: datetime
    ip_address: str | None = None
    user_agent: str | None = None
    employee_name: str | None = None
    employee_email: str | None = None


class AuditLogListResponse(BaseModel):
    data: list[AuditLogResponse]
    pagination: PaginationMeta