"""
src/employees/schemas.py
────────────────────────
Pydantic v2 schemas for the Employee management microservice.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


# ══════════════════════════════════════════════════════════════
#  Nested Relation Projections
# ══════════════════════════════════════════════════════════════

class DesignationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    designation_id: UUID
    designation_name: str
    designation_code: str
    level: int


class DepartmentTypeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type_name: str
    type_code: str


class DepartmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    department_id: UUID
    department_name: str
    department_code: str
    department_type: DepartmentTypeResponse | None = None


class ManagerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    employee_id: UUID
    username: str
    email: str


class StatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status_id: UUID
    status_code: str
    status_name: str


class WalletResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    wallet_id: UUID
    available_points: int
    redeemed_points: int
    total_earned_points: int
    version: int = 1


class RoleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role_id: UUID
    role_name: str
    role_code: str


# ══════════════════════════════════════════════════════════════
#  Main Response Models
# ══════════════════════════════════════════════════════════════

class EmployeeCreatedResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    employee_id: UUID
    username: str
    email: str
    designation_id: UUID
    department_id: UUID
    manager_id: UUID | None = None
    date_of_joining: date
    date_of_birth: date | None = None
    status_id: UUID
    is_active: bool = True
    wallet: WalletResponse | None = None
    created_at: datetime
    created_by: UUID | None = None


class EmployeeDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    employee_id: UUID
    username: str
    email: str
    designation: DesignationResponse | None = None
    department: DepartmentResponse | None = None
    manager: ManagerResponse | None = None
    date_of_joining: date
    date_of_birth: date | None = None
    status: StatusResponse | None = None
    is_active: bool = True
    wallet: WalletResponse | None = None
    roles: list[RoleResponse] = Field(default_factory=list)
    created_at: datetime
    created_by: UUID | None = None
    updated_at: datetime | None = None
    updated_by: UUID | None = None


class EmployeeListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    employee_id: UUID
    username: str
    email: str
    designation_id: UUID | None = None
    designation_name: str | None = None
    department_id: UUID | None = None
    department_name: str | None = None
    manager_id: UUID | None = None
    manager_name: str | None = None
    date_of_joining: date
    status_id: UUID | None = None
    status_name: str | None = None
    is_active: bool = True
    created_at: datetime
    updated_at: datetime | None = None


class PaginationMeta(BaseModel):
    current_page: int
    per_page: int
    total: int
    total_pages: int
    has_next: bool
    has_previous: bool


class EmployeeListResponse(BaseModel):
    data: list[EmployeeListItem]
    pagination: PaginationMeta


# ══════════════════════════════════════════════════════════════
#  Request Models
# ══════════════════════════════════════════════════════════════

class CreateEmployeeRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    designation_id: UUID
    department_id: UUID
    manager_id: UUID | None = None
    date_of_joining: date
    date_of_birth: date | None = None
    status_id: UUID

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower() if isinstance(v, str) else v

    @field_validator("date_of_birth")
    @classmethod
    def validate_dob(cls, v: date | None) -> date | None:
        if v is not None and v >= datetime.now(timezone.utc).date():
            raise ValueError("Date of birth must be in the past")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain an uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain a lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain a number")
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
            raise ValueError("Password must contain a special character")
        return v

    @field_validator("date_of_joining")
    @classmethod
    def validate_doj(cls, v: date) -> date:
        if v > datetime.now(timezone.utc).date():
            raise ValueError("Date of joining cannot be in the future")
        return v


class UpdateEmployeeRequest(BaseModel):
    username: str | None = Field(None, min_length=3, max_length=100)
    email: EmailStr | None = None
    designation_id: UUID | None = None
    department_id: UUID | None = None
    manager_id: UUID | None = None
    status_id: UUID | None = None
    date_of_birth: date | None = None
    is_active: bool | None = None

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v: str | None) -> str | None:
        return v.strip().lower() if isinstance(v, str) else v