"""
src/employees/repository.py
────────────────────────────
SQLAlchemy 2.0 implementation of IEmployeeRepository.
"""
from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from src.employees import schemas
from src.employees.models import Designation, Employee, StatusMaster
from src.organization.models import Department
from src.roles.models import EmployeeRole, Role
from src.wallet.models import Wallet


class SQLAlchemyEmployeeRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

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
        # Base query joining reference tables
        base_query = (
            select(
                Employee,
                Designation.designation_name,
                Department.department_name,
                StatusMaster.status_name,
                StatusMaster.status_code,
            )
            .outerjoin(Designation, Employee.designation_id == Designation.designation_id)
            .outerjoin(Department, Employee.department_id == Department.department_id)
            .outerjoin(StatusMaster, Employee.status_id == StatusMaster.status_id)
        )

        filters = []
        if department_id:
            filters.append(Employee.department_id == department_id)
        if designation_id:
            filters.append(Employee.designation_id == designation_id)
        if status_id:
            filters.append(Employee.status_id == status_id)
        if manager_id:
            filters.append(Employee.manager_id == manager_id)
        if is_active is not None:
            if is_active:
                filters.append(StatusMaster.status_code.in_(("ACTIVE", "EMP_ACTIVE", "GEN_ACTIVE")))
            else:
                filters.append(
                    or_(
                        StatusMaster.status_code.notin_(("ACTIVE", "EMP_ACTIVE", "GEN_ACTIVE")),
                        StatusMaster.status_code.is_(None),
                    )
                )
        if search:
            cleaned = f"%{search.strip().lower()}%"
            filters.append(
                or_(
                    func.lower(Employee.username).like(cleaned),
                    func.lower(Employee.email).like(cleaned),
                )
            )

        if filters:
            base_query = base_query.where(*filters)

        # Count total
        count_query = select(func.count()).select_from(base_query.subquery())
        total_count = (await self.db.execute(count_query)).scalar() or 0
        total_pages = math.ceil(total_count / limit) if limit > 0 else 0
        offset = (page - 1) * limit

        # Sorting
        sort_column_map = {
            "created_at": Employee.created_at,
            "username": Employee.username,
            "date_of_joining": Employee.date_of_joining,
        }
        sort_col = sort_column_map.get(sort_by, Employee.created_at)
        ordered_query = (
            base_query.order_by(sort_col.asc() if sort_order == "asc" else sort_col.desc())
            .offset(offset)
            .limit(limit)
        )

        rows = (await self.db.execute(ordered_query)).all()

        # Resolve manager usernames
        manager_ids = {row[0].manager_id for row in rows if row[0].manager_id}
        manager_name_map = {}
        if manager_ids:
            mgr_stmt = select(Employee.employee_id, Employee.username).where(
                Employee.employee_id.in_(manager_ids)
            )
            mgr_rows = (await self.db.execute(mgr_stmt)).all()
            manager_name_map = {r[0]: r[1] for r in mgr_rows}

        data = []
        for emp, desig_name, dept_name, status_name, status_code in rows:
            data.append(
                schemas.EmployeeListItem(
                    employee_id=emp.employee_id,
                    username=emp.username,
                    email=emp.email,
                    designation_id=emp.designation_id,
                    designation_name=desig_name,
                    department_id=emp.department_id,
                    department_name=dept_name,
                    manager_id=emp.manager_id,
                    manager_name=manager_name_map.get(emp.manager_id),
                    date_of_joining=emp.date_of_joining,
                    status_id=emp.status_id,
                    status_name=status_name,
                    is_active=(status_code in ("ACTIVE", "EMP_ACTIVE", "GEN_ACTIVE")),
                    created_at=emp.created_at,
                    updated_at=emp.updated_at,
                )
            )

        return schemas.EmployeeListResponse(
            data=data,
            pagination=schemas.PaginationMeta(
                current_page=page,
                per_page=limit,
                total=total_count,
                total_pages=total_pages,
                has_next=page < total_pages,
                has_previous=page > 1,
            ),
        )

    async def get_employee_by_id(self, employee_id: uuid.UUID) -> Employee | None:
        stmt = (
            select(Employee)
            .options(
                joinedload(Employee.designation),
                joinedload(Employee.status),
                joinedload(Employee.manager)
            )
            .where(Employee.employee_id == employee_id)
        )
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_username_or_email(
        self, username: str, email: str
    ) -> Employee | None:
        stmt = select(Employee).where(
            or_(
                func.lower(Employee.username) == username.strip().lower(),
                func.lower(Employee.email) == email.strip().lower(),
            )
        )
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def get_role_by_code(self, role_code: str) -> uuid.UUID | None:
        stmt = select(Role.role_id).where(Role.role_code == role_code)
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def get_status_by_code(self, status_code: str) -> uuid.UUID | None:
        stmt = select(StatusMaster.status_id).where(
            func.upper(StatusMaster.status_code) == status_code.strip().upper()
        )
        res = await self.db.execute(stmt)
        val = res.scalar_one_or_none()
        if val:
            return val

        code_upper = status_code.strip().upper()
        fallbacks = []
        if code_upper in ("ACTIVE", "EMP_ACTIVE"):
            fallbacks = ["EMP_ACTIVE", "ACTIVE", "GEN_ACTIVE"]
        elif code_upper in ("INACTIVE", "EMP_INACTIVE"):
            fallbacks = ["EMP_INACTIVE", "INACTIVE", "GEN_INACTIVE"]

        for fb in fallbacks:
            stmt = select(StatusMaster.status_id).where(
                func.upper(StatusMaster.status_code) == fb
            )
            val = (await self.db.execute(stmt)).scalar_one_or_none()
            if val:
                return val
        return None

    async def create_employee_with_wallet_and_role(
        self,
        data: schemas.CreateEmployeeRequest,
        hashed_password: str,
        default_role_id: uuid.UUID,
        created_by_id: uuid.UUID,
    ) -> Employee:
        now = datetime.now(timezone.utc)

        # 1. Employee
        emp = Employee(
            username=data.username,
            email=data.email,
            password_hash=hashed_password,
            designation_id=data.designation_id,
            department_id=data.department_id,
            manager_id=data.manager_id,
            date_of_joining=data.date_of_joining,
            date_of_birth=data.date_of_birth,
            status_id=data.status_id,
            created_by=created_by_id,
            updated_by=created_by_id,
            created_at=now,
            updated_at=now,
        )
        self.db.add(emp)
        await self.db.flush()

        # 2. Wallet
        wallet = Wallet(
            employee_id=emp.employee_id,
            available_points=0,
            redeemed_points=0,
            total_earned_points=0,
            version=1,
            created_by=created_by_id,
            updated_by=created_by_id,
            created_at=now,
            updated_at=now,
        )
        self.db.add(wallet)

        # 3. Default Role
        emp_role = EmployeeRole(
            employee_id=emp.employee_id,
            role_id=default_role_id,
            is_active=True,
            assigned_by=created_by_id,
            created_by=created_by_id,
            updated_by=created_by_id,
            assigned_at=now,
            created_at=now,
            updated_at=now,
        )
        self.db.add(emp_role)

        await self.db.flush()
        return await self.get_employee_by_id(emp.employee_id)

    async def update_employee(
        self,
        employee_id: uuid.UUID,
        update_fields: dict[str, Any],
        updated_by_id: uuid.UUID,
    ) -> Employee | None:
        now = datetime.now(timezone.utc)
        update_fields["updated_by"] = updated_by_id
        update_fields["updated_at"] = now

        stmt = (
            update(Employee)
            .where(Employee.employee_id == employee_id)
            .values(**update_fields)
        )
        await self.db.execute(stmt)
        return await self.get_employee_by_id(employee_id)

    async def update_status(
        self,
        employee_id: uuid.UUID,
        status_id: uuid.UUID,
        updated_by_id: uuid.UUID,
    ) -> bool:
        stmt = (
            update(Employee)
            .where(Employee.employee_id == employee_id)
            .values(
                status_id=status_id,
                updated_by=updated_by_id,
                updated_at=datetime.now(timezone.utc),
            )
        )
        res = await self.db.execute(stmt)
        return res.rowcount > 0

    async def get_active_counts(self) -> dict[str, int]:
        from dateutil.relativedelta import relativedelta
        now = datetime.now(timezone.utc)
        this_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_month_start = this_month_start - relativedelta(months=1)

        active_stmt = select(StatusMaster.status_id).where(
            StatusMaster.status_code.in_(("ACTIVE", "EMP_ACTIVE", "GEN_ACTIVE"))
        )
        active_status_ids = (await self.db.execute(active_stmt)).scalars().all()
        if not active_status_ids:
            return {"now": 0, "last_month": 0}

        now_stmt = select(func.count(Employee.employee_id)).where(Employee.status_id.in_(active_status_ids))
        last_month_stmt = select(func.count(Employee.employee_id)).where(
            Employee.status_id.in_(active_status_ids),
            Employee.created_at < last_month_start,
        )

        now_count = (await self.db.execute(now_stmt)).scalar() or 0
        last_month_count = (await self.db.execute(last_month_stmt)).scalar() or 0
        return {"now": now_count, "last_month": last_month_count}

    async def get_manager_email(self, employee_id: uuid.UUID) -> str | None:
        mgr = select(Employee.email).where(
            Employee.employee_id == (
                select(Employee.manager_id).where(Employee.employee_id == employee_id).scalar_subquery()
            )
        )
        return (await self.db.execute(mgr)).scalar_one_or_none()

    async def get_departments_with_members(self) -> list[dict[str, Any]]:
        # Fetch active departments ordered alphabetically
        dept_stmt = select(Department).order_by(Department.department_name.asc())
        depts = (await self.db.execute(dept_stmt)).scalars().all()

        # Fetch employees along with designation name
        emp_stmt = (
            select(
                Employee.employee_id,
                Employee.username,
                Employee.department_id,
                Designation.designation_name,
            )
            .outerjoin(Designation, Employee.designation_id == Designation.designation_id)
        )
        emp_rows = (await self.db.execute(emp_stmt)).all()

        members_by_dept: dict[str, list[dict[str, str]]] = {}
        for emp_id, uname, dept_id, desig_name in emp_rows:
            if not dept_id:
                continue
            key = str(dept_id)
            members_by_dept.setdefault(key, []).append({
                "employee_id": str(emp_id),
                "username": uname,
                "designation_name": desig_name or "N/A",
            })

        return [
            {
                "department_id": str(dept.department_id),
                "department_name": dept.department_name,
                "members": members_by_dept.get(str(dept.department_id), []),
            }
            for dept in depts
        ]