"""
src/organization/repository.py
───────────────────────────────
SQLAlchemy 2.0 implementation of IOrganizationRepository.
"""
from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, joinedload

from src.analytics.models import AuditLog
from src.employees.models import Employee, Designation, StatusMaster
from src.organization import schemas
from src.organization.models import (
    Department,
    DepartmentType
    
)


class SQLAlchemyOrganizationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Department Types ─────────────────────────────────────
    async def list_department_types(self) -> list[DepartmentType]:
        stmt = select(DepartmentType).order_by(DepartmentType.type_name.asc())
        res = await self.db.execute(stmt)
        return list(res.scalars().all())

    async def get_department_type_by_id(
        self, department_type_id: uuid.UUID
    ) -> DepartmentType | None:
        stmt = select(DepartmentType).where(
            DepartmentType.department_type_id == department_type_id
        )
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    # ── Departments ──────────────────────────────────────────
    async def list_departments(
        self,
        page: int,
        limit: int,
        is_active: bool | None,
        search: str | None,
    ) -> schemas.DepartmentListResponse:
        creator_alias = aliased(Employee)
        updater_alias = aliased(Employee)

        stmt = (
            select(
                Department,
                creator_alias.username.label("creator_name"),
                creator_alias.email.label("creator_email"),
                updater_alias.username.label("updater_name"),
                updater_alias.email.label("updater_email"),
            )
            .options(joinedload(Department.department_type))
            .outerjoin(creator_alias, Department.created_by == creator_alias.employee_id)
            .outerjoin(updater_alias, Department.updated_by == updater_alias.employee_id)
        )

        filters = []
        if is_active is not None:
            filters.append(Department.is_active == is_active)
        if search:
            cleaned = f"%{search.strip().lower()}%"
            filters.append(
                or_(
                    func.lower(Department.department_name).like(cleaned),
                    func.lower(Department.department_code).like(cleaned),
                )
            )
        if filters:
            stmt = stmt.where(*filters)

        # Count total
        count_query = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.execute(count_query)).scalar() or 0
        total_pages = math.ceil(total / limit) if total else 1
        offset = (page - 1) * limit

        ordered_query = (
            stmt.order_by(Department.created_at.desc()).offset(offset).limit(limit)
        )
        rows = (await self.db.execute(ordered_query)).all()

        data = []
        for dept, c_name, c_email, u_name, u_email in rows:
            dept_type = (
                schemas.DepartmentTypeResponse.model_validate(dept.department_type)
                if dept.department_type
                else None
            )
            creator_info = (
                schemas.ManagerBriefResponse(
                    employee_id=dept.created_by,
                    username=c_name,
                    email=c_email,
                )
                if dept.created_by and c_name
                else None
            )
            updater_info = (
                schemas.ManagerBriefResponse(
                    employee_id=dept.updated_by,
                    username=u_name,
                    email=u_email,
                )
                if dept.updated_by and u_name
                else None
            )

            data.append(
                schemas.DepartmentListItem(
                    department_id=dept.department_id,
                    department_name=dept.department_name,
                    department_code=dept.department_code,
                    department_type=dept_type,
                    is_active=dept.is_active,
                    created_at=dept.created_at,
                    created_by=dept.created_by,
                    created_by_info=creator_info,
                    updated_by=dept.updated_by,
                    updated_by_info=updater_info,
                )
            )

        return schemas.DepartmentListResponse(
            data=data,
            pagination=schemas.PaginationMeta(
                current_page=page,
                per_page=limit,
                total=total,
                total_pages=total_pages,
                has_next=page < total_pages,
                has_previous=page > 1,
            ),
        )

    async def get_department_detail(
        self, department_id: uuid.UUID
    ) -> schemas.DepartmentDetailResponse | None:
        creator_alias = aliased(Employee)
        updater_alias = aliased(Employee)

        stmt = (
            select(
                Department,
                creator_alias.username.label("creator_name"),
                creator_alias.email.label("creator_email"),
                updater_alias.username.label("updater_name"),
                updater_alias.email.label("updater_email"),
            )
            .options(joinedload(Department.department_type))
            .outerjoin(creator_alias, Department.created_by == creator_alias.employee_id)
            .outerjoin(updater_alias, Department.updated_by == updater_alias.employee_id)
            .where(Department.department_id == department_id)
        )
        row = (await self.db.execute(stmt)).first()
        if not row:
            return None

        dept, c_name, c_email, u_name, u_email = row

        emp_count_stmt = select(func.count(Employee.employee_id)).where(
            Employee.department_id == department_id
        )
        emp_count = (await self.db.execute(emp_count_stmt)).scalar() or 0

        dept_type = (
            schemas.DepartmentTypeResponse.model_validate(dept.department_type)
            if dept.department_type
            else None
        )
        creator_info = (
            schemas.ManagerBriefResponse(
                employee_id=dept.created_by,
                username=c_name,
                email=c_email,
            )
            if dept.created_by and c_name
            else None
        )
        updater_info = (
            schemas.ManagerBriefResponse(
                employee_id=dept.updated_by,
                username=u_name,
                email=u_email,
            )
            if dept.updated_by and u_name
            else None
        )

        return schemas.DepartmentDetailResponse(
            department_id=dept.department_id,
            department_name=dept.department_name,
            department_code=dept.department_code,
            department_type=dept_type,
            employee_count=emp_count,
            is_active=dept.is_active,
            created_at=dept.created_at,
            updated_at=dept.updated_at,
            created_by=dept.created_by,
            created_by_info=creator_info,
            updated_by=dept.updated_by,
            updated_by_info=updater_info,
        )

    async def get_department_by_name_or_code(
        self, name: str, code: str
    ) -> Department | None:
        stmt = select(Department).where(
            or_(
                func.lower(Department.department_name) == name.strip().lower(),
                func.upper(Department.department_code) == code.strip().upper(),
            )
        )
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def create_department(
        self,
        data: schemas.CreateDepartmentRequest,
        created_by_id: uuid.UUID,
    ) -> Department:
        now = datetime.now(timezone.utc)
        dept = Department(
            department_name=data.department_name.strip(),
            department_code=data.department_code.strip().upper(),
            department_type_id=data.department_type_id,
            is_active=True,
            created_by=created_by_id,
            updated_by=created_by_id,
            created_at=now,
            updated_at=now,
        )
        self.db.add(dept)
        await self.db.flush()

        stmt = (
            select(Department)
            .options(joinedload(Department.department_type))
            .where(Department.department_id == dept.department_id)
        )
        return (await self.db.execute(stmt)).scalar_one()

    async def update_department(
        self,
        department_id: uuid.UUID,
        update_data: dict[str, Any],
        updated_by_id: uuid.UUID,
    ) -> Department | None:
        now = datetime.now(timezone.utc)
        update_data["updated_by"] = updated_by_id
        update_data["updated_at"] = now

        stmt = (
            update(Department)
            .where(Department.department_id == department_id)
            .values(**update_data)
        )
        await self.db.execute(stmt)

        fetch_stmt = (
            select(Department)
            .options(joinedload(Department.department_type))
            .where(Department.department_id == department_id)
        )
        return (await self.db.execute(fetch_stmt)).scalar_one_or_none()

    # ── Designations ─────────────────────────────────────────
    async def list_designations(
        self,
        page: int,
        limit: int,
        is_active: bool | None,
    ) -> schemas.DesignationListResponse:
        stmt = select(Designation)
        if is_active is not None:
            stmt = stmt.where(Designation.is_active == is_active)

        count_query = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.execute(count_query)).scalar() or 0
        total_pages = math.ceil(total / limit) if total else 1
        offset = (page - 1) * limit

        ordered_query = (
            stmt.order_by(Designation.level.asc()).offset(offset).limit(limit)
        )
        designations = (await self.db.execute(ordered_query)).scalars().all()

        data = [
            schemas.DesignationListItem.model_validate(d) for d in designations
        ]
        return schemas.DesignationListResponse(
            data=data,
            pagination=schemas.PaginationMeta(
                current_page=page,
                per_page=limit,
                total=total,
                total_pages=total_pages,
                has_next=page < total_pages,
                has_previous=page > 1,
            ),
        )

    async def get_designation_detail(
        self, designation_id: uuid.UUID
    ) -> schemas.DesignationDetailResponse | None:
        stmt = select(Designation).where(
            Designation.designation_id == designation_id
        )
        desig = (await self.db.execute(stmt)).scalar_one_or_none()
        if not desig:
            return None

        emp_count_stmt = select(func.count(Employee.employee_id)).where(
            Employee.designation_id == designation_id
        )
        emp_count = (await self.db.execute(emp_count_stmt)).scalar() or 0

        return schemas.DesignationDetailResponse(
            designation_id=desig.designation_id,
            designation_name=desig.designation_name,
            designation_code=desig.designation_code,
            level=desig.level,
            description=desig.description,
            employee_count=emp_count,
            is_active=desig.is_active,
            created_at=desig.created_at,
            updated_at=desig.updated_at,
        )

    async def get_designation_by_name_or_code(
        self, name: str, code: str
    ) -> Designation | None:
        stmt = select(Designation).where(
            or_(
                func.lower(Designation.designation_name) == name.strip().lower(),
                func.upper(Designation.designation_code) == code.strip().upper(),
            )
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def check_designation_code_conflict(
        self, code: str, exclude_id: uuid.UUID
    ) -> bool:
        stmt = select(Designation.designation_id).where(
            func.upper(Designation.designation_code) == code.strip().upper(),
            Designation.designation_id != exclude_id,
        )
        return (await self.db.execute(stmt)).scalar_one_or_none() is not None

    async def create_designation(
        self,
        data: schemas.CreateDesignationRequest,
        created_by_id: uuid.UUID,
    ) -> Designation:
        now = datetime.now(timezone.utc)
        desig = Designation(
            designation_name=data.designation_name.strip(),
            designation_code=data.designation_code.strip().upper(),
            level=data.level,
            description=data.description,
            is_active=True,
            created_by=created_by_id,
            updated_by=created_by_id,
            created_at=now,
            updated_at=now,
        )
        self.db.add(desig)
        await self.db.flush()
        return desig

    async def update_designation(
        self,
        designation_id: uuid.UUID,
        update_data: dict[str, Any],
        updated_by_id: uuid.UUID,
    ) -> Designation | None:
        now = datetime.now(timezone.utc)
        update_data["updated_by"] = updated_by_id
        update_data["updated_at"] = now

        stmt = (
            update(Designation)
            .where(Designation.designation_id == designation_id)
            .values(**update_data)
        )
        await self.db.execute(stmt)

        fetch_stmt = select(Designation).where(
            Designation.designation_id == designation_id
        )
        return (await self.db.execute(fetch_stmt)).scalar_one_or_none()

    # ── Status Master ────────────────────────────────────────
    async def list_statuses(
        self, entity_type: str | None = None
    ) -> list[StatusMaster]:
        stmt = select(StatusMaster)
        if entity_type:
            stmt = stmt.where(StatusMaster.entity_type == entity_type.strip().upper())
        stmt = stmt.order_by(StatusMaster.entity_type.asc(), StatusMaster.status_code.asc())
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_status_by_id(self, status_id: uuid.UUID) -> StatusMaster | None:
        stmt = select(StatusMaster).where(StatusMaster.status_id == status_id)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_status_by_code(self, status_code: str) -> StatusMaster | None:
        stmt = select(StatusMaster).where(
            func.upper(StatusMaster.status_code) == status_code.strip().upper()
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def create_status(
        self,
        data: schemas.CreateStatusRequest,
        created_by_id: uuid.UUID,
    ) -> StatusMaster:
        now = datetime.now(timezone.utc)
        st = StatusMaster(
            status_code=data.status_code.strip().upper(),
            status_name=data.status_name.strip(),
            description=data.description,
            entity_type=data.entity_type.strip().upper(),
            created_by=created_by_id,
            updated_by=created_by_id,
            created_at=now,
            updated_at=now,
        )
        self.db.add(st)
        await self.db.flush()
        return st

    async def update_status(
        self,
        status_id: uuid.UUID,
        update_data: dict[str, Any],
        updated_by_id: uuid.UUID,
    ) -> StatusMaster | None:
        now = datetime.now(timezone.utc)
        update_data["updated_by"] = updated_by_id
        update_data["updated_at"] = now

        stmt = (
            update(StatusMaster)
            .where(StatusMaster.status_id == status_id)
            .values(**update_data)
        )
        await self.db.execute(stmt)

        fetch_stmt = select(StatusMaster).where(StatusMaster.status_id == status_id)
        return (await self.db.execute(fetch_stmt)).scalar_one_or_none()

    # ── Audit Logs ───────────────────────────────────────────
    async def list_audit_logs(
        self,
        page: int,
        limit: int,
        table_name: str | None,
        record_id: uuid.UUID | None,
        operation_type: str | None,
        performed_by: uuid.UUID | None,
        start_date: datetime | None,
        end_date: datetime | None,
    ) -> schemas.AuditLogListResponse:
        performer_alias = aliased(Employee)

        stmt = (
            select(
                AuditLog,
                performer_alias.username.label("employee_name"),
                performer_alias.email.label("employee_email"),
            )
            .outerjoin(performer_alias, AuditLog.performed_by == performer_alias.employee_id)
        )

        filters = []
        if table_name:
            filters.append(func.lower(AuditLog.table_name).like(f"%{table_name.strip().lower()}%"))
        if record_id:
            filters.append(AuditLog.record_id == record_id)
        if operation_type:
            filters.append(func.upper(AuditLog.operation_type).like(f"%{operation_type.strip().upper()}%"))
        if performed_by:
            filters.append(AuditLog.performed_by == performed_by)
        if start_date:
            filters.append(AuditLog.performed_at >= start_date)
        if end_date:
            filters.append(AuditLog.performed_at <= end_date)

        if filters:
            stmt = stmt.where(*filters)

        count_query = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.execute(count_query)).scalar() or 0
        total_pages = math.ceil(total / limit) if total else 1
        offset = (page - 1) * limit

        ordered_query = (
            stmt.order_by(AuditLog.performed_at.desc()).offset(offset).limit(limit)
        )
        rows = (await self.db.execute(ordered_query)).all()

        data = [
            schemas.AuditLogResponse(
                audit_id=log.audit_id,
                table_name=log.table_name,
                record_id=log.record_id,
                operation_type=log.operation_type,
                old_values=log.old_values,
                new_values=log.new_values,
                performed_by=log.performed_by,
                performed_at=log.performed_at,
                ip_address=log.ip_address,
                user_agent=log.user_agent,
                employee_name=emp_name,
                employee_email=emp_email,
            )
            for log, emp_name, emp_email in rows
        ]

        return schemas.AuditLogListResponse(
            data=data,
            pagination=schemas.PaginationMeta(
                current_page=page,
                per_page=limit,
                total=total,
                total_pages=total_pages,
                has_next=page < total_pages,
                has_previous=page > 1,
            ),
        )

    async def get_audit_log(
        self, audit_id: uuid.UUID
    ) -> schemas.AuditLogResponse | None:
        performer_alias = aliased(Employee)
        stmt = (
            select(
                AuditLog,
                performer_alias.username.label("employee_name"),
                performer_alias.email.label("employee_email"),
            )
            .outerjoin(performer_alias, AuditLog.performed_by == performer_alias.employee_id)
            .where(AuditLog.audit_id == audit_id)
        )
        row = (await self.db.execute(stmt)).first()
        if not row:
            return None

        log, emp_name, emp_email = row
        return schemas.AuditLogResponse(
            audit_id=log.audit_id,
            table_name=log.table_name,
            record_id=log.record_id,
            operation_type=log.operation_type,
            old_values=log.old_values,
            new_values=log.new_values,
            performed_by=log.performed_by,
            performed_at=log.performed_at,
            ip_address=log.ip_address,
            user_agent=log.user_agent,
            employee_name=emp_name,
            employee_email=emp_email,
        )