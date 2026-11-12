"""
src/organization/service.py
───────────────────────────
Organization Service layer decoupled via IOrganizationRepository.
Handles Departments, Designations, Statuses, and Audit Viewer.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import HTTPException, Request, status

from src.common.audit import audit_ctx
from src.common.cache import cache_delete, cache_get, cache_set, invalidate_pattern
from src.organization import schemas
from src.organization.interfaces import IOrganizationRepository

logger = logging.getLogger(__name__)

TTL_DEPT_TYPES = 3600
TTL_DEPARTMENTS = 3600
TTL_DESIGNATIONS = 3600


# ── Cache Key Helpers ────────────────────────────────────────[cite: 17]
def _key_dept_types() -> str:
    return "org:department_types"

def _key_depts(page: int, limit: int, is_active: bool | None, search: str | None) -> str:
    return f"org:departments:{page}:{limit}:{is_active}:{search}"

def _key_dept(dept_id: uuid.UUID) -> str:
    return f"org:department:{dept_id}"

def _key_desigs(page: int, limit: int, is_active: bool | None) -> str:
    return f"org:designations:{page}:{limit}:{is_active}"

def _key_desig(desig_id: uuid.UUID) -> str:
    return f"org:designation:{desig_id}"


class OrganizationService:
    def __init__(self, repo: IOrganizationRepository) -> None:
        self.repo = repo

    @staticmethod
    async def invalidate_departments() -> None:
        await invalidate_pattern("org:departments:*")
        await invalidate_pattern("org:department:*")

    @staticmethod
    async def invalidate_designations() -> None:
        await invalidate_pattern("org:designations:*")
        await invalidate_pattern("org:designation:*")

    # ══════════════════════════════════════════════
    #  Department Types
    # ══════════════════════════════════════════════

    async def list_department_types(self) -> list[schemas.DepartmentTypeResponse]:
        key = _key_dept_types()
        cached = await cache_get(key)
        if cached is not None:
            return [schemas.DepartmentTypeResponse(**t) for t in cached]

        types = await self.repo.list_department_types()
        result = [
            schemas.DepartmentTypeResponse(
                department_type_id=t.department_type_id,
                type_name=t.type_name,
                type_code=t.type_code,
            )
            for t in types
        ]
        await cache_set(key, [r.model_dump(mode="json") for r in result], ttl=TTL_DEPT_TYPES)
        return result

    # ══════════════════════════════════════════════
    #  Departments
    # ══════════════════════════════════════════════

    async def list_departments(
        self,
        page: int,
        limit: int,
        is_active: bool | None,
        search: str | None,
    ) -> schemas.DepartmentListResponse:
        key = _key_depts(page, limit, is_active, search)
        cached = await cache_get(key)
        if cached is not None:
            return schemas.DepartmentListResponse(**cached)

        result = await self.repo.list_departments(
            page=page, limit=limit, is_active=is_active, search=search
        )
        await cache_set(key, result.model_dump(mode="json"), ttl=TTL_DEPARTMENTS)
        return result

    async def get_department_detail(
        self, department_id: uuid.UUID
    ) -> schemas.DepartmentDetailResponse:
        key = _key_dept(department_id)
        cached = await cache_get(key)
        if cached is not None:
            return schemas.DepartmentDetailResponse(**cached)

        dept = await self.repo.get_department_detail(department_id)
        if not dept:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Department not found"
            )

        await cache_set(key, dept.model_dump(mode="json"), ttl=TTL_DEPARTMENTS)
        return dept

    async def create_department(
        self,
        data: schemas.CreateDepartmentRequest,
        created_by_id: uuid.UUID,
        request: Request | None = None,
    ) -> schemas.DepartmentCreatedResponse:
        existing = await self.repo.get_department_by_name_or_code(
            data.department_name, data.department_code
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Department name or code already exists",
            )

        dept_type = await self.repo.get_department_type_by_id(data.department_type_id)
        if not dept_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Department type not found",
            )

        new_dept = None
        async with audit_ctx(
            user_id=str(created_by_id),
            request=request,
            table_name="departments",
            record_id=lambda: str(new_dept.department_id) if new_dept else "UNKNOWN",
            operation="INSERT",
            new_values=lambda: {
                "department_name": data.department_name,
                "department_code": data.department_code,
                "department_type_id": str(data.department_type_id),
            },
        ):
            new_dept = await self.repo.create_department(data, created_by_id)

        await self.invalidate_departments()

        dept_type_resp = (
            schemas.DepartmentTypeResponse.model_validate(new_dept.department_type)
            if new_dept.department_type
            else None
        )

        return schemas.DepartmentCreatedResponse(
            department_id=new_dept.department_id,
            department_name=new_dept.department_name,
            department_code=new_dept.department_code,
            department_type=dept_type_resp,
            is_active=new_dept.is_active,
            created_at=new_dept.created_at,
            created_by=new_dept.created_by,
        )

    async def update_department(
        self,
        department_id: uuid.UUID,
        data: schemas.UpdateDepartmentRequest,
        updated_by_id: uuid.UUID,
        request: Request | None = None,
    ) -> schemas.DepartmentUpdatedResponse:
        existing = await self.repo.get_department_detail(department_id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Department not found"
            )

        update_data = data.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid fields to update",
            )

        if "department_type_id" in update_data and update_data["department_type_id"]:
            dept_type = await self.repo.get_department_type_by_id(
                update_data["department_type_id"]
            )
            if not dept_type:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Department type not found",
                )

        old_snapshot = {
            "department_name": existing.department_name,
            "department_code": existing.department_code,
            "is_active": existing.is_active,
        }

        updated = None
        async with audit_ctx(
            user_id=str(updated_by_id),
            request=request,
            table_name="departments",
            record_id=str(department_id),
            operation="UPDATE",
            old_values=old_snapshot,
            new_values=lambda: {
                k: str(v) if isinstance(v, uuid.UUID) else v
                for k, v in update_data.items()
            },
        ):
            updated = await self.repo.update_department(
                department_id=department_id,
                update_data=update_data,
                updated_by_id=updated_by_id,
            )

        await cache_delete(_key_dept(department_id))
        await invalidate_pattern("org:departments:*")

        dept_type_resp = (
            schemas.DepartmentTypeResponse.model_validate(updated.department_type)
            if updated and updated.department_type
            else None
        )

        return schemas.DepartmentUpdatedResponse(
            department_id=updated.department_id,
            department_name=updated.department_name,
            department_code=updated.department_code,
            department_type=dept_type_resp,
            is_active=updated.is_active,
            updated_at=updated.updated_at,
            updated_by=updated.updated_by,
        )

    # ══════════════════════════════════════════════
    #  Designations
    # ══════════════════════════════════════════════

    async def list_designations(
        self,
        page: int,
        limit: int,
        is_active: bool | None,
    ) -> schemas.DesignationListResponse:
        key = _key_desigs(page, limit, is_active)
        cached = await cache_get(key)
        if cached is not None:
            return schemas.DesignationListResponse(**cached)

        result = await self.repo.list_designations(
            page=page, limit=limit, is_active=is_active
        )
        await cache_set(key, result.model_dump(mode="json"), ttl=TTL_DESIGNATIONS)
        return result

    async def get_designation_detail(
        self, designation_id: uuid.UUID
    ) -> schemas.DesignationDetailResponse:
        key = _key_desig(designation_id)
        cached = await cache_get(key)
        if cached is not None:
            return schemas.DesignationDetailResponse(**cached)

        desig = await self.repo.get_designation_detail(designation_id)
        if not desig:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Designation not found"
            )

        await cache_set(key, desig.model_dump(mode="json"), ttl=TTL_DESIGNATIONS)
        return desig

    async def create_designation(
        self,
        data: schemas.CreateDesignationRequest,
        created_by_id: uuid.UUID,
        request: Request | None = None,
    ) -> schemas.DesignationListItem:
        existing = await self.repo.get_designation_by_name_or_code(
            data.designation_name, data.designation_code
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Designation name or code already exists",
            )

        new_desig = None
        async with audit_ctx(
            user_id=str(created_by_id),
            request=request,
            table_name="designations",
            record_id=lambda: str(new_desig.designation_id) if new_desig else "UNKNOWN",
            operation="INSERT",
            new_values=lambda: {
                "designation_name": data.designation_name,
                "designation_code": data.designation_code,
                "level": data.level,
            },
        ):
            new_desig = await self.repo.create_designation(data, created_by_id)

        await self.invalidate_designations()
        return schemas.DesignationListItem(
            designation_id=new_desig.designation_id,
            designation_name=new_desig.designation_name,
            designation_code=new_desig.designation_code,
            level=new_desig.level,
            is_active=True,
            created_at=new_desig.created_at,
        )

    async def update_designation(
        self,
        designation_id: uuid.UUID,
        data: schemas.UpdateDesignationRequest,
        updated_by_id: uuid.UUID,
        request: Request | None = None,
    ) -> schemas.DesignationDetailResponse:
        existing = await self.repo.get_designation_detail(designation_id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Designation not found"
            )

        update_data = {
            k: v
            for k, v in data.model_dump(exclude_unset=True).items()
            if k not in ("is_active",)
        }
        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid fields to update",
            )

        new_code = update_data.get("designation_code")
        if new_code and new_code != existing.designation_code:
            conflict = await self.repo.check_designation_code_conflict(
                new_code, designation_id
            )
            if conflict:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Designation code '{new_code}' is already in use.",
                )

        old_snapshot = {
            "designation_name": existing.designation_name,
            "designation_code": existing.designation_code,
            "level": existing.level,
        }

        async with audit_ctx(
            user_id=str(updated_by_id),
            request=request,
            table_name="designations",
            record_id=str(designation_id),
            operation="UPDATE",
            old_values=old_snapshot,
            new_values=lambda: update_data,
        ):
            await self.repo.update_designation(
                designation_id=designation_id,
                update_data=update_data,
                updated_by_id=updated_by_id,
            )

        await cache_delete(_key_desig(designation_id))
        await invalidate_pattern("org:designations:*")
        return await self.get_designation_detail(designation_id)

    # ══════════════════════════════════════════════
    #  Status Master
    # ══════════════════════════════════════════════

    async def list_statuses(
        self, entity_type: str | None = None
    ) -> list[schemas.StatusResponse]:
        statuses = await self.repo.list_statuses(entity_type)
        return [schemas.StatusResponse.model_validate(st) for st in statuses]

    async def get_status(self, status_id: uuid.UUID) -> schemas.StatusDetailResponse:
        st = await self.repo.get_status_by_id(status_id)
        if not st:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Status not found"
            )
        return schemas.StatusDetailResponse(
            status_id=st.status_id,
            status_code=st.status_code,
            status_name=st.status_name,
            description=st.description,
            entity_type=st.entity_type,
            created_at=st.created_at,
            updated_at=st.updated_at,
        )

    async def create_status(
        self,
        data: schemas.CreateStatusRequest,
        created_by_id: uuid.UUID,
        request: Request | None = None,
    ) -> schemas.StatusDetailResponse:
        existing = await self.repo.get_status_by_code(data.status_code)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="CONFLICT – status_code already exists",
            )

        new_st = None
        async with audit_ctx(
            user_id=str(created_by_id),
            request=request,
            table_name="status_master",
            record_id=lambda: str(new_st.status_id) if new_st else "UNKNOWN",
            operation="INSERT",
            new_values=lambda: {
                "status_code": data.status_code,
                "status_name": data.status_name,
                "entity_type": data.entity_type,
            },
        ):
            new_st = await self.repo.create_status(data, created_by_id)

        return schemas.StatusDetailResponse(
            status_id=new_st.status_id,
            status_code=new_st.status_code,
            status_name=new_st.status_name,
            description=new_st.description,
            entity_type=new_st.entity_type,
            created_at=new_st.created_at,
            updated_at=new_st.updated_at,
        )

    async def update_status(
        self,
        status_id: uuid.UUID,
        data: schemas.UpdateStatusRequest,
        updated_by_id: uuid.UUID,
        request: Request | None = None,
    ) -> schemas.StatusDetailResponse:
        existing = await self.repo.get_status_by_id(status_id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Status not found"
            )

        update_data = data.model_dump(exclude_unset=True)
        old_snapshot = {
            "status_name": existing.status_name,
            "description": existing.description,
        }

        updated = None
        async with audit_ctx(
            user_id=str(updated_by_id),
            request=request,
            table_name="status_master",
            record_id=str(status_id),
            operation="UPDATE",
            old_values=old_snapshot,
            new_values=lambda: update_data,
        ):
            updated = await self.repo.update_status(
                status_id=status_id,
                update_data=update_data,
                updated_by_id=updated_by_id,
            )

        return schemas.StatusDetailResponse(
            status_id=updated.status_id,
            status_code=updated.status_code,
            status_name=updated.status_name,
            description=updated.description,
            entity_type=updated.entity_type,
            created_at=updated.created_at,
            updated_at=updated.updated_at,
        )

    # ══════════════════════════════════════════════
    #  Audit Logs Viewer
    # ══════════════════════════════════════════════

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
        return await self.repo.list_audit_logs(
            page=page,
            limit=limit,
            table_name=table_name,
            record_id=record_id,
            operation_type=operation_type,
            performed_by=performed_by,
            start_date=start_date,
            end_date=end_date,
        )

    async def get_audit_log(self, audit_id: uuid.UUID) -> schemas.AuditLogResponse:
        log = await self.repo.get_audit_log(audit_id)
        if not log:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Audit log entry not found.",
            )
        return log