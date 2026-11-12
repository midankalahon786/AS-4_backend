"""
src/employees/router.py
───────────────────────
Public and Admin-protected Employee routes.
"""
from __future__ import annotations

from uuid import UUID
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from src.common.dependencies import CurrentUser, check_route_permission
from src.employees import schemas
from src.employees.dependencies import get_employee_service
from src.employees.service import EmployeeService

router = APIRouter()

# ── Static routes MUST come before /{employee_id} wildcard ───────────────────[cite: 14]

@router.get("/list", response_model=schemas.EmployeeListResponse)
async def get_employees(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    department_id: UUID | None = None,
    designation_id: UUID | None = None,
    status_id: UUID | None = None,
    manager_id: UUID | None = None,
    is_active: bool | None = None,
    search: str | None = None,
    sort_by: Literal["created_at", "username", "date_of_joining"] = Query("created_at"),
    sort_order: Literal["asc", "desc"] = Query("desc"),
    current_user: CurrentUser = Depends(check_route_permission),
    service: EmployeeService = Depends(get_employee_service),
):
    """Retrieve paginated list of employees."""
    return await service.list_employees(
        page=page,
        limit=limit,
        department_id=department_id,
        designation_id=designation_id,
        status_id=status_id,
        manager_id=manager_id,
        is_active=is_active,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.post("/create", response_model=schemas.EmployeeCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_employee(
    request: Request,
    payload: schemas.CreateEmployeeRequest,
    current_user: CurrentUser = Depends(check_route_permission),
    service: EmployeeService = Depends(get_employee_service),
):
    """Create a new employee[cite: 14]."""
    return await service.create_employee(
        data=payload,
        created_by_id=UUID(str(current_user.id)),
        request=request,
    )


# ── Wildcard routes LAST ──────────────────────────────────────────────────────[cite: 14]

@router.get("/{employee_id}", response_model=schemas.EmployeeDetailResponse)
async def get_employee_by_id(
    employee_id: UUID,
    current_user: CurrentUser = Depends(check_route_permission),
    service: EmployeeService = Depends(get_employee_service),
):
    """Retrieve detailed employee info."""
    return await service.get_employee_detail(employee_id)


@router.put("/{employee_id}", response_model=schemas.EmployeeDetailResponse)
async def update_employee(
    request: Request,
    employee_id: UUID,
    payload: schemas.UpdateEmployeeRequest,
    current_user: CurrentUser = Depends(check_route_permission),
    service: EmployeeService = Depends(get_employee_service),
):
    """Update employee[cite: 14]."""
    return await service.update_employee(
        employee_id=employee_id,
        data=payload,
        updated_by_id=UUID(str(current_user.id)),
        request=request,
    )


@router.patch("/{employee_id}", status_code=status.HTTP_204_NO_CONTENT)
async def patch_employee(
    request: Request,
    employee_id: UUID,
    payload: schemas.UpdateEmployeeRequest | None = None,
    current_user: CurrentUser = Depends(check_route_permission),
    service: EmployeeService = Depends(get_employee_service),
):
    """Partially update, activate, or deactivate employee."""
    if payload is not None and payload.is_active is True:
        await service.activate_employee(
            employee_id=employee_id,
            updated_by_id=UUID(str(current_user.id)),
            request=request,
        )
    elif payload is not None and payload.is_active is False:
        await service.deactivate_employee(
            employee_id=employee_id,
            updated_by_id=UUID(str(current_user.id)),
            request=request,
        )
    elif payload is not None and any(v is not None for v in payload.model_dump(exclude_unset=True).values()):
        await service.update_employee(
            employee_id=employee_id,
            data=payload,
            updated_by_id=UUID(str(current_user.id)),
            request=request,
        )
    else:
        # Default behavior with empty/no body: soft delete / deactivate
        await service.deactivate_employee(
            employee_id=employee_id,
            updated_by_id=UUID(str(current_user.id)),
            request=request,
        )


@router.post("/{employee_id}/activate", status_code=status.HTTP_204_NO_CONTENT)
@router.patch("/{employee_id}/activate", status_code=status.HTTP_204_NO_CONTENT)
async def activate_employee_route(
    request: Request,
    employee_id: UUID,
    current_user: CurrentUser = Depends(check_route_permission),
    service: EmployeeService = Depends(get_employee_service),
):
    """Explicitly activate employee."""
    await service.activate_employee(
        employee_id=employee_id,
        updated_by_id=UUID(str(current_user.id)),
        request=request,
    )


@router.post("/{employee_id}/deactivate", status_code=status.HTTP_204_NO_CONTENT)
@router.patch("/{employee_id}/deactivate", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_employee_route(
    request: Request,
    employee_id: UUID,
    current_user: CurrentUser = Depends(check_route_permission),
    service: EmployeeService = Depends(get_employee_service),
):
    """Explicitly deactivate employee."""
    await service.deactivate_employee(
        employee_id=employee_id,
        updated_by_id=UUID(str(current_user.id)),
        request=request,
    )