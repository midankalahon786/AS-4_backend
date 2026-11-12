"""
src/webhooks/repository.py
──────────────────────────
SQLAlchemy 2.0 implementation of IWebhookRepository.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.employees.models import Employee, StatusMaster, Designation
from src.organization.models import Department 


class SQLAlchemyWebhookRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_department_by_code(self, code: str) -> Department | None:
        stmt = select(Department).where(
            func.upper(Department.department_code) == code.strip().upper()
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_designation_by_code(self, code: str) -> Designation | None:
        stmt = select(Designation).where(
            func.upper(Designation.designation_code) == code.strip().upper()
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_status_by_code(
        self, code: str, entity_type: str = "GENERAL"
    ) -> StatusMaster | None:
        stmt = select(StatusMaster).where(
            func.upper(StatusMaster.status_code) == code.strip().upper(),
            func.upper(StatusMaster.entity_type) == entity_type.strip().upper(),
        )
        row = (await self.db.execute(stmt)).scalar_one_or_none()
        if row:
            return row

        code_upper = code.strip().upper()
        candidates = [code_upper]
        if code_upper in ("ACTIVE", "EMP_ACTIVE"):
            candidates.extend(["EMP_ACTIVE", "ACTIVE", "GEN_ACTIVE"])
        elif code_upper in ("INACTIVE", "EMP_INACTIVE"):
            candidates.extend(["EMP_INACTIVE", "INACTIVE", "GEN_INACTIVE"])

        fallback_stmt = select(StatusMaster).where(
            func.upper(StatusMaster.status_code).in_(candidates)
        )
        return (await self.db.execute(fallback_stmt)).scalars().first()

    async def get_employee_by_email(self, email: str) -> Employee | None:
        stmt = select(Employee).where(
            func.lower(Employee.email) == email.strip().lower()
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

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
    ) -> Employee:
        now = datetime.now(timezone.utc)
        emp = Employee(
            username=username.strip(),
            email=email.strip().lower(),
            department_id=department_id,
            designation_id=designation_id,
            status_id=status_id,
            date_of_joining=datetime.fromisoformat(date_of_joining),
            date_of_birth=(
                datetime.fromisoformat(date_of_birth) if date_of_birth else None
            ),
            manager_id=manager_id,
            # Empty password_hash is intentional for HRIS-provisioned SSO accounts
            password_hash="",
            created_at=now,
            updated_at=now,
        )
        self.db.add(emp)
        await self.db.flush()
        return emp

    async def update_employee_from_hris(
        self,
        employee_id: uuid.UUID,
        update_data: dict[str, Any],
    ) -> Employee | None:
        update_data["updated_at"] = datetime.now(timezone.utc)
        stmt = (
            update(Employee)
            .where(Employee.employee_id == employee_id)
            .values(**update_data)
        )
        await self.db.execute(stmt)

        fetch_stmt = select(Employee).where(Employee.employee_id == employee_id)
        return (await self.db.execute(fetch_stmt)).scalar_one_or_none()