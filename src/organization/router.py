"""
src/organization/router.py
──────────────────────────
Routers for Departments, Designations, Department Types, Status Master, and Audit Logs.
Powered by OrganizationService with SQLAlchemy 2.0 async session dependency injection.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status

from src.common.dependencies import CurrentUser, check_route_permission
from src.organization import schemas
from src.organization.dependencies import get_organization_service
from src.organization.service import OrganizationService

departments_router = APIRouter()
designations_router = APIRouter()
department_types_router = APIRouter()
statuses_router = APIRouter()
audit_logs_router = APIRouter()


# ══════════════════════════════════════════════
#  DEPARTMENT ROUTES
# ══════════════════════════════════════════════

@departments_router.get("", response_model=schemas.DepartmentListResponse)
async def list_departments(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    is_active: bool | None = None,
    search: str | None = None,
    current_user: CurrentUser = Depends(check_route_permission),
    service: OrganizationService = Depends(get_organization_service),
):
    return await service.list_departments(
        page=page,
        limit=limit,
        is_active=is_active,
        search=search,
    )


@departments_router.get("/{department_id}", response_model=schemas.DepartmentDetailResponse)
async def get_department(
    department_id: UUID,
    current_user: CurrentUser = Depends(check_route_permission),
    service: OrganizationService = Depends(get_organization_service),
):
    return await service.get_department_detail(department_id)


@departments_router.post(
    "",
    response_model=schemas.DepartmentCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_department(
    request: Request,
    payload: schemas.CreateDepartmentRequest,
    current_user: CurrentUser = Depends(check_route_permission),
    service: OrganizationService = Depends(get_organization_service),
):
    return await service.create_department(
        data=payload,
        created_by_id=UUID(str(current_user.id)),
        request=request,
    )


@departments_router.put("/{department_id}", response_model=schemas.DepartmentUpdatedResponse)
async def update_department(
    request: Request,
    department_id: UUID,
    payload: schemas.UpdateDepartmentRequest,
    current_user: CurrentUser = Depends(check_route_permission),
    service: OrganizationService = Depends(get_organization_service),
):
    return await service.update_department(
        department_id=department_id,
        data=payload,
        updated_by_id=UUID(str(current_user.id)),
        request=request,
    )


# ══════════════════════════════════════════════
#  DESIGNATION ROUTES
# ══════════════════════════════════════════════

@designations_router.get("", response_model=schemas.DesignationListResponse)
async def list_designations(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    is_active: bool | None = None,
    current_user: CurrentUser = Depends(check_route_permission),
    service: OrganizationService = Depends(get_organization_service),
):
    return await service.list_designations(
        page=page,
        limit=limit,
        is_active=is_active,
    )


@designations_router.get("/{designation_id}", response_model=schemas.DesignationDetailResponse)
async def get_designation(
    designation_id: UUID,
    current_user: CurrentUser = Depends(check_route_permission),
    service: OrganizationService = Depends(get_organization_service),
):
    return await service.get_designation_detail(designation_id)


@designations_router.post(
    "",
    response_model=schemas.DesignationListItem,
    status_code=status.HTTP_201_CREATED,
)
async def create_designation(
    request: Request,
    payload: schemas.CreateDesignationRequest,
    current_user: CurrentUser = Depends(check_route_permission),
    service: OrganizationService = Depends(get_organization_service),
):
    return await service.create_designation(
        data=payload,
        created_by_id=UUID(str(current_user.id)),
        request=request,
    )


@designations_router.put("/{designation_id}", response_model=schemas.DesignationDetailResponse)
async def update_designation(
    request: Request,
    designation_id: UUID,
    payload: schemas.UpdateDesignationRequest,
    current_user: CurrentUser = Depends(check_route_permission),
    service: OrganizationService = Depends(get_organization_service),
):
    return await service.update_designation(
        designation_id=designation_id,
        data=payload,
        updated_by_id=UUID(str(current_user.id)),
        request=request,
    )


# ══════════════════════════════════════════════
#  DEPARTMENT TYPES ROUTE
# ══════════════════════════════════════════════

@department_types_router.get("", response_model=list[schemas.DepartmentTypeResponse])
async def get_all_department_types(
    current_user: CurrentUser = Depends(check_route_permission),
    service: OrganizationService = Depends(get_organization_service),
):
    return await service.list_department_types()


# ══════════════════════════════════════════════
#  STATUS MASTER ROUTES
# ══════════════════════════════════════════════

@statuses_router.get("", response_model=list[schemas.StatusResponse])
async def list_statuses(
    entity_type: str | None = Query(None),
    current_user: CurrentUser = Depends(check_route_permission),
    service: OrganizationService = Depends(get_organization_service),
):
    return await service.list_statuses(entity_type)


@statuses_router.get("/{status_id}", response_model=schemas.StatusDetailResponse)
async def get_status(
    status_id: UUID,
    current_user: CurrentUser = Depends(check_route_permission),
    service: OrganizationService = Depends(get_organization_service),
):
    return await service.get_status(status_id)


@statuses_router.post(
    "",
    response_model=schemas.StatusDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_status(
    request: Request,
    payload: schemas.CreateStatusRequest,
    current_user: CurrentUser = Depends(check_route_permission),
    service: OrganizationService = Depends(get_organization_service),
):
    return await service.create_status(
        data=payload,
        created_by_id=UUID(str(current_user.id)),
        request=request,
    )


@statuses_router.put("/{status_id}", response_model=schemas.StatusDetailResponse)
async def update_status(
    request: Request,
    status_id: UUID,
    payload: schemas.UpdateStatusRequest,
    current_user: CurrentUser = Depends(check_route_permission),
    service: OrganizationService = Depends(get_organization_service),
):
    return await service.update_status(
        status_id=status_id,
        data=payload,
        updated_by_id=UUID(str(current_user.id)),
        request=request,
    )


# ══════════════════════════════════════════════
#  AUDIT LOGS ROUTES (Read-Only Viewer)
# ══════════════════════════════════════════════

@audit_logs_router.get("", response_model=schemas.AuditLogListResponse)
async def list_audit_logs(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    table_name: str | None = None,
    record_id: UUID | None = None,
    operation_type: str | None = None,
    performed_by: UUID | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    current_user: CurrentUser = Depends(check_route_permission),
    service: OrganizationService = Depends(get_organization_service),
):
    return await service.list_audit_logs(
        page=page,
        limit=limit,
        table_name=table_name,
        record_id=record_id,
        operation_type=operation_type,
        performed_by=performed_by,
        start_date=start_date,
        end_date=end_date,
    )


@audit_logs_router.get("/{audit_id}", response_model=schemas.AuditLogResponse)
async def get_audit_log(
    audit_id: UUID,
    current_user: CurrentUser = Depends(check_route_permission),
    service: OrganizationService = Depends(get_organization_service),
):
    return await service.get_audit_log(audit_id)