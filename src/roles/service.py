"""
src/roles/service.py
────────────────────
Role management and route permission service.
Decoupled via IRoleRepository and PostgreSQL AsyncSession.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any
from uuid import UUID

from fastapi import HTTPException, Request, status

from src.common.audit import audit, audit_ctx
from src.common.cache import (
    L1_MEDIUM,
    L1_PERMANENT,
    L1_VOLATILE,
    TTL_MEDIUM,
    TTL_PERMANENT,
    TTL_VOLATILE,
    cache_delete,
    cache_get,
    cache_set,
)
from src.common.dependencies import CurrentUser
from src.roles import schemas
from src.roles.interfaces import IRoleRepository

logger = logging.getLogger(__name__)

_KEY_ROLES = "roles:list"
_KEY_EMP_ROLES = "roles:employees"
_KEY_PERMISSIONS = "roles:route_permissions"


async def invalidate_roles() -> None:
    await cache_delete(_KEY_ROLES)


async def invalidate_employee_roles() -> None:
    await cache_delete(_KEY_EMP_ROLES)


async def invalidate_permissions() -> None:
    await cache_delete(_KEY_PERMISSIONS)


class RoleService:
    def __init__(self, repo: IRoleRepository) -> None:
        self.repo = repo

    # ── Roles ─────────────────────────────────────────────────────────────────

    async def list_roles(self) -> list[schemas.RoleResponse]:
        cached = await cache_get(_KEY_ROLES, l1_ttl=L1_MEDIUM)
        if cached is not None:
            return [schemas.RoleResponse(**r) for r in cached]

        rows = await self.repo.list_roles()
        result = [schemas.RoleResponse.model_validate(r) for r in rows]
        await cache_set(
            _KEY_ROLES,
            [r.model_dump(mode="json") for r in result],
            ttl=TTL_MEDIUM,
            l1_ttl=L1_MEDIUM,
        )
        return result

    async def create_role(
        self,
        body: schemas.CreateRoleRequest,
        current_user: CurrentUser,
        request: Request | None = None,
    ) -> schemas.RoleResponse:
        user_id = UUID(str(current_user.id))
        existing = await self.repo.get_role_by_code(body.role_code)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Role '{body.role_code}' already exists",
            )

        result = None
        async with audit_ctx(
            user_id=str(user_id),
            request=request,
            table_name="roles",
            record_id=lambda: str(result.role_id) if result else "UNKNOWN",
            operation="INSERT",
            new_values=lambda: {
                "role_name": body.role_name,
                "role_code": body.role_code,
                "reviewer_weight": body.reviewer_weight,
            },
        ):
            result = await self.repo.create_role(body, user_id)

        await invalidate_roles()
        return schemas.RoleResponse.model_validate(result)

    # ── Employee ↔ Role ───────────────────────────────────────────────────────

    async def list_employee_roles(self) -> list[dict[str, Any]]:
        cached = await cache_get(_KEY_EMP_ROLES, l1_ttl=L1_VOLATILE)
        if cached is not None:
            return cached

        data = await self.repo.list_active_employee_roles()
        await cache_set(_KEY_EMP_ROLES, data, ttl=TTL_VOLATILE, l1_ttl=L1_VOLATILE)
        return data

    async def assign_role(
        self,
        body: schemas.AssignRoleRequest,
        current_user: CurrentUser,
        request: Request | None = None,
    ) -> schemas.EmployeeRoleResponse:
        user_id = UUID(str(current_user.id))
        existing = await self.repo.get_active_assignment(
            body.employee_id, body.role_id
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Employee already has this role",
            )

        result = None
        async with audit_ctx(
            user_id=str(user_id),
            request=request,
            table_name="employee_roles",
            record_id=lambda: str(result.employee_role_id) if result else "UNKNOWN",
            operation="INSERT",
            new_values=lambda: {
                "employee_id": str(body.employee_id),
                "role_id": str(body.role_id),
                "assigned_by": str(user_id),
            },
        ):
            result = await self.repo.assign_role(
                body.employee_id, body.role_id, user_id
            )

        await invalidate_employee_roles()
        return schemas.EmployeeRoleResponse.model_validate(result)

    async def revoke_role(
        self,
        body: schemas.RevokeRoleRequest,
        current_user: CurrentUser,
        request: Request | None = None,
    ) -> schemas.EmployeeRoleResponse:
        user_id = UUID(str(current_user.id))
        record = await self.repo.get_active_assignment(
            body.employee_id, body.role_id
        )
        if not record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Active role assignment not found",
            )

        result = None
        async with audit_ctx(
            user_id=str(user_id),
            request=request,
            table_name="employee_roles",
            record_id=str(record.employee_role_id),
            operation="REVOKE",
            old_values={
                "is_active": True,
                "employee_id": str(body.employee_id),
                "role_id": str(body.role_id),
            },
            new_values=lambda: {"is_active": False, "revoked_by": str(user_id)},
        ):
            result = await self.repo.revoke_role(
                record.employee_role_id, user_id
            )

        await invalidate_employee_roles()
        return schemas.EmployeeRoleResponse.model_validate(result)

    # ── Route Permissions ─────────────────────────────────────────────────────

    async def list_route_permissions(self) -> list[dict[str, Any]]:
        cached = await cache_get(_KEY_PERMISSIONS, l1_ttl=L1_PERMANENT)
        if cached is not None:
            return cached

        data = await self.repo.list_active_route_permissions()
        await cache_set(
            _KEY_PERMISSIONS, data, ttl=TTL_PERMANENT, l1_ttl=L1_PERMANENT
        )
        return data

    async def add_route_permission(
        self,
        body: schemas.SetRoutePermissionRequest,
        current_user: CurrentUser,
        request: Request | None = None,
    ) -> schemas.RoutePermissionResponse:
        user_id = UUID(str(current_user.id))
        existing = await self.repo.get_route_permission(
            body.route_key, body.role_id
        )
        if existing and existing.is_active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Permission already exists and is active",
            )

        result = None
        async with audit_ctx(
            user_id=str(user_id),
            request=request,
            table_name="route_permissions",
            record_id=lambda: str(result.id) if result else "UNKNOWN",
            operation="INSERT",
            new_values=lambda: {
                "route_key": body.route_key,
                "role_id": str(body.role_id),
                "is_active": True,
            },
        ):
            result = await self.repo.create_or_reactivate_permission(
                route_key=body.route_key,
                role_id=body.role_id,
                title=body.title,
                current_user_id=user_id,
            )

        await invalidate_permissions()
        return schemas.RoutePermissionResponse(
            permission_id=result.id,
            route_key=result.route_key,
            role_id=result.role_id,
            title=result.title,
        )

    async def remove_route_permission(
        self,
        body: schemas.DeleteRoutePermissionRequest,
        current_user: CurrentUser,
        request: Request | None = None,
    ) -> dict[str, str]:
        user_id = UUID(str(current_user.id))
        record = await self.repo.get_route_permission(
            body.route_key, body.role_id
        )
        if not record or not record.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Active permission not found",
            )

        async with audit_ctx(
            user_id=str(user_id),
            request=request,
            table_name="route_permissions",
            record_id=str(record.id),
            operation="DELETE",
            old_values={
                "route_key": body.route_key,
                "role_id": str(body.role_id),
                "is_active": True,
            },
            new_values=lambda: {"is_active": False},
        ):
            await self.repo.deactivate_route_permission(record.id, user_id)

        await invalidate_permissions()
        return {"message": "Permission revoked successfully"}

    async def update_route_title(
        self,
        body: schemas.UpdateRouteTitleRequest,
        current_user: CurrentUser,
        request: Request | None = None,
    ) -> dict[str, Any]:
        user_id = UUID(str(current_user.id))
        count, first_id = await self.repo.update_route_titles(
            body.route_key, body.title, user_id
        )
        if count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No permissions found for this route_key",
            )

        await audit(
            table_name="route_permissions",
            record_id=str(first_id),
            operation="UPDATE",
            performed_by=str(user_id),
            new_values={"route_key": body.route_key, "title": body.title},
            request=request,
        )

        await invalidate_permissions()
        return {
            "route_key": body.route_key,
            "title": body.title,
            "updated_rows": count,
        }

    async def get_my_permissions(self, current_user: CurrentUser) -> list[str]:
        user_id = UUID(str(current_user.id))
        return await self.repo.get_employee_route_keys(user_id)