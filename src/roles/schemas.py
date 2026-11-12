"""
src/roles/schemas.py
────────────────────
Pydantic v2 request and response schemas for the Roles and Permissions microservice.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ══════════════════════════════════════════════════════════════
#  Role Requests & Responses
# ══════════════════════════════════════════════════════════════

class CreateRoleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_name: str = Field(..., min_length=2, max_length=100, description="Human-readable role name")
    role_code: str = Field(..., min_length=2, max_length=50, description="Unique uppercase code, e.g. HR_ADMIN")
    description: str | None = Field(None, max_length=500)
    reviewer_weight: float = Field(default=1.0, gt=0, description="Recognition multiplier weight for this role")

    @field_validator("role_code")
    @classmethod
    def normalize_role_code(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("role_name")
    @classmethod
    def normalize_role_name(cls, v: str) -> str:
        return v.strip()


class UpdateRoleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_name: str | None = Field(None, min_length=2, max_length=100)
    description: str | None = Field(None, max_length=500)
    reviewer_weight: float | None = Field(None, gt=0)


class RoleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role_id: UUID
    role_name: str
    role_code: str
    description: str | None = None
    reviewer_weight: float = 1.0
    created_at: datetime


# ══════════════════════════════════════════════════════════════
#  Assignment Requests & Responses
# ══════════════════════════════════════════════════════════════

class AssignRoleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee_id: UUID
    role_id: UUID


class RevokeRoleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee_id: UUID
    role_id: UUID


class EmployeeRoleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    employee_id: UUID
    role_id: UUID
    role_code: str | None = None
    role_name: str | None = None
    is_active: bool
    assigned_at: datetime
    assigned_by: UUID | None = None


# ══════════════════════════════════════════════════════════════
#  Route Permission Requests & Responses
# ══════════════════════════════════════════════════════════════

class SetRoutePermissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route_key: str = Field(
        ...,
        pattern=r"^(GET|POST|PUT|PATCH|DELETE):\/.*$",
        description='e.g. "POST:/aabhar/v1/rewards/categories"',
    )
    role_id: UUID
    title: str | None = Field(None, max_length=150)


class DeleteRoutePermissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route_key: str = Field(..., pattern=r"^(GET|POST|PUT|PATCH|DELETE):\/.*$")
    role_id: UUID


class UpdateRouteTitleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route_key: str = Field(..., pattern=r"^(GET|POST|PUT|PATCH|DELETE):\/.*$")
    title: str = Field(..., min_length=1, max_length=150)


class RoutePermissionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    permission_id: UUID
    route_key: str
    role_id: UUID
    title: str | None = None


class RouteRegistryEntry(BaseModel):
    route_key: str
    title: str | None = None
    allowed_roles: list[str] = Field(default_factory=list)