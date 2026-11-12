"""
src/auth/repository.py
───────────────────────
SQLAlchemy 2.0 implementation of IAuthRepository.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import RefreshToken
from src.auth.schemas import SignUpRequest
from src.employees.models import Designation, Employee, StatusMaster
from src.organization.models import Department
from src.roles.models import EmployeeRole, Role


class SQLAlchemyAuthRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_employee_by_identifier(self, identifier: str) -> Employee | None:
        cleaned = identifier.strip().lower()
        stmt = select(Employee).where(
            or_(
                func.lower(Employee.username) == cleaned,
                func.lower(Employee.email) == cleaned,
            )
        )
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def get_employee_by_id(self, employee_id: uuid.UUID) -> Employee | None:
        stmt = select(Employee).where(Employee.employee_id == employee_id)
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def get_employee_by_email(self, email: str) -> Employee | None:
        cleaned = email.strip().lower()
        stmt = select(Employee).where(func.lower(Employee.email) == cleaned)
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def get_active_role_codes(self, employee_id: uuid.UUID) -> list[str]:
        stmt = (
            select(Role.role_code)
            .join(EmployeeRole, EmployeeRole.role_id == Role.role_id)
            .where(
                EmployeeRole.employee_id == employee_id,
                EmployeeRole.is_active.is_(True),
            )
        )
        res = await self.db.execute(stmt)
        return list(res.scalars().all())

    async def validate_signup_dependencies(
        self,
        designation_id: uuid.UUID,
        department_id: uuid.UUID,
        manager_id: uuid.UUID | None,
    ) -> uuid.UUID:
        if manager_id:
            m_stmt = select(Employee.employee_id).where(Employee.employee_id == manager_id)
            if not (await self.db.execute(m_stmt)).scalar_one_or_none():
                raise ValueError("Manager not found")

        des_stmt = select(Designation.designation_id).where(Designation.designation_id == designation_id)
        if not (await self.db.execute(des_stmt)).scalar_one_or_none():
            raise ValueError("Designation not found")

        dep_stmt = select(Department.department_id).where(Department.department_id == department_id)
        if not (await self.db.execute(dep_stmt)).scalar_one_or_none():
            raise ValueError("Department not found")

        status_stmt = select(StatusMaster.status_id).where(StatusMaster.status_code == "ACTIVE")
        status_id = (await self.db.execute(status_stmt)).scalar_one_or_none()
        if not status_id:
            raise ValueError("Default ACTIVE status not found in system")

        return status_id

    async def create_employee(
        self,
        payload: SignUpRequest,
        password_hash: str,
        status_id: uuid.UUID,
        created_by: uuid.UUID,
    ) -> Employee:
        now = datetime.now(timezone.utc)
        emp = Employee(
            username=payload.username,
            email=payload.email,
            password_hash=password_hash,
            designation_id=payload.designation_id,
            department_id=payload.department_id,
            manager_id=payload.manager_id,
            date_of_joining=now.date(),
            date_of_birth=payload.date_of_birth,
            status_id=status_id,
            created_by=created_by,
            updated_by=created_by,
            created_at=now,
            updated_at=now,
        )
        self.db.add(emp)
        await self.db.flush()
        await self.db.refresh(emp)
        return emp

    async def create_refresh_token(
        self,
        token_id: uuid.UUID,
        token_hash: str,
        employee_id: uuid.UUID,
        expires_at: datetime,
    ) -> RefreshToken:
        now = datetime.now(timezone.utc)
        token_record = RefreshToken(
            token_id=token_id,
            token_hash=token_hash,
            employee_id=employee_id,
            expires_at=expires_at,
            created_at=now,
            updated_at=now,
        )
        self.db.add(token_record)
        await self.db.flush()
        await self.db.refresh(token_record)
        return token_record

    async def get_refresh_token(self, token_id: uuid.UUID) -> RefreshToken | None:
        stmt = select(RefreshToken).where(RefreshToken.token_id == token_id)
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def revoke_refresh_token(
        self, token_id: uuid.UUID, revoked_at: datetime
    ) -> bool:
        stmt = (
            update(RefreshToken)
            .where(RefreshToken.token_id == token_id)
            .values(revoked_at=revoked_at, updated_at=revoked_at)
        )
        res = await self.db.execute(stmt)
        return res.rowcount > 0

    async def revoke_all_employee_tokens(
        self, employee_id: uuid.UUID, revoked_at: datetime
    ) -> int:
        stmt = (
            update(RefreshToken)
            .where(
                RefreshToken.employee_id == employee_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at, updated_at=revoked_at)
        )
        res = await self.db.execute(stmt)
        return res.rowcount

    async def update_password(
        self,
        employee_id: uuid.UUID,
        new_password_hash: str,
        must_change_password: bool,
        updated_by: uuid.UUID,
    ) -> bool:
        now = datetime.now(timezone.utc)
        stmt = (
            update(Employee)
            .where(Employee.employee_id == employee_id)
            .values(
                password_hash=new_password_hash,
                must_change_password=must_change_password,
                updated_at=now,
                updated_by=updated_by,
            )
        )
        res = await self.db.execute(stmt)
        return res.rowcount > 0