"""
src/employees/interfaces.py
────────────────────────────
Abstract repository contract for employee management.
"""
from __future__ import annotations

import uuid
from typing import Any, Protocol

from src.employees import schemas
from src.employees.models import Employee


class IEmployeeRepository(Protocol):
    async def list_employees(
        self,
        page: int,
        limit: int,
        department_id: uuid.UUID | None = None,
        designation_id: uuid.UUID | None = None,
        status_id: uuid.UUID | None = None,
        manager_id: uuid.UUID | None = None,
        is_active: bool | None = None,
        search: str | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> schemas.EmployeeListResponse:
        """Fetch paginated employees with dynamic filters and eager-loaded relations."""
        ...

    async def get_employee_by_id(self, employee_id: uuid.UUID) -> Employee | None:
        """Fetch employee with department, designation, manager, wallet, and active roles loaded."""
        ...

    async def get_by_username_or_email(
        self, username: str, email: str
    ) -> Employee | None:
        """Check uniqueness for employee username or email."""
        ...

    async def get_role_by_code(self, role_code: str) -> uuid.UUID | None:
        """Fetch role_id by code (e.g. 'EMPLOYEE')."""
        ...

    async def get_status_by_code(self, status_code: str) -> uuid.UUID | None:
        """Fetch status_id by code (e.g. 'ACTIVE', 'INACTIVE')."""
        ...

    async def create_employee_with_wallet_and_role(
        self,
        data: schemas.CreateEmployeeRequest,
        hashed_password: str,
        default_role_id: uuid.UUID,
        created_by_id: uuid.UUID,
    ) -> Employee:
        """Atomically persist employee, default role, and initial wallet."""
        ...

    async def update_employee(
        self,
        employee_id: uuid.UUID,
        update_fields: dict[str, Any],
        updated_by_id: uuid.UUID,
    ) -> Employee | None:
        """Update employee columns and return the refreshed entity."""
        ...

    async def update_status(
        self,
        employee_id: uuid.UUID,
        status_id: uuid.UUID,
        updated_by_id: uuid.UUID,
    ) -> bool:
        """Update status_id for an employee."""
        ...

    async def get_active_counts(self) -> dict[str, int]: ...

    async def get_manager_email(self, employee_id: uuid.UUID) -> str | None: ...

    async def get_departments_with_members(self) -> list[dict[str, Any]]: ...