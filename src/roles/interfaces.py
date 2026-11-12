"""
src/roles/interfaces.py
───────────────────────
Abstract repository contract for roles, employee role assignments,
and dynamic route permissions.
"""
from __future__ import annotations

import uuid
from typing import Any, Protocol

from src.roles import schemas
from src.roles.models import EmployeeRole, Role, RoutePermission


class IRoleRepository(Protocol):
    # ── Role Management ──────────────────────────────────────
    async def list_roles(self) -> list[Role]: ...

    async def get_role_by_id(self, role_id: uuid.UUID) -> Role | None: ...

    async def get_role_by_code(self, role_code: str) -> Role | None: ...

    async def create_role(
        self, body: schemas.CreateRoleRequest, current_user_id: uuid.UUID
    ) -> Role: ...

    # ── Employee Role Assignments ────────────────────────────
    async def list_active_employee_roles(self) -> list[dict[str, Any]]: ...

    async def get_active_assignment(
        self, employee_id: uuid.UUID, role_id: uuid.UUID
    ) -> EmployeeRole | None: ...

    async def assign_role(
        self,
        employee_id: uuid.UUID,
        role_id: uuid.UUID,
        current_user_id: uuid.UUID,
    ) -> EmployeeRole: ...

    async def revoke_role(
        self,
        employee_role_id: uuid.UUID,
        current_user_id: uuid.UUID,
    ) -> EmployeeRole | None: ...

    # ── Route Permissions ────────────────────────────────────
    async def list_active_route_permissions(self) -> list[dict[str, Any]]: ...

    async def get_route_permission(
        self, route_key: str, role_id: uuid.UUID
    ) -> RoutePermission | None: ...

    async def create_or_reactivate_permission(
        self,
        route_key: str,
        role_id: uuid.UUID,
        title: str | None,
        current_user_id: uuid.UUID,
    ) -> RoutePermission: ...

    async def deactivate_route_permission(
        self,
        permission_id: uuid.UUID,
        current_user_id: uuid.UUID,
    ) -> RoutePermission | None: ...

    async def update_route_titles(
        self,
        route_key: str,
        title: str,
        current_user_id: uuid.UUID,
    ) -> tuple[int, uuid.UUID | None]: ...

    async def get_employee_route_keys(
        self, employee_id: uuid.UUID
    ) -> list[str]: ...