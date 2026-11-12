"""
src/roles/router.py
───────────────────
API routes for role creation, employee role assignment, and dynamic route permissions.
Powered by RoleService with SQLAlchemy 2.0 async session dependency injection.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, status

from src.common.dependencies import CurrentUser, check_route_permission, get_current_user
from src.roles import schemas
from src.roles.dependencies import get_role_service
from src.roles.service import RoleService

router = APIRouter(tags=["Role Management"])


# ══════════════════════════════════════════════════════════════
#  Roles
# ══════════════════════════════════════════════════════════════

@router.get(
    "/list",
    response_model=list[schemas.RoleResponse],
    summary="List Roles",
)
async def list_roles(
    current_user: CurrentUser = Depends(check_route_permission),
    service: RoleService = Depends(get_role_service),
):
    return await service.list_roles()


@router.post(
    "/create",
    response_model=schemas.RoleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Role",
)
async def create_role(
    request: Request,
    body: schemas.CreateRoleRequest,
    current_user: CurrentUser = Depends(check_route_permission),
    service: RoleService = Depends(get_role_service),
):
    return await service.create_role(body, current_user, request=request)


# ══════════════════════════════════════════════════════════════
#  Employee ↔ Role
# ══════════════════════════════════════════════════════════════

@router.get(
    "/employees",
    response_model=list[dict[str, Any]],
    summary="List Active Employee Role Assignments",
)
async def list_employee_roles(
    current_user: CurrentUser = Depends(check_route_permission),
    service: RoleService = Depends(get_role_service),
):
    return await service.list_employee_roles()


@router.post(
    "/assign",
    response_model=schemas.EmployeeRoleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Assign Role to Employee",
)
async def assign_role(
    request: Request,
    body: schemas.AssignRoleRequest,
    current_user: CurrentUser = Depends(check_route_permission),
    service: RoleService = Depends(get_role_service),
):
    return await service.assign_role(body, current_user, request=request)


@router.post(
    "/revoke",
    response_model=schemas.EmployeeRoleResponse,
    summary="Revoke Role from Employee",
)
async def revoke_role(
    request: Request,
    body: schemas.RevokeRoleRequest,
    current_user: CurrentUser = Depends(check_route_permission),
    service: RoleService = Depends(get_reward_service if False else get_role_service),
):
    return await service.revoke_role(body, current_user, request=request)


# ══════════════════════════════════════════════════════════════
#  Route Permissions
# ══════════════════════════════════════════════════════════════

@router.get(
    "/route-permissions",
    response_model=list[dict[str, Any]],
    summary="List Dynamic Route Permissions",
)
async def list_route_permissions(
    current_user: CurrentUser = Depends(check_route_permission),
    service: RoleService = Depends(get_role_service),
):
    return await service.list_route_permissions()


@router.post(
    "/route-permissions",
    response_model=schemas.RoutePermissionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add or Reactivate Route Permission",
)
async def add_route_permission(
    request: Request,
    body: schemas.SetRoutePermissionRequest,
    current_user: CurrentUser = Depends(check_route_permission),
    service: RoleService = Depends(get_role_service),
):
    return await service.add_route_permission(body, current_user, request=request)


@router.patch(
    "/route-permissions",
    summary="Remove Route Permission",
)
async def remove_route_permission(
    request: Request,
    body: schemas.DeleteRoutePermissionRequest,
    current_user: CurrentUser = Depends(check_route_permission),
    service: RoleService = Depends(get_role_service),
):
    return await service.remove_route_permission(body, current_user, request=request)


@router.patch(
    "/route-permissions/title",
    summary="Update Route Display Title",
)
async def update_route_title(
    request: Request,
    body: schemas.UpdateRouteTitleRequest,
    current_user: CurrentUser = Depends(check_route_permission),
    service: RoleService = Depends(get_role_service),
):
    return await service.update_route_title(body, current_user, request=request)


@router.get(
    "/my-permissions",
    response_model=list[str],
    summary="Get Accessible Route Keys for Current User",
)
async def get_my_permissions(
    current_user: CurrentUser = Depends(get_current_user),
    service: RoleService = Depends(get_role_service),
):
    """Returns route keys available to the current user to configure client-side navigation."""
    return await service.get_my_permissions(current_user)