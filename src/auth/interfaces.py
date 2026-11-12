"""
src/auth/interfaces.py
───────────────────────
Abstract repository contract for authentication and employee identity.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Protocol

from src.auth.models import RefreshToken
from src.auth.schemas import SignUpRequest
from src.employees.models import Employee


class IAuthRepository(Protocol):
    async def get_employee_by_identifier(self, identifier: str) -> Employee | None:
        """Find an employee case-insensitively by either username or email."""
        ...

    async def get_employee_by_id(self, employee_id: uuid.UUID) -> Employee | None:
        """Find an employee by their primary key UUID."""
        ...

    async def get_employee_by_email(self, email: str) -> Employee | None:
        """Find an employee by exact or case-normalized email."""
        ...

    async def get_active_role_codes(self, employee_id: uuid.UUID) -> list[str]:
        """Fetch active role codes (e.g. ['ADMIN', 'EMPLOYEE']) for an employee."""
        ...

    async def validate_signup_dependencies(
        self,
        designation_id: uuid.UUID,
        department_id: uuid.UUID,
        manager_id: uuid.UUID | None,
    ) -> uuid.UUID:
        """
        Validates foreign relations and returns the ACTIVE status_id UUID.
        Raises ValueError if any referenced entity is missing.
        """
        ...

    async def create_employee(
        self,
        payload: SignUpRequest,
        password_hash: str,
        status_id: uuid.UUID,
        created_by: uuid.UUID,
    ) -> Employee:
        """Persists a new employee record."""
        ...

    async def create_refresh_token(
        self,
        token_id: uuid.UUID,
        token_hash: str,
        employee_id: uuid.UUID,
        expires_at: datetime,
    ) -> RefreshToken:
        """Persists a new refresh token record."""
        ...

    async def get_refresh_token(self, token_id: uuid.UUID) -> RefreshToken | None:
        """Find a refresh token by its primary key UUID."""
        ...

    async def revoke_refresh_token(
        self, token_id: uuid.UUID, revoked_at: datetime
    ) -> bool:
        """Marks a single refresh token as revoked."""
        ...

    async def revoke_all_employee_tokens(
        self, employee_id: uuid.UUID, revoked_at: datetime
    ) -> int:
        """Revokes all active refresh tokens belonging to an employee."""
        ...

    async def update_password(
        self,
        employee_id: uuid.UUID,
        new_password_hash: str,
        must_change_password: bool,
        updated_by: uuid.UUID,
    ) -> bool:
        """Updates the password hash and password change flags for an employee."""
        ...