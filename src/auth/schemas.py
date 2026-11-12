"""
src/auth/schemas.py
───────────────────
Pydantic v2 request and response schemas for the Auth microservice.
"""
from datetime import date
from typing import Annotated
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
)


# ══════════════════════════════════════════════════════════════
#  Employee DTOs
# ══════════════════════════════════════════════════════════════

class EmployeeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    employee_id: UUID
    username: str
    email: EmailStr
    designation_id: UUID | None = None
    department_id: UUID | None = None
    must_change_password: bool = True


# ══════════════════════════════════════════════════════════════
#  Registration & Authentication Schemas
# ══════════════════════════════════════════════════════════════

class SignUpRequest(BaseModel):
    username: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
    ]
    email: EmailStr
    password: Annotated[
        str,
        StringConstraints(min_length=8, max_length=128),
    ]
    designation_id: UUID
    department_id: UUID
    manager_id: UUID | None = None
    date_of_birth: date | None = None

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower() if isinstance(v, str) else v


class LoginRequest(BaseModel):
    username: str  # Accepts either username or email
    password: str

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, v: str) -> str:
        return v.strip().lower() if isinstance(v, str) else v


# ══════════════════════════════════════════════════════════════
#  Token Lifecycle Schemas
# ══════════════════════════════════════════════════════════════

class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class TokenValidationRequest(BaseModel):
    token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int
    employee: EmployeeResponse


class TokenValidationResponse(BaseModel):
    """Response schema returned by the token validation endpoint."""
    valid: bool
    user_id: UUID | None = None
    email: EmailStr | None = None
    roles: list[str] = Field(default_factory=list)
    department_id: UUID | None = None
    error: str | None = None


# ══════════════════════════════════════════════════════════════
#  Password Management Schemas
# ══════════════════════════════════════════════════════════════

class ChangePasswordRequest(BaseModel):
    """Request schema for an authenticated employee changing their password."""
    new_password: Annotated[
        str,
        StringConstraints(min_length=8, max_length=128),
    ]


class ChangePasswordResponse(BaseModel):
    message: str


class ForgotPasswordRequest(BaseModel):
    """Request schema to initiate a password reset."""
    email: EmailStr

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower() if isinstance(v, str) else v


class ForgotPasswordResponse(BaseModel):
    message: str


class ResetPasswordRequest(BaseModel):
    """Request schema to finalize a password reset with a reset token."""
    token: str
    new_password: Annotated[
        str,
        StringConstraints(min_length=8, max_length=128),
    ]


class ResetPasswordResponse(BaseModel):
    message: str