"""
src/employees/internal_router.py
──────────────────────────────────
Internal-only endpoints consumed by the Analytics service.
Routes are written as /internal/employees/... with NO APIRouter prefix.
"""
from __future__ import annotations

from uuid import UUID
from fastapi import APIRouter, Depends

from src.employees.dependencies import get_employee_service
from src.employees.service import EmployeeService

router = APIRouter(tags=["Internal"])


@router.get("/internal/employees/active-count")
async def active_employee_count(
    service: EmployeeService = Depends(get_employee_service),
):
    """Returns {now: int, last_month: int} for the Analytics dashboard active_users KPI[cite: 13]."""
    return await service.get_active_counts()


@router.get("/internal/employees/{employee_id}/manager-email")
async def get_manager_email(
    employee_id: UUID,
    service: EmployeeService = Depends(get_employee_service),
):
    email = await service.get_manager_email(employee_id)
    return {"email": email}


@router.get("/internal/employees/departments-with-members")
async def departments_with_members(
    service: EmployeeService = Depends(get_employee_service),
):
    """Returns all departments with member lists for team reports[cite: 13]."""
    return await service.get_departments_with_members()