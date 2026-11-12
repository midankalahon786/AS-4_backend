"""
src/roles/repository.py
───────────────────────
SQLAlchemy 2.0 implementation of IRoleRepository.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.employees.models import Employee
from src.roles import schemas
from src.roles.models import EmployeeRole, Role, RoutePermission


class SQLAlchemyRoleRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Role Management ──────────────────────────────────────

    async def list_roles(self) -> list[Role]:
        stmt = select(Role).order_by(Role.role_name.asc())
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_role_by_id(self, role_id: uuid.UUID) -> Role | None:
        stmt = select(Role).where(Role.role_id == role_id)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_role_by_code(self, role_code: str) -> Role | None:
        stmt = select(Role).where(
            func.upper(Role.role_code) == role_code.strip().upper()
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def create_role(
        self, body: schemas.CreateRoleRequest, current_user_id: uuid.UUID
    ) -> Role:
        now = datetime.now(timezone.utc)
        role = Role(
            role_name=body.role_name.strip(),
            role_code=body.role_code.strip().upper(),
            description=body.description,
            reviewer_weight=body.reviewer_weight,
            created_by=current_user_id,
            updated_by=current_user_id,
            created_at=now,
            updated_at=now,
        )
        self.db.add(role)
        await self.db.flush()
        return role

    # ── Employee Role Assignments ────────────────────────────

    async def list_active_employee_roles(self) -> list[dict[str, Any]]:
        stmt = (
            select(EmployeeRole)
            .options(
                joinedload(EmployeeRole.employee),
                joinedload(EmployeeRole.role),
            )
            .where(EmployeeRole.is_active.is_(True))
            .order_by(EmployeeRole.assigned_at.desc())
        )
        rows = (await self.db.execute(stmt)).scalars().all()

        data = []
        for r in rows:
            data.append({
                "employee_role_id": str(r.employee_role_id),
                "assigned_at": r.assigned_at.isoformat() if r.assigned_at else None,
                "is_active": r.is_active,
                "employee": {
                    "id": str(r.employee.employee_id),
                    "username": r.employee.username,
                    "email": r.employee.email,
                } if r.employee else None,
                "role": {
                    "id": str(r.role.role_id),
                    "name": r.role.role_name,
                    "code": r.role.role_code,
                } if r.role else None,
            })
        return data

    async def get_active_assignment(
        self, employee_id: uuid.UUID, role_id: uuid.UUID
    ) -> EmployeeRole | None:
        stmt = select(EmployeeRole).where(
            EmployeeRole.employee_id == employee_id,
            EmployeeRole.role_id == role_id,
            EmployeeRole.is_active.is_(True),
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def assign_role(
        self,
        employee_id: uuid.UUID,
        role_id: uuid.UUID,
        current_user_id: uuid.UUID,
    ) -> EmployeeRole:
        now = datetime.now(timezone.utc)
        record = EmployeeRole(
            employee_id=employee_id,
            role_id=role_id,
            is_active=True,
            assigned_at=now,
            assigned_by=current_user_id,
            created_by=current_user_id,
            updated_by=current_user_id,
            created_at=now,
            updated_at=now,
        )
        self.db.add(record)
        await self.db.flush()
        return record

    async def revoke_role(
        self,
        employee_role_id: uuid.UUID,
        current_user_id: uuid.UUID,
    ) -> EmployeeRole | None:
        now = datetime.now(timezone.utc)
        stmt = (
            update(EmployeeRole)
            .where(EmployeeRole.employee_role_id == employee_role_id)
            .values(
                is_active=False,
                revoked_at=now,
                revoked_by=current_user_id,
                updated_by=current_user_id,
                updated_at=now,
            )
        )
        await self.db.execute(stmt)

        fetch_stmt = select(EmployeeRole).where(
            EmployeeRole.employee_role_id == employee_role_id
        )
        return (await self.db.execute(fetch_stmt)).scalar_one_or_none()

    # ── Route Permissions ────────────────────────────────────

    async def list_active_route_permissions(self) -> list[dict[str, Any]]:
        stmt = (
            select(RoutePermission)
            .options(joinedload(RoutePermission.role))
            .where(RoutePermission.is_active.is_(True))
            .order_by(RoutePermission.route_key.asc())
        )
        rows = (await self.db.execute(stmt)).scalars().all()

        grouped: dict[str, dict[str, Any]] = {}
        for row in rows:
            key = row.route_key
            if key not in grouped:
                grouped[key] = {
                    "route_key": key,
                    "title": row.title,
                    "roles": [],
                }
            elif row.title and not grouped[key]["title"]:
                grouped[key]["title"] = row.title

            if row.role:
                grouped[key]["roles"].append({
                    "role_id": str(row.role_id),
                    "role_code": row.role.role_code,
                    "role_name": row.role.role_name,
                })

        return list(grouped.values())

    async def get_route_permission(
        self, route_key: str, role_id: uuid.UUID
    ) -> RoutePermission | None:
        stmt = select(RoutePermission).where(
            RoutePermission.route_key == route_key,
            RoutePermission.role_id == role_id,
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def create_or_reactivate_permission(
        self,
        route_key: str,
        role_id: uuid.UUID,
        title: str | None,
        current_user_id: uuid.UUID,
    ) -> RoutePermission:
        now = datetime.now(timezone.utc)
        existing = await self.get_route_permission(route_key, role_id)

        if existing:
            stmt = (
                update(RoutePermission)
                .where(RoutePermission.id == existing.id)
                .values(
                    is_active=True,
                    title=title or existing.title,
                    updated_by=current_user_id,
                    updated_at=now,
                )
            )
            await self.db.execute(stmt)
            refreshed = await select(RoutePermission).where(RoutePermission.id == existing.id)
            return (await self.db.execute(refreshed)).scalar_one()

        record = RoutePermission(
            route_key=route_key,
            role_id=role_id,
            title=title,
            is_active=True,
            created_by=current_user_id,
            updated_by=current_user_id,
            created_at=now,
            updated_at=now,
        )
        self.db.add(record)
        await self.db.flush()
        return record

    async def deactivate_route_permission(
        self,
        permission_id: uuid.UUID,
        current_user_id: uuid.UUID,
    ) -> RoutePermission | None:
        now = datetime.now(timezone.utc)
        stmt = (
            update(RoutePermission)
            .where(RoutePermission.id == permission_id)
            .values(
                is_active=False,
                updated_by=current_user_id,
                updated_at=now,
            )
        )
        await self.db.execute(stmt)
        refreshed = select(RoutePermission).where(RoutePermission.id == permission_id)
        return (await self.db.execute(refreshed)).scalar_one_or_none()

    async def update_route_titles(
        self,
        route_key: str,
        title: str,
        current_user_id: uuid.UUID,
    ) -> tuple[int, uuid.UUID | None]:
        now = datetime.now(timezone.utc)
        find_stmt = select(RoutePermission.id).where(
            RoutePermission.route_key == route_key
        )
        ids = list((await self.db.execute(find_stmt)).scalars().all())
        if not ids:
            return 0, None

        stmt = (
            update(RoutePermission)
            .where(RoutePermission.route_key == route_key)
            .values(
                title=title,
                updated_by=current_user_id,
                updated_at=now,
            )
        )
        res = await self.db.execute(stmt)
        return res.rowcount, ids[0]

    async def get_employee_route_keys(
        self, employee_id: uuid.UUID
    ) -> list[str]:
        stmt = (
            select(RoutePermission.route_key)
            .join(EmployeeRole, EmployeeRole.role_id == RoutePermission.role_id)
            .where(
                EmployeeRole.employee_id == employee_id,
                EmployeeRole.is_active.is_(True),
                RoutePermission.is_active.is_(True),
            )
            .distinct()
        )
        return list((await self.db.execute(stmt)).scalars().all())