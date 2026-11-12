"""
src/webhooks/interfaces.py
──────────────────────────
Abstract repository contract for HRIS webhook employee provisioning and updates.
"""
from __future__ import annotations

import uuid
from typing import Any, Protocol

from src.employees.models import Employee, StatusMaster, Designation
from src.organization.models import Department 


class IWebhookRepository(Protocol):
    async def get_department_by_code(self, code: str) -> Department | None: ...

    async def get_designation_by_code(self, code: str) -> Designation | None: ...

    async def get_status_by_code(
        self, code: str, entity_type: str = "GENERAL"
    ) -> StatusMaster | None: ...

    async def get_employee_by_email(self, email: str) -> Employee | None: ...

    async def create_employee_from_hris(
        self,
        username: str,
        email: str,
        department_id: uuid.UUID,
        designation_id: uuid.UUID,
        status_id: uuid.UUID,
        date_of_joining: str,
        date_of_birth: str | None = None,
        manager_id: uuid.UUID | None = None,
    ) -> Employee: ...

    async def update_employee_from_hris(
        self,
        employee_id: uuid.UUID,
        update_data: dict[str, Any],
    ) -> Employee | None: ...